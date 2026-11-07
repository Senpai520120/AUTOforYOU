#!/usr/bin/env bash
# Эхо-тест CLOUDFLARE_PROXY (задача 7.1): какой IP клиента nginx передаёт в backend.
# Настоящий nginx из nginx/templates + эхо-backend (отвечает полученными X-Forwarded-For и X-Real-IP)
# в отдельной сети Docker; клиент шлёт CF-Connecting-IP и поддельный X-Forwarded-For.
# Запуск: ./scripts/tests/test_cloudflare_realip.sh   Нужен Docker. Код возврата 0 = все проверки прошли.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
IMAGE=nginx:1.31-alpine
NET=afy-cf-realip-test
SUBNET=172.31.250.0/24
CLIENT_IP=172.31.250.50
FAKE_IP=198.51.100.7
export MSYS_NO_PATHCONV=1   # Git Bash на Windows не переписывает пути внутри контейнера
fails=0

ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }
contains() { if grep -qF -- "$3" <<< "$2"; then ok "$1"; else bad "$1 (нет '$3' в: $(head -c 300 <<< "$2"))"; fi; }
lacks() { if grep -qF -- "$3" <<< "$2"; then bad "$1 (есть '$3' в: $(head -c 300 <<< "$2"))"; else ok "$1"; fi; }
hostpath() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

TMP=$(mktemp -d "$ROOT/.cf-realip-test.XXXXXX")
cleanup() {
    docker rm -f afy-cf-nginx afy-cf-echo > /dev/null 2>&1 || true
    docker network rm "$NET" > /dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap cleanup EXIT
cleanup_containers() { docker rm -f afy-cf-nginx afy-cf-echo > /dev/null 2>&1 || true; }

docker network rm "$NET" > /dev/null 2>&1 || true
docker network create --subnet "$SUBNET" "$NET" > /dev/null

# Эхо-backend: один контейнер под именами backend и frontend (upstream'ы шаблона).
cat > "$TMP/echo.conf" <<'CONF'
server {
    listen 8000;
    listen 3000;
    default_type text/plain;
    location / { return 200 "xff=[$http_x_forwarded_for] real=[$http_x_real_ip]\n"; }
}
CONF

start_stack() { # $1 - содержимое cloudflare-ips.conf ("" = файла нет), дальше - переменные окружения nginx
    cleanup_containers
    docker run -d --name afy-cf-echo --network "$NET" --network-alias backend --network-alias frontend         -v "$(hostpath "$TMP/echo.conf"):/etc/nginx/conf.d/default.conf:ro" "$IMAGE" > /dev/null
    # Копия nginx/: файл диапазонов кладётся рядом с шаблонами, как его создаёт update-cloudflare-ips.sh.
    rm -rf "$TMP/nginx"
    cp -r "$ROOT/nginx" "$TMP/nginx"
    rm -f "$TMP/nginx/cloudflare-ips.conf"
    [ -n "$1" ] && printf '%s
' "$1" > "$TMP/nginx/cloudflare-ips.conf"
    shift
    local envs=(-e DOMAIN=localhost -e TLS_MODE=external)
    for e in "$@"; do envs+=(-e "$e"); done
    docker run -d --name afy-cf-nginx --network "$NET" --network-alias nginx         -v "$(hostpath "$TMP/nginx"):/nginx-src:ro" "${envs[@]}"         --entrypoint /bin/sh "$IMAGE" -c '. /nginx-src/docker-entrypoint.d/15-afy-nginx-setup.sh && exec nginx -g "daemon off;"' > /dev/null
    for _ in $(seq 1 30); do
        [ "$(docker inspect -f '{{.State.Running}}' afy-cf-nginx 2> /dev/null)" = "false" ] && return 1
        docker exec afy-cf-nginx wget -qO- http://127.0.0.1/api/ping > /dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

ask() { # путь [XFF] - ответ эхо-backend на запрос клиента с фиксированного IP
    docker run --rm --network "$NET" --ip "$CLIENT_IP" "$IMAGE"         wget -qO- --header "CF-Connecting-IP: $FAKE_IP" --header "X-Forwarded-For: ${2:-203.0.113.9}" "http://nginx$1"
}

CF=CLOUDFLARE_PROXY=true

echo "# 1. Источник в диапазоне Cloudflare: IP клиента берётся из CF-Connecting-IP"
if start_stack "set_real_ip_from $SUBNET;" "$CF"; then
    for path in /api/v1/echo /; do
        out=$(ask "$path")
        contains "$path: X-Forwarded-For = только CF-Connecting-IP" "$out" "xff=[$FAKE_IP] real="
        contains "$path: X-Real-IP = CF-Connecting-IP" "$out" "real=[$FAKE_IP]"
        lacks "$path: поддельный X-Forwarded-For клиента не передан" "$out" "203.0.113.9"
    done
else
    bad "nginx не стартовал с диапазоном Cloudflare: $(docker logs afy-cf-nginx 2>&1 | tail -5)"
fi

echo "# 2. Источник вне диапазонов Cloudflare: CF-Connecting-IP игнорируется (подделка)"
if start_stack "set_real_ip_from 203.0.113.0/24;" "$CF"; then
    for path in /api/v1/echo /; do
        out=$(ask "$path")
        contains "$path: X-Forwarded-For = адрес отправителя" "$out" "xff=[$CLIENT_IP] real="
        contains "$path: X-Real-IP = адрес отправителя" "$out" "real=[$CLIENT_IP]"
        lacks "$path: CF-Connecting-IP не принят" "$out" "$FAKE_IP"
    done
else
    bad "nginx не стартовал с чужим диапазоном: $(docker logs afy-cf-nginx 2>&1 | tail -5)"
fi

echo "# 3. CLOUDFLARE_PROXY=true без файла диапазонов: nginx не стартует с понятной ошибкой"
if start_stack "" "$CF"; then
    bad "nginx стартовал без cloudflare-ips.conf"
else
    contains "текст ошибки называет скрипт обновления" "$(docker logs afy-cf-nginx 2>&1)" "update-cloudflare-ips.sh"
fi

echo "# 4. Посторонняя строка в cloudflare-ips.conf: nginx не стартует"
if start_stack "$(printf 'set_real_ip_from %s;
real_ip_header X-Forwarded-For;' "$SUBNET")" "$CF"; then
    bad "nginx стартовал с посторонней директивой в cloudflare-ips.conf"
else
    contains "текст ошибки про посторонние строки" "$(docker logs afy-cf-nginx 2>&1)" "кроме set_real_ip_from"
fi

echo "# 5. CLOUDFLARE_PROXY=true вместе с TRUSTED_PROXY_IPS: nginx не стартует (балансировщик подставил бы CF-Connecting-IP)"
if start_stack "set_real_ip_from 203.0.113.0/24;" "$CF" "TRUSTED_PROXY_IPS=$SUBNET"; then
    bad "nginx стартовал с CLOUDFLARE_PROXY и TRUSTED_PROXY_IPS"
else
    contains "текст ошибки про несовместимость" "$(docker logs afy-cf-nginx 2>&1)" "вместе не поддерживаются"
fi

echo "# 6. Без Cloudflare, балансировщик в TRUSTED_PROXY_IPS: IP клиента - последний недоверенный адрес XFF"
if start_stack "" "TRUSTED_PROXY_IPS=$SUBNET"; then
    for path in /api/v1/echo /; do
        out=$(ask "$path" "6.6.6.6, 203.0.113.9")
        contains "$path: X-Forwarded-For = клиент балансировщика" "$out" "xff=[203.0.113.9] real="
        lacks "$path: подставленный клиентом префикс XFF отброшен" "$out" "6.6.6.6"
        lacks "$path: CF-Connecting-IP без Cloudflare не читается" "$out" "$FAKE_IP"
    done
else
    bad "nginx не стартовал с TRUSTED_PROXY_IPS: $(docker logs afy-cf-nginx 2>&1 | tail -5)"
fi

echo "# 7. Без Cloudflare, источник вне TRUSTED_PROXY_IPS: XFF клиента игнорируется"
if start_stack "" "TRUSTED_PROXY_IPS=10.0.0.0/8"; then
    out=$(ask /api/v1/echo "6.6.6.6")
    contains "API: X-Forwarded-For = адрес отправителя" "$out" "xff=[$CLIENT_IP] real="
    lacks "API: XFF клиента не принят" "$out" "6.6.6.6"
else
    bad "nginx не стартовал с чужим TRUSTED_PROXY_IPS: $(docker logs afy-cf-nginx 2>&1 | tail -5)"
fi

if [ "$fails" -gt 0 ]; then
    echo "Провалено проверок: $fails"
    exit 1
fi
echo "Все проверки прошли"
