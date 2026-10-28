#!/usr/bin/env bash
# Тесты deploy.sh и scripts/server-setup.sh (задача 7.5). Без Docker, сети и root: docker, curl, uname, git и т.п. - заглушки в PATH.
# Запуск: ./scripts/tests/test_deploy.sh   Код возврата 0 = все проверки прошли.
# shellcheck disable=SC2015,SC2016  # A && B || C в проверках намеренно; одинарные кавычки - тексты заглушек
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (ожидалось: $2 | получено: $3)"; fi; }
contains() { if grep -qF -- "$3" <<< "$2"; then ok "$1"; else bad "$1 (нет '$3' в: $(head -c 300 <<< "$2"))"; fi; }
lacks() { if grep -qF -- "$3" <<< "$2"; then bad "$1 (не ожидалось '$3')"; else ok "$1"; fi; }

# ── Заглушки ─────────────────────────────────────────────────────────────────
BIN="$TMP/bin"
STATE="$TMP/state"
mkdir -p "$BIN" "$STATE"
cat > "$BIN/docker" <<'MOCK'
#!/bin/sh
echo "docker platform=${DOCKER_DEFAULT_PLATFORM:-} tag=${IMAGE_TAG:-} $*" >> "$STUB_LOG"
case "$1" in
    info) exit 0 ;;
    image) [ "${STUB_NO_IMAGES:-0}" = 1 ] && exit 1; exit 0 ;;
esac
[ "$1" = compose ] || exit 0
shift
sub=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --env-file) shift 2 ;;
        -*) shift ;;
        *) sub="$1"; break ;;
    esac
done
case "$sub" in
    ps) [ "${STUB_DB_RUNNING:-0}" = 1 ] && echo abc123def; exit 0 ;;
    exec)
        case "$*" in *"nginx -s reload"*) [ "${STUB_RELOAD_FAIL:-0}" = 1 ] && exit 1; exit 0 ;; esac
        [ "${STUB_NO_DUMMY:-0}" = 1 ] && exit 1; exit 0 ;;
    up)
        if [ "${IMAGE_TAG:-}" = "${STUB_UP_FAIL_TAG:-none}" ]; then exit 1; fi
        echo "${IMAGE_TAG:-}" > "$STUB_STATE/last_up_tag"
        exit 0 ;;
    *) exit 0 ;;
esac
MOCK
cat > "$BIN/curl" <<'MOCK'
#!/bin/sh
echo "curl $*" >> "$STUB_LOG"
last=$(cat "$STUB_STATE/last_up_tag" 2> /dev/null || echo none)
if [ "$last" = "${STUB_SMOKE_BAD_TAG:-none}" ]; then printf '503'; else printf '%s' "${STUB_CURL_CODE:-200}"; fi
MOCK
cat > "$BIN/uname" <<'MOCK'
#!/bin/sh
[ "$1" = "-m" ] && echo "${STUB_ARCH:-x86_64}" || echo Linux
MOCK
cat > "$BIN/git" <<'MOCK'
#!/bin/sh
echo "git $*" >> "$STUB_LOG"
case "$1" in
    rev-parse)
        case "$*" in
            *--short*) echo "${STUB_SHA:-b2b2b2b}" ;;
            *) echo "${STUB_FULL_SHA:-cccccccccccccccccccccccccccccccccccccccc}" ;;
        esac ;;
esac
exit 0
MOCK
chmod +x "$BIN"/*

# Каталог "проекта": копия deploy.sh + заглушки скриптов, которые он вызывает.
new_project() {
    P=$(mktemp -d -p "$TMP")
    mkdir -p "$P/scripts" "$P/nginx" "$P/frontend"
    cp "$ROOT/deploy.sh" "$P/deploy.sh"
    printf '#!/bin/sh\necho "backup.sh $*" >> "$STUB_LOG"\nmkdir -p "${BACKUP_DIR:-./backups}"\ntouch "${BACKUP_DIR:-./backups}/autoforyou_2026-01-01_0330.dump"\n' > "$P/scripts/backup.sh"
    printf '#!/bin/sh\necho "update-cloudflare-ips.sh" >> "$STUB_LOG"\n' > "$P/scripts/update-cloudflare-ips.sh"
    chmod +x "$P/scripts/"*.sh "$P/deploy.sh"
    : > "$STUB_LOG"
    rm -f "$STATE/last_up_tag"
}
STUB_LOG="$TMP/docker.log"
export STUB_LOG STUB_STATE="$STATE"

# Корректный .env; аргументы вида KEY=VALUE дописываются ниже и переопределяют (последняя строка побеждает).
mkenv() {
    {
        cat <<'ENV'
SECRET_KEY=test-only-secret-key-for-deploy-sh-stubs-not-a-real-one
POSTGRES_PASSWORD=test-only-pg-pass
DATABASE_URL=postgres://autoforyou:test-only-pg-pass@db:5432/autoforyou
REDIS_PASSWORD=Strong0RedisXyz
DEBUG=false
DOMAIN=shop.example.test
ALLOWED_HOSTS=shop.example.test,localhost
SITE_URL=https://shop.example.test
TLS_MODE=letsencrypt
NEXT_PUBLIC_API_URL=https://shop.example.test
NEXT_PUBLIC_SITE_URL=https://shop.example.test
ENV
        for kv in "$@"; do echo "$kv"; done
    } > "$P/.env"
}

# run_deploy [аргументы deploy.sh]: в $OUT вывод (stdout+stderr), в $RC код. Окружение чистое, как у cron/ssh.
run_deploy() {
    set +e
    # shellcheck disable=SC2086  # STUB_ENV - несколько присваиваний через пробел
    OUT=$(cd "$P" && env -i PATH="$BIN:/usr/bin:/bin" HOME="$TMP" STUB_LOG="$STUB_LOG" STUB_STATE="$STATE" \
        DEPLOY_SMOKE_RETRIES=2 DEPLOY_SMOKE_SLEEP=0 ${STUB_ENV:-} bash ./deploy.sh "$@" 2>&1)
    RC=$?
    set -e
}
docker_log() { cat "$STUB_LOG"; }

# ── 1. Проверки конфигурации ─────────────────────────────────────────────────
new_project
run_deploy
[ "$RC" -ne 0 ] && ok "нет .env: код != 0" || bad "нет .env: ожидался код != 0"
contains "нет .env: сообщение" "$OUT" ".env не найден"

new_project; mkenv "SECRET_KEY=REPLACE-with-real-key"
run_deploy
[ "$RC" -ne 0 ] && ok "SECRET_KEY с REPLACE: код != 0" || bad "SECRET_KEY с REPLACE: ожидался код != 0"
contains "SECRET_KEY с REPLACE: сообщение о заглушке" "$OUT" "placeholder"

new_project; mkenv "DEBUG=true"
run_deploy
[ "$RC" -ne 0 ] && ok "DEBUG=true: код != 0" || bad "DEBUG=true: ожидался код != 0"
contains "DEBUG=true: сообщение" "$OUT" "DEBUG is enabled"

new_project; mkenv "SITE_URL=http://shop.example.test"
run_deploy
[ "$RC" -ne 0 ] && ok "SITE_URL http при TLS_MODE=letsencrypt: код != 0" || bad "SITE_URL http при letsencrypt: ожидался код != 0"
contains "SITE_URL http: сообщение про https" "$OUT" "https://"

new_project; mkenv "ALLOWED_HOSTS=other.example.test"
run_deploy
[ "$RC" -ne 0 ] && ok "ALLOWED_HOSTS без DOMAIN: код != 0" || bad "ALLOWED_HOSTS без DOMAIN: ожидался код != 0"
contains "ALLOWED_HOSTS без DOMAIN: сообщение" "$OUT" "ALLOWED_HOSTS"

new_project; mkenv "ALLOWED_HOSTS=.example.test"
run_deploy
check "ALLOWED_HOSTS=.example.test покрывает shop.example.test (как в Django): код 0" "0" "$RC"

new_project; mkenv "ALLOWED_HOSTS=.other.test"
run_deploy
[ "$RC" -ne 0 ] && ok "ALLOWED_HOSTS=.other.test не покрывает домен: код != 0" || bad ".other.test: ожидался код != 0"

new_project; mkenv "ALLOWED_HOSTS=shop.example.test,*"
run_deploy
[ "$RC" -ne 0 ] && ok "'*' в ALLOWED_HOSTS: код != 0" || bad "'*' в ALLOWED_HOSTS: ожидался код != 0"
contains "'*' в ALLOWED_HOSTS: сообщение" "$OUT" "содержит '*'"

# Прочие проверки значений
new_project; mkenv "CORS_ALLOW_ALL_ORIGINS=true"
run_deploy
[ "$RC" -ne 0 ] && ok "CORS_ALLOW_ALL_ORIGINS=true: код != 0" || bad "CORS_ALLOW_ALL_ORIGINS=true: ожидался код != 0"
contains "CORS_ALLOW_ALL_ORIGINS: сообщение" "$OUT" "CORS_ALLOW_ALL_ORIGINS"

new_project; mkenv "POSTGRES_PASSWORD=changeme"
run_deploy
[ "$RC" -ne 0 ] && ok "слабый POSTGRES_PASSWORD: код != 0" || bad "слабый POSTGRES_PASSWORD: ожидался код != 0"
contains "слабый POSTGRES_PASSWORD: сообщение" "$OUT" "POSTGRES_PASSWORD"

new_project; mkenv "DATABASE_URL=postgres://autoforyou:<POSTGRES_PASSWORD>@db:5432/autoforyou"
run_deploy
[ "$RC" -ne 0 ] && ok "заглушка <...> в DATABASE_URL: код != 0" || bad "заглушка в DATABASE_URL: ожидался код != 0"
contains "заглушка в DATABASE_URL: сообщение" "$OUT" "заглушку"

new_project; mkenv "DATABASE_URL=postgres://u:test-only-pg-pass@host.docker.internal:5432/x"
run_deploy
[ "$RC" -ne 0 ] && ok "host.docker.internal в DATABASE_URL: код != 0" || bad "host.docker.internal: ожидался код != 0"
contains "host.docker.internal: сообщение" "$OUT" "host.docker.internal"

# ── Формат .env: неоднозначные строки отвергаются, значения нормализуются ──
for bad_line in "DEBUG = true" "DEBUG: true" "export DEBUG=true"; do
    new_project; mkenv "$bad_line"
    run_deploy
    [ "$RC" -ne 0 ] && ok "строка '$bad_line': код != 0" || bad "строка '$bad_line': ожидался код != 0"
    contains "строка '$bad_line': указан номер строки" "$OUT" "строка 12"
done
new_project; mkenv 'DEBUG="True"'
run_deploy
[ "$RC" -ne 0 ] && ok 'DEBUG="True" в кавычках распознан как включённый: код != 0' || bad 'DEBUG="True": ожидался код != 0'
new_project; mkenv "DEBUG='true'"
run_deploy
[ "$RC" -ne 0 ] && ok "DEBUG='true' в кавычках: код != 0" || bad "DEBUG='true': ожидался код != 0"
new_project; mkenv "DEBUG=true"
sed -i 's/$/\r/' "$P/.env"
run_deploy
[ "$RC" -ne 0 ] && ok "CRLF в .env: DEBUG=true распознан: код != 0" || bad "CRLF: DEBUG=true не распознан"
new_project; mkenv
sed -i 's/$/\r/' "$P/.env"
run_deploy
check "CRLF в .env не ломает остальные значения: код 0" "0" "$RC"
# DEBUG=false в окружении shell не должен маскировать DEBUG=true из файла
new_project; mkenv "DEBUG=true"
STUB_ENV="DEBUG=false" run_deploy
[ "$RC" -ne 0 ] && ok "DEBUG=false в shell не маскирует DEBUG=true в файле" || bad "DEBUG из shell замаскировал файл"
new_project; mkenv "TLS_MODE=off" "SITE_URL=http://localhost" "DOMAIN=localhost" "ALLOWED_HOSTS=localhost"
STUB_ENV="TLS_MODE=letsencrypt" run_deploy
check "TLS_MODE из shell не подменяет файл (off в файле): код 0" "0" "$RC"
for key in BASH_ENV ENV LD_PRELOAD LD_LIBRARY_PATH PATH IFS PS4 SHELLOPTS BASHOPTS DOCKER_HOST DOCKER_CONFIG GIT_DIR GIT_SSH_COMMAND; do
    new_project; mkenv "$key=/tmp/x"
    run_deploy
    [ "$RC" -ne 0 ] && ok "опасный ключ $key в .env: код != 0" || bad "опасный ключ $key: ожидался код != 0"
    contains "опасный ключ $key: сообщение" "$OUT" "запрещена"
done

new_project; mkenv "DOMAIN="
run_deploy
[ "$RC" -ne 0 ] && ok "пустой DOMAIN: код != 0" || bad "пустой DOMAIN: ожидался код != 0"
contains "пустой DOMAIN: сообщение" "$OUT" "DOMAIN не задан"

new_project; mkenv "TLS_MODE=off" "SITE_URL=http://localhost" "DOMAIN=localhost" "ALLOWED_HOSTS=localhost"
run_deploy
check "TLS_MODE=off с http SITE_URL допустим: код 0" "0" "$RC"

# ── 2. .env читается как данные, а не исполняется ────────────────────────────
new_project; mkenv "SECRET_KEY=abc#def\$(touch $P/PWNED)(x)<y>zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz" "B2B_ENABLED=\"false\""
run_deploy
check "значения с \$(...), #, <> не исполняются: код 0" "0" "$RC"
[ ! -e "$P/PWNED" ] && ok "команда из значения .env не выполнена" || bad "команда из .env выполнена!"

new_project; mkenv "DEPLOY_X=1"
mv "$P/.env" "$P/custom.env"
STUB_ENV="DEPLOY_ENV_FILE=custom.env" run_deploy
check "DEPLOY_ENV_FILE=custom.env: код 0" "0" "$RC"
contains "DEPLOY_ENV_FILE передаётся в docker compose --env-file" "$(docker_log)" "--env-file custom.env"

# ── 3. Архитектура ───────────────────────────────────────────────────────────
for pair in "x86_64:linux/amd64" "aarch64:linux/arm64" "arm64:linux/arm64"; do
    arch=${pair%%:*}; plat=${pair##*:}
    new_project; mkenv
    STUB_ENV="STUB_ARCH=$arch STUB_NO_DUMMY=1" run_deploy
    check "uname -m=$arch: код 0" "0" "$RC"
    contains "uname -m=$arch: платформа $plat у docker" "$(docker_log)" "platform=$plat"
    lacks "uname -m=$arch: нет предупреждений" "$OUT" "ПРЕДУПРЕЖДЕНИЕ"
done
new_project; mkenv
STUB_ENV="STUB_ARCH=riscv64" run_deploy
[ "$RC" -ne 0 ] && ok "uname -m=riscv64: код != 0" || bad "riscv64: ожидался код != 0"
contains "riscv64: сообщение" "$OUT" "не поддерживается"

# ── 4. Успешный деплой, теги, бэкап, флаги ───────────────────────────────────
new_project; mkenv
mkdir -p "$P/.deploy"; echo a1a1a1a > "$P/.deploy/current_tag"
STUB_ENV="STUB_DB_RUNNING=1" run_deploy --build
check "деплой: код 0" "0" "$RC"
check "деплой: current_tag = новый sha" "b2b2b2b" "$(cat "$P/.deploy/current_tag")"
check "деплой: previous_tag = прежний current_tag" "a1a1a1a" "$(cat "$P/.deploy/previous_tag")"
contains "деплой: бэкап вызван" "$(docker_log)" "backup.sh --now"
contains "деплой: путь к дампу напечатан" "$OUT" "autoforyou_2026-01-01_0330.dump"
contains "деплой: --build передан в compose up" "$(docker_log)" "--build"
if docker_log | grep -qE ' up -d$'; then ok "деплой: остальные сервисы (bot, backup) запущены без --wait"; else bad "деплой: нет запуска остальных сервисов"; fi
contains "деплой: ждём healthy" "$(docker_log)" "--wait"
contains "деплой: smoke ходит на /healthz" "$(docker_log)" "/healthz"
contains "деплой: smoke через --resolve на 127.0.0.1" "$(docker_log)" "--resolve shop.example.test:443:127.0.0.1"
lacks "деплой без --pull не делает git pull" "$(docker_log)" "git pull"
if docker_log | grep -q 'exec -T nginx nginx -s reload'; then ok "деплой: nginx перечитывает адреса upstream (reload)"; else bad "деплой: нет nginx -s reload"; fi

new_project; mkenv
mkdir -p "$P/.deploy"; echo a1a1a1a > "$P/.deploy/current_tag"
STUB_ENV="STUB_RELOAD_FAIL=1" run_deploy --build
[ "$RC" -ne 0 ] && ok "nginx reload не удался: код != 0" || bad "nginx reload не удался: ожидался код != 0"
contains "nginx reload не удался: автоматический откат" "$OUT" "автоматический откат"

new_project; mkenv
STUB_ENV="STUB_DB_RUNNING=0" run_deploy
check "первый деплой (БД нет): код 0" "0" "$RC"
lacks "первый деплой: бэкап не вызывается" "$(docker_log)" "backup.sh"

new_project; mkenv
STUB_ENV="STUB_DB_RUNNING=1" run_deploy --skip-backup
lacks "--skip-backup: бэкап не вызывается" "$(docker_log)" "backup.sh"
contains "--skip-backup: предупреждение" "$OUT" "бэкап пропущен"

new_project; mkenv
run_deploy --pull
contains "--pull: git pull --ff-only" "$(docker_log)" "git pull --ff-only"

new_project; mkenv "B2B_ENABLED=true"
run_deploy
check "замороженный флаг true: деплой идёт (код 0)" "0" "$RC"
contains "замороженный флаг true: предупреждение" "$OUT" "B2B_ENABLED=true"

new_project; mkenv "CLOUDFLARE_PROXY=true"
run_deploy
contains "CLOUDFLARE_PROXY=true: вызван update-cloudflare-ips.sh" "$(docker_log)" "update-cloudflare-ips.sh"
new_project; mkenv "CLOUDFLARE_PROXY=false"
run_deploy
lacks "CLOUDFLARE_PROXY=false: update-cloudflare-ips.sh не вызывается" "$(docker_log)" "update-cloudflare-ips.sh"

# ── 4a. EXPECTED_SHA, проверка файлов состояния, curl -k ─────────────────────
FULL=cccccccccccccccccccccccccccccccccccccccc
new_project; mkenv
STUB_ENV="EXPECTED_SHA=$FULL STUB_FULL_SHA=$FULL" run_deploy --pull
check "EXPECTED_SHA совпал с HEAD: код 0" "0" "$RC"
new_project; mkenv
STUB_ENV="EXPECTED_SHA=$FULL STUB_FULL_SHA=dddddddddddddddddddddddddddddddddddddddd" run_deploy --pull
[ "$RC" -ne 0 ] && ok "EXPECTED_SHA не совпал с HEAD: код != 0" || bad "EXPECTED_SHA не совпал: ожидался код != 0"
contains "EXPECTED_SHA: сообщение" "$OUT" "не тот коммит"
lacks "EXPECTED_SHA: до запуска стека дело не дошло" "$(docker_log)" " up -d"
new_project; mkenv
STUB_ENV="EXPECTED_SHA=abc" run_deploy --pull
[ "$RC" -ne 0 ] && ok "EXPECTED_SHA не 40 hex: код != 0" || bad "EXPECTED_SHA короткий: ожидался код != 0"
new_project; mkenv
STUB_ENV="EXPECTED_SHA=abc STUB_FULL_SHA=abc" run_deploy --pull
[ "$RC" -ne 0 ] && ok "EXPECTED_SHA не 40 hex (даже если равен HEAD): код != 0" || bad "EXPECTED_SHA=abc=HEAD: ожидался код != 0"
contains "EXPECTED_SHA формат: сообщение" "$OUT" "40 hex"

new_project; mkenv
mkdir -p "$P/.deploy"; echo 'a1a1a1a; touch PWNED' > "$P/.deploy/current_tag"
run_deploy
[ "$RC" -ne 0 ] && ok "повреждённый .deploy/current_tag: код != 0" || bad "повреждённый тег: ожидался код != 0"
contains "повреждённый тег: сообщение" "$OUT" "повреждён"

new_project; mkenv
run_deploy
check "каталог .deploy создан с правами 700" "700" "$(stat -c %a "$P/.deploy")"

new_project; mkenv "TLS_MODE=selfsigned"
run_deploy
contains "selfsigned: curl с -k" "$(docker_log)" "curl -s -k"
new_project; mkenv "TLS_MODE=letsencrypt"
STUB_ENV="STUB_NO_DUMMY=1" run_deploy
lacks "letsencrypt с настоящим сертификатом: curl без -k" "$(docker_log)" "curl -s -k"
new_project; mkenv "TLS_MODE=letsencrypt"
run_deploy
contains "letsencrypt с временным сертификатом: curl с -k" "$(docker_log)" "curl -s -k"
new_project; mkenv "TLS_MODE=off" "SITE_URL=http://localhost" "DOMAIN=localhost" "ALLOWED_HOSTS=localhost"
run_deploy
lacks "TLS_MODE=off: curl без -k" "$(docker_log)" "curl -s -k"

# ── 5. Откат ─────────────────────────────────────────────────────────────────
new_project; mkenv
mkdir -p "$P/.deploy"; echo a1a1a1a > "$P/.deploy/current_tag"
STUB_ENV="STUB_SMOKE_BAD_TAG=b2b2b2b" run_deploy --skip-backup
[ "$RC" -ne 0 ] && ok "провал smoke: код != 0" || bad "провал smoke: ожидался код != 0"
check "провал smoke: поднят предыдущий тег" "a1a1a1a" "$(cat "$STATE/last_up_tag")"
check "провал smoke: current_tag не изменился" "a1a1a1a" "$(cat "$P/.deploy/current_tag")"
contains "провал smoke: сообщено про миграции БД" "$OUT" "миграции БД автоматически НЕ откатываются"
contains "провал smoke: сообщено про restore.sh" "$OUT" "restore.sh"

new_project; mkenv
mkdir -p "$P/.deploy"; echo a1a1a1a > "$P/.deploy/current_tag"
STUB_ENV="STUB_UP_FAIL_TAG=b2b2b2b" run_deploy --skip-backup
[ "$RC" -ne 0 ] && ok "провал up --wait: код != 0" || bad "провал up --wait: ожидался код != 0"
check "провал up --wait: поднят предыдущий тег" "a1a1a1a" "$(cat "$STATE/last_up_tag")"

new_project; mkenv
STUB_ENV="STUB_SMOKE_BAD_TAG=b2b2b2b" run_deploy --skip-backup
[ "$RC" -ne 0 ] && ok "первый деплой с провалом smoke: код != 0" || bad "ожидался код != 0"
contains "первый деплой с провалом: откатываться некуда" "$OUT" "откатываться некуда"

new_project; mkenv
run_deploy --rollback
[ "$RC" -ne 0 ] && ok "--rollback без previous_tag: код != 0" || bad "--rollback без previous_tag: ожидался код != 0"
contains "--rollback без previous_tag: понятная ошибка" "$OUT" "нет .deploy/previous_tag"

new_project; mkenv
mkdir -p "$P/.deploy"; echo a1a1a1a > "$P/.deploy/previous_tag"; echo b2b2b2b > "$P/.deploy/current_tag"
run_deploy --rollback
check "--rollback: код 0" "0" "$RC"
check "--rollback: поднят previous_tag" "a1a1a1a" "$(cat "$STATE/last_up_tag")"
check "--rollback: теги поменялись местами (current)" "a1a1a1a" "$(cat "$P/.deploy/current_tag")"
check "--rollback: теги поменялись местами (previous)" "b2b2b2b" "$(cat "$P/.deploy/previous_tag")"
lacks "--rollback не делает бэкап и git pull" "$(docker_log)" "backup.sh"

new_project; mkenv
mkdir -p "$P/.deploy"; echo a1a1a1a > "$P/.deploy/previous_tag"
STUB_ENV="STUB_NO_IMAGES=1" run_deploy --rollback
[ "$RC" -ne 0 ] && ok "--rollback без локальных образов: код != 0" || bad "ожидался код != 0"
contains "--rollback без образов: сообщение" "$OUT" "образы с тегом"

new_project; mkenv
run_deploy --help
check "--help: код 0" "0" "$RC"
new_project; mkenv
run_deploy --bogus
[ "$RC" -ne 0 ] && ok "неизвестный аргумент: код != 0" || bad "неизвестный аргумент: ожидался код != 0"

# ── 6. server-setup.sh: повторный запуск не создаёт второй swap ──────────────
# Заглушки root-команд; состояние swap и сгенерированные файлы лежат в песочнице.
SS="$TMP/ss"
mkdir -p "$SS/bin" "$SS/etc/sysctl.d" "$SS/etc/fstab.d"
: > "$SS/fstab"
SS_LOG="$SS/calls.log"
for cmd in apt-get apt install curl gpg ufw systemctl sysctl useradd usermod chmod chown dpkg mkswap fallocate dd getent id install; do
    printf '#!/bin/sh\necho "%s $*" >> "%s"\nexit 0\n' "$cmd" "$SS_LOG" > "$SS/bin/$cmd"
done
# id -u должен вернуть 0 (root), getent group docker - успех, пользователя deploy "нет" при первом запуске.
printf '#!/bin/sh\n[ "$1" = "-u" ] && { echo "${STUB_UID:-0}"; exit 0; }\nexit 1\n' > "$SS/bin/id"
printf '#!/bin/sh\nfor p in $STUB_SSHD_PORTS; do echo "port $p"; done\necho "addressfamily any"\n' > "$SS/bin/sshd"
printf '#!/bin/sh\necho "swapon $*" >> "%s"\n[ -f "%s/swap_on" ] && echo "/swapfile file 2G 0B -2"\nexit 0\n' "$SS_LOG" "$SS" > "$SS/bin/swapon"
printf '#!/bin/sh\necho "mkswap $*" >> "%s"\nexit 0\n' "$SS_LOG" > "$SS/bin/mkswap"
chmod +x "$SS/bin/"*
run_setup() {
    set +e
    SS_OUT=$(env -i PATH="$SS/bin:/usr/bin:/bin" HOME="$TMP" SS_ROOT="$SS" SWAP_FILE="$SS/swapfile" FSTAB_FILE="$SS/fstab" \
        SYSCTL_FILE="$SS/etc/sysctl.d/99-autoforyou.conf" SERVER_SETUP_SKIP_APT=1 SWAP_SIZE_GB=1 STUB_SSHD_PORTS="${STUB_SSHD_PORTS:-}" bash "$ROOT/scripts/server-setup.sh" 2>&1)
    SS_RC=$?
    set -e
}
STUB_SSHD_PORTS="2222 22"; export STUB_SSHD_PORTS
run_setup
check "server-setup (1-й запуск): код 0" "0" "$SS_RC"
allow_line=$(grep -n '^ufw allow 2222/tcp' "$SS_LOG" | head -n 1 | cut -d: -f1 || true)
enable_line=$(grep -n '^ufw --force enable' "$SS_LOG" | head -n 1 | cut -d: -f1 || true)
if [ -n "$allow_line" ] && [ -n "$enable_line" ] && [ "$allow_line" -lt "$enable_line" ]; then ok "ufw: порт SSH из sshd -T (2222) разрешён до enable"; else bad "ufw: allow 2222 не раньше enable ($allow_line/$enable_line)"; fi
check "ufw: второй порт sshd (22) тоже разрешён" "1" "$(grep -c '^ufw allow 22/tcp' "$SS_LOG" || true)"
check "ufw: allow 80 и 443 есть" "2" "$(grep -cE '^ufw allow (80|443)/tcp' "$SS_LOG" || true)"
check "server-setup: swap создан один раз" "1" "$(grep -c '^mkswap ' "$SS_LOG" || true)"
touch "$SS/swap_on"
run_setup
check "server-setup (повтор, swap уже включён): код 0" "0" "$SS_RC"
check "server-setup: повтор не создаёт второй swap" "1" "$(grep -c '^mkswap ' "$SS_LOG" || true)"
contains "server-setup: swap уже есть - сообщение" "$SS_OUT" "swap уже настроен"
check "server-setup: vm.swappiness записан в sysctl-файл" "1" "$(grep -c '^vm.swappiness' "$SS/etc/sysctl.d/99-autoforyou.conf" || true)"
check "server-setup: запись swap в fstab не дублируется" "1" "$(grep -c "$SS/swapfile" "$SS/fstab" || true)"
# sshd ничего не вернул: запасной порт 22
: > "$SS_LOG"; rm -f "$SS/swap_on"
STUB_SSHD_PORTS="" run_setup
check "ufw: sshd -T пуст - запасной порт 22" "1" "$(grep -c '^ufw allow 22/tcp' "$SS_LOG" || true)"
# SSH_PORT вне диапазона - отказ до любых изменений ufw
: > "$SS_LOG"
SS_OUT=$(env -i PATH="$SS/bin:/usr/bin:/bin" SS_ROOT="$SS" SWAP_FILE="$SS/swapfile" FSTAB_FILE="$SS/fstab" SYSCTL_FILE="$SS/etc/sysctl.d/99-autoforyou.conf" SERVER_SETUP_SKIP_APT=1 STUB_SSHD_PORTS="2222" SSH_PORT=70000 bash "$ROOT/scripts/server-setup.sh" 2>&1 || true)
contains "SSH_PORT вне 1-65535: отказ" "$SS_OUT" "1-65535"
check "SSH_PORT вне диапазона: ufw не тронут" "0" "$(grep -c '^ufw ' "$SS_LOG" || true)"
SS_OUT=$(env -i PATH="$SS/bin:/usr/bin:/bin" STUB_UID=1000 bash "$ROOT/scripts/server-setup.sh" 2>&1 || true)
contains "server-setup не от root: отказ" "$SS_OUT" "root"

echo
if [ "$fails" -eq 0 ]; then echo "Все проверки прошли."; else echo "Провалено проверок: $fails"; exit 1; fi
