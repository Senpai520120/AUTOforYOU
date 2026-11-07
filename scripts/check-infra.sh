#!/usr/bin/env bash
# Все проверки инфраструктуры одной командой: то же, что джоба infra-lint и шаг nginx -t в CI.
# Запуск: ./scripts/check-infra.sh [раздел ...]   без аргументов - все разделы.
# Разделы: lf shellcheck compose nginx shell-tests cloudflare
# Нужен Docker (кроме lf; shellcheck - если нет локального). На Windows (Git Bash) shell-тесты
# идут в ubuntu:24.04: NTFS не хранит права файлов, и test_deploy.sh там ложно падает.
# Код возврата 0 = все выбранные разделы прошли.
# shellcheck disable=SC2317  # функции check_* вызываются по имени раздела ("check_${s//-/_}")
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1
export MSYS_NO_PATHCONV=1   # Git Bash не переписывает пути внутри контейнеров
NGINX_IMAGE=nginx:1.31-alpine
SHELLCHECK_IMAGE=koalaman/shellcheck:v0.9.0
LINUX_IMAGE=ubuntu:24.04
ALL_SECTIONS="lf shellcheck compose nginx shell-tests cloudflare"

hostpath() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
is_windows() { case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) return 0;; *) return 1;; esac; }
need_docker() { docker info > /dev/null 2>&1 || { echo "Docker недоступен: запустите Docker Desktop" >&2; return 1; }; }

check_lf() {
    local bad=0
    git ls-files --eol -- '*.sh' | awk '$1 != "i/lf" {print; bad=1} END {exit bad}' || bad=1
    # -U: grep в Git Bash иначе срезает \r и CRLF не видит.
    if git ls-files -z '*.sh' | xargs -0 grep -lIU $'\r'; then echo "CRLF в *.sh" >&2; bad=1; fi
    return "$bad"
}

check_shellcheck() {
    # SC1007 исключён: `DATABASE_URL= REDIS_URL= cmd` в scripts/test-backend.sh - намеренное обнуление переменных.
    local files=(deploy.sh docker/*.sh docker/backup/*.sh scripts/*.sh scripts/tests/*.sh)
    if command -v shellcheck > /dev/null; then
        shellcheck -e SC1007 "${files[@]}"
    else
        need_docker || return 1
        docker run --rm -v "$(hostpath "$ROOT"):/mnt:ro" -w /mnt "$SHELLCHECK_IMAGE" -e SC1007 "${files[@]}"
    fi
}

check_compose() {
    need_docker || return 1
    # docker-compose.yml требует .env и .env.e2e (required: true). Существующие файлы не трогаем,
    # недостающие создаём на время проверки и удаляем.
    local made_env=0 made_e2e=0 rc=0 empty
    # Пустой env-файл вместо /dev/null: docker compose на Windows не понимает /dev/null.
    empty=$(mktemp)
    [ -f .env ] || { : > .env; made_env=1; }
    [ -f .env.e2e ] || { cp .env.e2e.example .env.e2e; made_e2e=1; }
    (
        export POSTGRES_PASSWORD=x REDIS_PASSWORD=x NEXT_PUBLIC_API_URL=http://x NEXT_PUBLIC_SITE_URL=http://x
        docker compose --env-file "$(hostpath "$empty")" config --quiet &&
            docker compose --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml config --quiet
    ) || rc=1
    [ "$made_env" = 1 ] && rm -f .env
    [ "$made_e2e" = 1 ] && rm -f .env.e2e
    rm -f "$empty"
    return "$rc"
}

# nginx из шаблонов: setup-скрипт и команда после него. Аргументы - переменные окружения, последний - команда.
# Вывод (предупреждения setup-скрипта) показывается только при ошибке.
nginx_run() {
    local envs=() cmd out rc
    while [ $# -gt 1 ]; do envs+=(-e "$1"); shift; done
    cmd=$1
    out=$(docker run --rm --add-host backend:127.0.0.1 --add-host frontend:127.0.0.1 \
        -v "$(hostpath "$ROOT/nginx"):/nginx-src:ro" -e DOMAIN=ci.example.test "${envs[@]}" \
        "$NGINX_IMAGE" sh -c ". /nginx-src/docker-entrypoint.d/15-afy-nginx-setup.sh && $cmd" 2>&1); rc=$?
    [ "$rc" = 0 ] || printf '%s\n' "$out" | grep -v 'ВНИМАНИЕ' | tail -5 >&2
    return "$rc"
}

check_nginx() {
    need_docker || return 1
    local bad=0 mode
    for mode in off external selfsigned letsencrypt; do
        nginx_run TLS_MODE="$mode" TRUSTED_PROXY_IPS=10.0.0.0/8 'nginx -t' || { echo "nginx -t: TLS_MODE=$mode" >&2; bad=1; }
    done
    # CAPTCHA_PROVIDER=turnstile: домен Turnstile сам попадает в CSP (иначе капча не загрузится).
    nginx_run TLS_MODE=off CAPTCHA_PROVIDER=turnstile 'grep -rq challenges.cloudflare.com /etc/nginx/' \
        || { echo "Turnstile не попал в CSP" >&2; bad=1; }
    # Аналитика (3.5): домены GA4 и Cloudflare WA - в CSP только при заданных ID и только корректных.
    nginx_run TLS_MODE=off GA4_MEASUREMENT_ID=G-TEST000000 CLOUDFLARE_ANALYTICS_TOKEN=CFTEST0000000000 \
        'nginx -t && grep -rq www.googletagmanager.com /etc/nginx/ && grep -rq static.cloudflareinsights.com /etc/nginx/' \
        || { echo "GA4/Cloudflare WA не попали в CSP" >&2; bad=1; }
    nginx_run TLS_MODE=off '! grep -rqE "googletagmanager|google-analytics|cloudflareinsights" /etc/nginx/' \
        || { echo "домены аналитики в CSP без ID" >&2; bad=1; }
    nginx_run TLS_MODE=off 'GA4_MEASUREMENT_ID=G-"><script>' '! grep -rqE "googletagmanager|google-analytics" /etc/nginx/' \
        || { echo "некорректный GA4_MEASUREMENT_ID попал в CSP" >&2; bad=1; }
    # Cloudflare без файла диапазонов: nginx обязан не стартовать.
    if nginx_run CLOUDFLARE_PROXY=true 'true' 2> /dev/null; then
        echo "CLOUDFLARE_PROXY=true без файла диапазонов должен падать" >&2; bad=1
    fi
    return "$bad"
}

# Запускает тест, показывает только провалы (весь вывод - если тест упал без строк FAIL).
run_quiet() {
    local out rc
    out=$("$@" 2>&1); rc=$?
    if [ "$rc" != 0 ]; then
        grep -E '^FAIL|Провалено' <<< "$out" || tail -20 <<< "$out"
    fi
    return "$rc"
}

check_shell_tests() {
    local bad=0 t
    for t in test_backup_rotation test_deploy test_check_memory test_e2e_run; do
        echo "-- $t"
        if is_windows; then
            need_docker || return 1
            run_quiet docker run --rm -v "$(hostpath "$ROOT"):/repo:ro" -w /repo "$LINUX_IMAGE" bash "scripts/tests/$t.sh" || bad=1
        else
            run_quiet "scripts/tests/$t.sh" || bad=1
        fi
    done
    return "$bad"
}

check_cloudflare() {
    need_docker || return 1
    run_quiet bash scripts/tests/test_cloudflare_realip.sh
}

sections=("$@")
[ ${#sections[@]} -gt 0 ] || read -r -a sections <<< "$ALL_SECTIONS"
results=() failed=0
for s in "${sections[@]}"; do
    case " $ALL_SECTIONS " in *" $s "*) ;; *) echo "Неизвестный раздел: $s (есть: $ALL_SECTIONS)" >&2; exit 2;; esac
    echo "=== $s"
    start=$SECONDS
    if "check_${s//-/_}"; then
        results+=("ok   $s ($((SECONDS - start)) с)")
    else
        results+=("FAIL $s ($((SECONDS - start)) с)"); failed=1
    fi
done
echo "=== Итог"
printf '%s\n' "${results[@]}"
exit "$failed"
