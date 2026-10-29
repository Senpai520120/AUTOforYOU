#!/usr/bin/env bash
# deploy.sh - развёртывание стека на любом Linux-VPS с Docker Engine и Compose v2 (задача 7.5).
#
# Порядок: проверки -> git pull (--pull) -> бэкап БД -> сборка и запуск с тегом IMAGE_TAG=<git short sha>
#          -> smoke (/healthz и / через локальный nginx) -> итог. При провале запуска или smoke
#          автоматически поднимаются образы предыдущего деплоя (.deploy/previous_tag).
#
# Использование: ./deploy.sh [--pull] [--build] [--skip-backup] [--rollback] [--smoke-e2e] [--help]
#
# Переменные окружения (всё необязательно):
#   DEPLOY_ENV_FILE       файл настроек (по умолчанию .env в каталоге скрипта)
#   COMPOSE_FILE          файлы compose (стандартная переменная Compose, разделитель :)
#   COMPOSE_PROJECT_NAME  имя проекта Compose (стандартная переменная Compose)
#   EXPECTED_SHA          полный sha коммита, который должен быть на сервере после --pull (задаёт CI)
#   DEPLOY_WAIT_TIMEOUT   секунд на `up --wait` (по умолчанию 300)
#   DEPLOY_SMOKE_RETRIES, DEPLOY_SMOKE_SLEEP  число и пауза (с) попыток smoke (15 и 2)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

ENV_FILE="${DEPLOY_ENV_FILE:-.env}"
STATE_DIR=".deploy"
WAIT_TIMEOUT="${DEPLOY_WAIT_TIMEOUT:-300}"
SMOKE_RETRIES="${DEPLOY_SMOKE_RETRIES:-15}"
SMOKE_SLEEP="${DEPLOY_SMOKE_SLEEP:-2}"
# Сервисы, которых ждём (healthy). bot без токена завершается кодом 0, поэтому его и backup ждать нельзя:
# они запускаются вторым вызовом без --wait.
WAIT_SERVICES=(db redis backend frontend nginx celery_worker celery_beat)

log() { echo "[deploy] $*"; }
warn() { echo "[deploy] ПРЕДУПРЕЖДЕНИЕ: $*" >&2; }
die() { echo "ERROR: $*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Использование: ./deploy.sh [опции]

  --pull         перед деплоем выполнить git pull --ff-only
  --build        пересобрать образы (на сервере обычно нужен после --pull)
  --skip-backup  не делать бэкап БД перед деплоем (только осознанно)
  --rollback     поднять образы предыдущего деплоя (.deploy/previous_tag); данные БД не откатываются
  --smoke-e2e    после деплоя прогнать Playwright @smoke (нужны node/npx и `npm ci` в frontend/)
  --help         эта справка

Настройки читаются из .env (или DEPLOY_ENV_FILE). Подробности: DEPLOY_NOTES.md.
USAGE
}

DO_PULL=0
DO_BUILD=0
SKIP_BACKUP=0
DO_ROLLBACK=0
DO_E2E=0
for arg in "$@"; do
    case "$arg" in
        --pull) DO_PULL=1 ;;
        --build) DO_BUILD=1 ;;
        --skip-backup) SKIP_BACKUP=1 ;;
        --rollback) DO_ROLLBACK=1 ;;
        --smoke-e2e) DO_E2E=1 ;;
        --help | -h) usage; exit 0 ;;
        *) usage >&2; die "неизвестный аргумент: $arg" ;;
    esac
done

# ─── Загрузка настроек ───────────────────────────────────────────────────────
# Файл не исполняется как shell (в нём бывают значения с пробелами, # и $): читаются только строки KEY=VALUE.
# Формы `KEY = value`, `KEY: value`, `export KEY=value` Compose читает иначе, чем человек, поэтому это ошибка с номером строки.
# Кавычки вокруг значения и CRLF снимаются, как в Compose. Уже заданные в окружении переменные не перезаписываются,
# КРОМЕ ключей проверок (SECURITY_KEYS): их значения берутся только из файла, окружение shell их не маскирует.
SECURITY_KEYS=(DEBUG CORS_ALLOW_ALL_ORIGINS ALLOWED_HOSTS TLS_MODE SITE_URL DOMAIN SECRET_KEY)
# Переменные, которые меняют поведение shell, загрузчика или Docker/git: в .env им не место.
is_dangerous_key() {
    case "$1" in
        BASH_ENV | ENV | LD_PRELOAD | LD_LIBRARY_PATH | PATH | IFS | PS4 | SHELLOPTS | BASHOPTS | DOCKER_HOST | DOCKER_CONFIG | GIT_*) return 0 ;;
    esac
    return 1
}
load_env() {
    local line key val n=0 k
    local -A from_file=()
    for k in "${SECURITY_KEYS[@]}"; do unset "$k"; done
    while IFS= read -r line || [ -n "$line" ]; do
        n=$((n + 1))
        line="${line%$'\r'}"
        line="${line#"${line%%[![:space:]]*}"}"
        case "$line" in '' | '#'*) continue ;; esac
        if ! [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            die "$ENV_FILE, строка $n: ожидается KEY=value без пробелов вокруг '=' и без 'export' или ':' (получено: '${line%%=*}')."
        fi
        key="${BASH_REMATCH[1]}"
        val="${BASH_REMATCH[2]}"
        is_dangerous_key "$key" && die "$ENV_FILE, строка $n: переменная $key в .env запрещена (меняет поведение shell/Docker)."
        if [[ "$val" =~ ^\"(.*)\"[[:space:]]*$ ]] || [[ "$val" =~ ^\'(.*)\'[[:space:]]*$ ]]; then
            val="${BASH_REMATCH[1]}"
        else
            val="${val%%[[:space:]]#*}"
            val="${val%"${val##*[![:space:]]}"}"
        fi
        # Повтор ключа в файле: побеждает последняя строка (как в Compose).
        if [ -z "${!key+x}" ] || [ -n "${from_file[$key]+x}" ]; then
            export "$key=$val"
            from_file[$key]=1
        fi
    done < "$ENV_FILE"
}

if [ ! -f "$ENV_FILE" ]; then
    die "$ENV_FILE не найден. Создайте его: cp .env.example .env (прод-шаблон) и заполните (см. DEPLOY_NOTES.md, docs/LAUNCH_CHECKLIST.md)."
fi
load_env

dc() { docker compose --env-file "$ENV_FILE" "$@"; }
# Для scripts/backup.sh и restore.sh: тот же env-файл (файлы и имя проекта берутся из COMPOSE_FILE / COMPOSE_PROJECT_NAME).
export COMPOSE_CMD="docker compose --env-file $ENV_FILE"

is_true() { [[ "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" =~ ^(true|1|yes)$ ]]; }

require_var() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        die "$name не задан. Добавьте его в $ENV_FILE перед деплоем."
    fi
}

# ─── Проверки ────────────────────────────────────────────────────────────────
detect_platform() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64 | amd64) PLATFORM="linux/amd64" ;;
        aarch64 | arm64) PLATFORM="linux/arm64" ;;
        *) die "архитектура '$arch' не поддерживается (нужны x86_64 или aarch64/arm64)." ;;
    esac
    export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-$PLATFORM}"
    log "Архитектура $arch, платформа образов $DOCKER_DEFAULT_PLATFORM."
}

check_docker() {
    command -v docker > /dev/null 2>&1 || die "docker не найден. Установите Docker Engine (scripts/server-setup.sh или DEPLOY_NOTES.md)."
    docker compose version > /dev/null 2>&1 || die "нужен Docker Compose v2 (команда 'docker compose')."
    docker info > /dev/null 2>&1 || die "нет доступа к Docker: демон не запущен или пользователь не в группе docker."
}

preflight() {
    require_var SECRET_KEY
    require_var POSTGRES_PASSWORD
    require_var DATABASE_URL
    require_var DOMAIN

    # Страховка от копипасты из шаблонов.
    if grep -qi "REPLACE" <<< "$SECRET_KEY"; then
        echo "ERROR: SECRET_KEY looks like a placeholder (contains 'REPLACE')." >&2
        echo "       Generate a real key:" >&2
        echo "       python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\"" >&2
        exit 1
    fi
    if grep -qiE "local-docker-dev|django-insecure" <<< "$SECRET_KEY"; then
        die "SECRET_KEY is a dev fallback (local-docker-dev / django-insecure) - do not use on prod."
    fi
    if grep -qiE "^(autoforyou_dev_pass|autopass123|password|changeme)$" <<< "$POSTGRES_PASSWORD"; then
        die "POSTGRES_PASSWORD is a known dev/placeholder value - change it before deploying."
    fi
    if grep -q "host.docker.internal" <<< "$DATABASE_URL"; then
        die "DATABASE_URL still points to host.docker.internal - update to db:5432 for Docker deployment."
    fi
    if grep -q '<[A-Za-z_]*>' <<< "$DATABASE_URL ${REDIS_URL:-}"; then
        die "DATABASE_URL или REDIS_URL содержит заглушку вида <POSTGRES_PASSWORD> - подставьте реальный пароль."
    fi

    # DEBUG=true в проде отключает SECURE_*-заголовки, показывает трейсбеки и переводит Celery в синхронный режим.
    if is_true "${DEBUG:-false}"; then
        die "DEBUG is enabled. Set DEBUG=false in $ENV_FILE before deploying."
    fi
    # В паре с CORS_ALLOW_CREDENTIALS=true открытый CORS позволяет любому сайту обращаться к API от имени пользователя.
    if is_true "${CORS_ALLOW_ALL_ORIGINS:-false}"; then
        die "CORS_ALLOW_ALL_ORIGINS is enabled. Set it to false and list real origins in CORS_ALLOWED_ORIGINS."
    fi

    case "${TLS_MODE:-}" in
        off | external | selfsigned | letsencrypt) ;;
        *) die "TLS_MODE='${TLS_MODE:-}' не поддерживается (off, external, selfsigned, letsencrypt)." ;;
    esac
    if [ "$TLS_MODE" != "off" ] && [[ "${SITE_URL:-}" != https://* ]]; then
        die "TLS_MODE=$TLS_MODE, а SITE_URL='${SITE_URL:-}' не начинается с https://."
    fi

    # DOMAIN должен проходить ALLOWED_HOSTS: иначе Django отвечает 400 на все запросы (в том числе /healthz).
    local found=0 host
    local -a hosts
    IFS=',' read -r -a hosts <<< "${ALLOWED_HOSTS:-}"
    for host in "${hosts[@]}"; do
        host="${host//[[:space:]]/}"
        [ "$host" = "*" ] && die "ALLOWED_HOSTS содержит '*': подмена заголовка Host. Перечислите реальные домены."
        # Как в Django: '.example.test' покрывает example.test и любые поддомены.
        if [ "$host" = "$DOMAIN" ]; then found=1; fi
        if [[ "$host" == .* ]] && { [ "${host#.}" = "$DOMAIN" ] || [[ "$DOMAIN" == *"$host" ]]; }; then found=1; fi
    done
    [ "$found" = 1 ] || die "ALLOWED_HOSTS ('${ALLOWED_HOSTS:-}') не содержит DOMAIN ($DOMAIN)."

    # Замороженные модули (ВОЛНА-1): в проде они должны быть выключены. Предупреждение, не ошибка.
    local flag
    for flag in LOTS_ENABLED B2B_ENABLED DEALERS_ENABLED SHIPMENTS_ENABLED VIN_REPORTS_ENABLED; do
        if is_true "${!flag:-false}"; then
            warn "$flag=true при DEBUG=false: модуль заморожен по плану запуска. Это сделано осознанно?"
        fi
    done

    if [ "$DO_E2E" = 1 ] && ! command -v npx > /dev/null 2>&1; then
        die "--smoke-e2e требует node/npx (и 'npm ci' в frontend/). Без них проверяйте smoke через curl (он выполняется всегда)."
    fi

    detect_platform
    check_docker
    # Пустые обязательные переменные compose (REDIS_PASSWORD, NEXT_PUBLIC_*) падают здесь, до бэкапа и сборки.
    dc config --quiet || die "docker compose config не прошёл: проверьте переменные в $ENV_FILE."
    log "Проверки пройдены."
}

# ─── Состояние тегов ─────────────────────────────────────────────────────────
# Тег попадает в команды docker: читаем только git sha или 'local'.
read_state() {
    local v=""
    if [ -s "$STATE_DIR/$1" ]; then v="$(tr -d '[:space:]' < "$STATE_DIR/$1")"; fi
    if [ -n "$v" ] && ! [[ "$v" =~ ^([0-9a-f]{7,40}|local)$ ]]; then
        die "$STATE_DIR/$1 повреждён (ожидался git sha, получено '$v'). Удалите файл вручную."
    fi
    printf '%s' "$v"
}
write_state() { (umask 077 && mkdir -p "$STATE_DIR" && printf '%s\n' "$2" > "$STATE_DIR/$1"); }

# ─── Шаги ────────────────────────────────────────────────────────────────────
do_pull() {
    log "git pull --ff-only"
    git pull --ff-only
}

LAST_DUMP=""
do_backup() {
    if [ "$SKIP_BACKUP" = 1 ]; then
        warn "бэкап пропущен (--skip-backup)."
        return 0
    fi
    if [ -z "$(dc ps -q db 2> /dev/null || true)" ]; then
        log "Контейнер БД ещё не создан (первый запуск) - бэкапить нечего."
        return 0
    fi
    log "Бэкап перед деплоем: scripts/backup.sh --now"
    ./scripts/backup.sh --now || die "бэкап не удался, деплой отменён (--skip-backup пропускает бэкап осознанно)."
    local dir="${BACKUP_DIR:-./backups}"
    LAST_DUMP="$(find "$dir" -maxdepth 1 -name 'autoforyou_*.dump' 2> /dev/null | sort | tail -n 1 || true)"
    if [ -n "$LAST_DUMP" ]; then
        log "Дамп перед деплоем: $LAST_DUMP (для отката данных: ./scripts/restore.sh $LAST_DUMP)"
    fi
}

up_stack() { # $1 = тег; $2 = --build или пусто
    local tag="$1" build="${2:-}"
    local -a args=(up -d --wait --wait-timeout "$WAIT_TIMEOUT")
    [ -n "$build" ] && args+=(--build)
    IMAGE_TAG="$tag" dc "${args[@]}" "${WAIT_SERVICES[@]}" || return 1
    # Остальные сервисы (bot, backup, mailpit в e2e): без --wait.
    IMAGE_TAG="$tag" dc up -d || return 1
    # nginx резолвит backend/frontend один раз при старте: у пересозданных контейнеров новые IP,
    # без reload он шлёт запросы на старые адреса и отдаёт 503 (проверено повторным деплоем).
    log "Перечитываю адреса upstream: nginx -s reload"
    IMAGE_TAG="$tag" dc exec -T nginx nginx -s reload || return 1
}

# Каждый деплой оставляет образы со своим тегом (~1,5 ГБ на тег): храним только текущий и предыдущий
# (нужен для --rollback), остальные теги и висячие слои удаляем, чтобы диск сервера не заполнялся.
prune_old_tags() {
    local prev ref tag
    prev="$(read_state previous_tag)"
    log "Удаляю старые теги образов (оставляю $TAG${prev:+ и $prev})"
    docker image ls --format '{{.Repository}}:{{.Tag}}' |
        grep -E '^autoforyou-[a-z_]+:[0-9a-f]{7,40}$' |
        while read -r ref; do
            tag="${ref##*:}"
            if [ "$tag" = "$TAG" ] || [ "$tag" = "$prev" ]; then continue; fi
            docker image rm "$ref" > /dev/null 2>&1 || warn "не удалось удалить $ref (занят контейнером?)"
        done
    docker image prune -f > /dev/null || warn "docker image prune не выполнился"
}

smoke_check() { # $1 = путь
    local path="$1" i code
    for ((i = 1; i <= SMOKE_RETRIES; i++)); do
        code="$(curl -s "${SMOKE_CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' -m 10 --resolve "$SMOKE_HOST:$SMOKE_PORT:127.0.0.1" "$SMOKE_SCHEME://$SMOKE_HOST:$SMOKE_PORT$path" || true)"
        if [ "$code" = "200" ]; then return 0; fi
        # За внешним балансировщиком запрос с самого сервера не доверенный: Django может ответить редиректом на https.
        if [ "${TLS_MODE:-}" = "external" ] && [[ "$code" =~ ^30[1278]$ ]]; then return 0; fi
        sleep "$SMOKE_SLEEP"
    done
    echo "[deploy] smoke: $SMOKE_SCHEME://$SMOKE_HOST:$SMOKE_PORT$path отвечает '$code', ожидался 200" >&2
    return 1
}

smoke() {
    # Проверяем локальный nginx и имя сайта из DOMAIN/SITE_URL через --resolve: результат не зависит от DNS и Cloudflare.
    if [ "$TLS_MODE" = "selfsigned" ] || [ "$TLS_MODE" = "letsencrypt" ]; then
        SMOKE_SCHEME="https"
        SMOKE_HOST="${SITE_URL#*://}"
        SMOKE_HOST="${SMOKE_HOST%%/*}"
        SMOKE_HOST="${SMOKE_HOST%%:*}"
        SMOKE_PORT="${NGINX_HTTPS_PORT:-443}"
    else
        SMOKE_SCHEME="http"
        SMOKE_HOST="$DOMAIN"
        SMOKE_PORT="${NGINX_PORT:-80}"
    fi
    # Проверка сертификата отключается только для selfsigned и для временного сертификата letsencrypt до init-letsencrypt.sh.
    SMOKE_CURL_OPTS=()
    if [ "$TLS_MODE" = "selfsigned" ]; then
        SMOKE_CURL_OPTS=(-k)
    elif [ "$TLS_MODE" = "letsencrypt" ] && dc exec -T nginx sh -c "[ -e /etc/letsencrypt/live/$DOMAIN/.dummy ]" > /dev/null 2>&1; then
        warn "у nginx временный сертификат (init-letsencrypt.sh ещё не выполнен): проверка сертификата в smoke отключена."
        SMOKE_CURL_OPTS=(-k)
    fi
    log "Smoke: $SMOKE_SCHEME://$SMOKE_HOST:$SMOKE_PORT (через 127.0.0.1) /healthz и /"
    smoke_check /healthz && smoke_check /
}

smoke_e2e() {
    log "Playwright @smoke против $SMOKE_SCHEME://$SMOKE_HOST"
    local base="$SMOKE_SCHEME://$SMOKE_HOST"
    if [ "$SMOKE_SCHEME" = "https" ] && [ "$SMOKE_PORT" != "443" ]; then base="$base:$SMOKE_PORT"; fi
    if [ "$SMOKE_SCHEME" = "http" ] && [ "$SMOKE_PORT" != "80" ]; then base="$base:$SMOKE_PORT"; fi
    (cd frontend && E2E_BASE_URL="$base" E2E_ALLOW_REMOTE=1 npx playwright test --project=smoke --grep @smoke)
}

images_exist() { # $1 = тег
    docker image inspect "autoforyou-backend:$1" "autoforyou-frontend:$1" > /dev/null 2>&1
}

# Поднимает образы с тегом $1. Миграции БД автоматически не откатываются.
roll_to() {
    local tag="$1"
    images_exist "$tag" || die "образы с тегом '$tag' не найдены локально (docker image ls autoforyou-backend); откат невозможен."
    log "Поднимаю образы с тегом $tag"
    up_stack "$tag" "" || die "не удалось поднять образы $tag."
}

rollback_notice() {
    warn "миграции БД автоматически НЕ откатываются. Если новая миграция уже применена, а старому коду она не подходит,"
    warn "верните данные: ./scripts/restore.sh ${LAST_DUMP:-<дамп из backups/>}  (правило совместимых миграций - DEPLOY_NOTES.md)."
}

manual_rollback() {
    local prev cur
    prev="$(read_state previous_tag)"
    cur="$(read_state current_tag)"
    [ -n "$prev" ] || die "нет $STATE_DIR/previous_tag: откатываться некуда (предыдущего деплоя этим скриптом не было)."
    roll_to "$prev"
    # Меняем местами, чтобы повторный --rollback вернул обратно.
    write_state current_tag "$prev"
    [ -n "$cur" ] && write_state previous_tag "$cur"
    rollback_notice
    log "Откат на $prev выполнен."
}

# ─── Основной сценарий ───────────────────────────────────────────────────────
preflight

if [ "$DO_ROLLBACK" = 1 ]; then
    manual_rollback
    exit 0
fi

[ "$DO_PULL" = 1 ] && do_pull

# CI передаёт SHA коммита, прошедшего проверки: на сервере должен оказаться именно он (не более новый и не чужой).
if [ -n "${EXPECTED_SHA:-}" ]; then
    [[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || die "EXPECTED_SHA должен быть полным git sha (40 hex-символов)."
    HEAD_SHA="$(git rev-parse HEAD 2> /dev/null || true)"
    if [ "$HEAD_SHA" != "$EXPECTED_SHA" ]; then
        die "на сервере не тот коммит, что прошёл CI (на сервере ${HEAD_SHA:-неизвестно}, ожидался $EXPECTED_SHA). Деплой отменён; для новейшего коммита запустите workflow заново."
    fi
fi

TAG="$(git rev-parse --short HEAD 2> /dev/null || true)"
[ -n "$TAG" ] || die "не удалось определить git-коммит для IMAGE_TAG (запускайте из клона репозитория)."
CURRENT="$(read_state current_tag)"

# Cloudflare: обновить диапазоны IP перед запуском; nginx перечитает файл при перезапуске.
CF_CHANGED=0
if is_true "${CLOUDFLARE_PROXY:-false}"; then
    before="$(cksum nginx/cloudflare-ips.conf 2> /dev/null || true)"
    log "CLOUDFLARE_PROXY=true: scripts/update-cloudflare-ips.sh"
    ./scripts/update-cloudflare-ips.sh
    [ "$(cksum nginx/cloudflare-ips.conf 2> /dev/null || true)" != "$before" ] && CF_CHANGED=1
fi

do_backup

log "Деплой тега $TAG (сейчас работает: ${CURRENT:-нет})"
BUILD_ARG=""
[ "$DO_BUILD" = 1 ] && BUILD_ARG="--build"

fail_deploy() {
    echo "ERROR: $1" >&2
    PREV="$(read_state previous_tag)"
    if [ -n "$CURRENT" ] && [ "$CURRENT" != "$TAG" ]; then PREV="$CURRENT"; fi
    if [ -z "$PREV" ]; then
        warn "предыдущих образов нет (первый деплой) - откатываться некуда. Логи: docker compose logs --tail 100"
    else
        warn "автоматический откат на $PREV"
        if images_exist "$PREV" && up_stack "$PREV" ""; then
            log "Откат на $PREV выполнен."
        else
            warn "откат на $PREV не удался. Смотрите: docker compose ps; docker compose logs --tail 100"
        fi
        rollback_notice
    fi
    exit 1
}

# Запоминаем предыдущий тег до запуска (нужен и автоматическому, и ручному откату).
if [ -n "$CURRENT" ] && [ "$CURRENT" != "$TAG" ]; then write_state previous_tag "$CURRENT"; fi

up_stack "$TAG" "$BUILD_ARG" || fail_deploy "docker compose up --wait не дождался healthy-сервисов."
[ "$CF_CHANGED" = 1 ] && { log "Диапазоны Cloudflare изменились - перезапуск nginx."; dc restart nginx; }
smoke || fail_deploy "smoke-проверка не прошла."
if [ "$DO_E2E" = 1 ]; then
    smoke_e2e || fail_deploy "Playwright @smoke не прошёл."
fi

write_state current_tag "$TAG"
prune_old_tags
log "Готово. Работает тег $TAG."
dc ps
