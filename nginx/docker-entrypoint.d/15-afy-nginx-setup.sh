#!/bin/sh
# Подготовка конфигурации nginx по .env (задача 7.1). Запускается из entrypoint в docker-compose.yml
# (через `.`, не через /docker-entrypoint.d, чтобы не зависеть от бита исполнения на Windows).
# Выбирает серверные блоки по TLS_MODE, собирает CSP и HSTS, генерирует сертификаты
# (selfsigned и временный для первого запуска letsencrypt). Любая ошибка настроек - остановка.
set -eu
SRC="${NGINX_SRC:-/nginx-src}"
GEN="${NGINX_GEN:-/etc/nginx/generated}"
CONF_OUT="${NGINX_CONF_OUT:-/etc/nginx/conf.d/default.conf}"

NL="$(printf '\nx')"; NL="${NL%x}"
CR="$(printf '\r')"

fail() { echo "[afy-nginx] ОШИБКА: $*" >&2; exit 1; }
need_chars() { # имя значение regex
    # grep проверяет построчно: многострочное значение (перевод строки) отвергаем заранее.
    case "$2" in *"$NL"*|*"$CR"*) fail "значение $1 содержит перевод строки";; esac
    printf '%s\n' "$2" | grep -Eq "$3" || fail "значение $1 содержит недопустимые символы или формат"
}

DOMAIN="${DOMAIN:-}"
[ -n "$DOMAIN" ] || fail "DOMAIN не задан (.env)"
need_chars DOMAIN "$DOMAIN" '^[A-Za-z0-9.-]+$'
TLS_MODE="${TLS_MODE:-off}"
case "$TLS_MODE" in off|selfsigned|letsencrypt|external) ;; *) fail "TLS_MODE=$TLS_MODE не поддерживается (off, selfsigned, letsencrypt, external)";; esac

NGINX_MAX_BODY_SIZE="${NGINX_MAX_BODY_SIZE:-20M}"
need_chars NGINX_MAX_BODY_SIZE "$NGINX_MAX_BODY_SIZE" '^[0-9]+[kKmMgG]?$'
NGINX_AUTH_RATE="${NGINX_AUTH_RATE:-20r/m}"
need_chars NGINX_AUTH_RATE "$NGINX_AUTH_RATE" '^[0-9]+r/[ms]$'
INTERNAL_HOST="${INTERNAL_HOST:-nginx}"
need_chars INTERNAL_HOST "$INTERNAL_HOST" '^[A-Za-z0-9.-]+$'

SERVER_NAMES="$DOMAIN"
DOMAIN_WWW="${DOMAIN_WWW:-false}"

# ─── CSP: базовая политика + *_EXTRA из .env (доменов провайдеров в коде нет, кроме Turnstile) ──
# В *_EXTRA допустимы только токены вида https://host[:port]: без `*` и голого `https:`.
for v in CSP_SCRIPT_SRC_EXTRA CSP_CONNECT_SRC_EXTRA CSP_FRAME_SRC_EXTRA CSP_IMG_SRC_EXTRA; do
    eval "val=\${$v:-}"
    need_chars "$v" "$val" '^[A-Za-z0-9 :/.-]*$'
    for tok in $val; do
        printf '%s\n' "$tok" | grep -Eq '^https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]+)?$' \
            || fail "$v: допустимы только значения вида https://host[:port], получено '$tok'"
    done
done
join() { # базовое-значение extra
    if [ -z "$1" ]; then printf '%s' "$2"; elif [ -n "$2" ]; then printf '%s %s' "$1" "$2"; else printf '%s' "$1"; fi
}
CSP_SCRIPT_SRC_EXTRA="${CSP_SCRIPT_SRC_EXTRA:-}"
CSP_FRAME_SRC_EXTRA="${CSP_FRAME_SRC_EXTRA:-}"
CSP_CONNECT_SRC_EXTRA="${CSP_CONNECT_SRC_EXTRA:-}"
CSP_IMG_SRC_EXTRA="${CSP_IMG_SRC_EXTRA:-}"
# Cloudflare Turnstile (CAPTCHA_PROVIDER=turnstile): скрипт и iframe виджета добавляются автоматически.
if [ "$(printf '%s' "${CAPTCHA_PROVIDER:-}" | tr 'A-Z' 'a-z')" = "turnstile" ]; then
    CSP_SCRIPT_SRC_EXTRA="$(join "$CSP_SCRIPT_SRC_EXTRA" "https://challenges.cloudflare.com")"
    CSP_FRAME_SRC_EXTRA="$(join "$CSP_FRAME_SRC_EXTRA" "https://challenges.cloudflare.com")"
fi
# Веб-аналитика (задача 3.5): домены добавляются только при заданном ID правильного формата
# (тот же шаблон, что в core/analytics.py). Без ID или с битым значением доменов в политике нет.
case "${GA4_MEASUREMENT_ID:-}${CLOUDFLARE_ANALYTICS_TOKEN:-}" in *"$NL"*|*"$CR"*) fail "GA4_MEASUREMENT_ID/CLOUDFLARE_ANALYTICS_TOKEN содержат перевод строки";; esac
if printf '%s\n' "${GA4_MEASUREMENT_ID:-}" | grep -Eq '^G-[A-Z0-9]{4,20}$'; then
    CSP_SCRIPT_SRC_EXTRA="$(join "$CSP_SCRIPT_SRC_EXTRA" "https://www.googletagmanager.com")"
    CSP_CONNECT_SRC_EXTRA="$(join "$CSP_CONNECT_SRC_EXTRA" "https://www.googletagmanager.com https://www.google-analytics.com https://*.google-analytics.com https://*.analytics.google.com")"
fi
if printf '%s\n' "${CLOUDFLARE_ANALYTICS_TOKEN:-}" | grep -Eq '^[A-Za-z0-9]{16,64}$'; then
    CSP_SCRIPT_SRC_EXTRA="$(join "$CSP_SCRIPT_SRC_EXTRA" "https://static.cloudflareinsights.com")"
    CSP_CONNECT_SRC_EXTRA="$(join "$CSP_CONNECT_SRC_EXTRA" "https://cloudflareinsights.com")"
fi
CSP_VALUE="default-src 'self'"
CSP_VALUE="$CSP_VALUE; script-src $(join "'self' 'unsafe-inline'" "$CSP_SCRIPT_SRC_EXTRA")"
CSP_VALUE="$CSP_VALUE; style-src 'self' 'unsafe-inline'"
CSP_VALUE="$CSP_VALUE; img-src $(join "'self' data: blob: https:" "$CSP_IMG_SRC_EXTRA")"
CSP_VALUE="$CSP_VALUE; font-src 'self' data:"
CSP_VALUE="$CSP_VALUE; connect-src $(join "'self'" "$CSP_CONNECT_SRC_EXTRA")"
if [ -n "$CSP_FRAME_SRC_EXTRA" ]; then CSP_VALUE="$CSP_VALUE; frame-src 'self' $CSP_FRAME_SRC_EXTRA"; fi
CSP_VALUE="$CSP_VALUE; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self' https://www.liqpay.ua"
CSP_HEADER_NAME="Content-Security-Policy"
if [ "${CSP_REPORT_ONLY:-false}" = "true" ]; then CSP_HEADER_NAME="Content-Security-Policy-Report-Only"; fi

# ─── HSTS (только по https; preload и subdomains - по флагам, 01-S18) ───────────
HSTS_MAX_AGE="${HSTS_MAX_AGE:-31536000}"
need_chars HSTS_MAX_AGE "$HSTS_MAX_AGE" '^[0-9]+$'
HSTS_VALUE="max-age=$HSTS_MAX_AGE"
if [ "${HSTS_INCLUDE_SUBDOMAINS:-false}" = "true" ]; then HSTS_VALUE="$HSTS_VALUE; includeSubDomains"; fi
if [ "${HSTS_PRELOAD:-false}" = "true" ]; then HSTS_VALUE="$HSTS_VALUE; preload"; fi
if [ "$HSTS_MAX_AGE" = "0" ]; then HSTS_VALUE=""; fi

# ─── Доверенные прокси (режим external) ──────────────────────────────────────────
# X-Forwarded-Proto и real_ip доверяются только адресам из TRUSTED_PROXY_IPS (и диапазонам Cloudflare
# при CLOUDFLARE_PROXY=true). Иначе любой клиент подделает схему, а limit_req станет общим на всех.
TRUSTED_LIST=""
if [ "$TLS_MODE" = "external" ]; then
    for ip in $(printf '%s' "${TRUSTED_PROXY_IPS:-}" | tr ',' ' '); do
        need_chars TRUSTED_PROXY_IPS "$ip" '^[0-9a-fA-F:./]+$'
        TRUSTED_LIST="$TRUSTED_LIST $ip"
    done
    if [ -z "$TRUSTED_LIST" ] && [ "${CLOUDFLARE_PROXY:-false}" != "true" ]; then
        fail "TLS_MODE=external требует TRUSTED_PROXY_IPS (адреса балансировщика через запятую, CIDR допустим) или CLOUDFLARE_PROXY=true"
    fi
fi

# ─── Cloudflare: диапазоны только из проверенного списка ──────────────────────────
CF_RANGES=""
if [ "${CLOUDFLARE_PROXY:-false}" = "true" ]; then
    CF_FILE="$SRC/cloudflare-ips.conf"
    if [ ! -s "$CF_FILE" ] || ! grep -q '^set_real_ip_from ' "$CF_FILE"; then
        fail "CLOUDFLARE_PROXY=true, но $CF_FILE пуст или отсутствует. Запустите scripts/update-cloudflare-ips.sh"
    fi
    if grep -Ev '^(set_real_ip_from [0-9a-fA-F:./]+;|#.*|[[:space:]]*)$' "$CF_FILE" >/dev/null; then
        fail "cloudflare-ips.conf содержит строки, кроме set_real_ip_from и комментариев"
    fi
    CF_RANGES="$(grep '^set_real_ip_from ' "$CF_FILE" | sed 's/^set_real_ip_from //; s/;$//')"
fi

mkdir -p "$GEN"
rm -f "$GEN"/*

# Карта схемы для backend: за внешним балансировщиком берём его X-Forwarded-Proto (только http/https
# и только от доверенного адреса), иначе схему собственного соединения.
if [ "$TLS_MODE" = "external" ]; then
    {
        echo 'geo $realip_remote_addr $trusted_proxy {'
        echo '    default 0;'
        for ip in $TRUSTED_LIST $CF_RANGES; do echo "    $ip 1;"; done
        echo '}'
        echo 'map "$trusted_proxy:$http_x_forwarded_proto" $forwarded_proto {'
        echo '    default     $scheme;'
        echo '    "1:https"   https;'
        echo '    "1:http"    http;'
        echo '}'
    } > "$GEN/proto-map.conf"
else
    cat > "$GEN/proto-map.conf" <<MAP
map \$scheme \$forwarded_proto {
    default  \$scheme;
}
MAP
fi
cat > "$GEN/hsts-map.conf" <<MAP
map \$forwarded_proto \$hsts_value {
    default  "";
    https    "$HSTS_VALUE";
}
MAP

# ─── real_ip: настоящий IP клиента только от доверенных адресов ───────────────────
if [ "${CLOUDFLARE_PROXY:-false}" = "true" ]; then
    {
        for ip in $CF_RANGES $TRUSTED_LIST; do echo "set_real_ip_from $ip;"; done
        echo "real_ip_header CF-Connecting-IP;"
        echo "real_ip_recursive off;"
    } > "$GEN/real-ip.conf"
elif [ -n "$TRUSTED_LIST" ]; then
    {
        for ip in $TRUSTED_LIST; do echo "set_real_ip_from $ip;"; done
        echo "real_ip_header X-Forwarded-For;"
        echo "real_ip_recursive on;"
    } > "$GEN/real-ip.conf"
else
    : > "$GEN/real-ip.conf"
fi

# ─── Админка: список разрешённых IP (C10). Пусто = открыта (ограничивает только limit_req) ──
: > "$GEN/admin-access.conf"
if [ -n "${ADMIN_ALLOWED_IPS:-}" ]; then
    for ip in $(printf '%s' "$ADMIN_ALLOWED_IPS" | tr ',' ' '); do
        need_chars ADMIN_ALLOWED_IPS "$ip" '^[0-9a-fA-F:./]+$'
        echo "allow $ip;" >> "$GEN/admin-access.conf"
    done
    echo "deny all;" >> "$GEN/admin-access.conf"
else
    echo "[afy-nginx] ВНИМАНИЕ: ADMIN_ALLOWED_IPS пуст, /admin/ открыт из интернета (защищён только limit_req)." >&2
fi

# ─── Сертификаты ───────────────────────────────────────────────────────────────
make_cert() { # каталог дней
    command -v openssl >/dev/null 2>&1 || apk add --no-cache openssl >/dev/null 2>&1 \
        || fail "нужен openssl для самоподписанного сертификата (образ без openssl и без доступа к apk)"
    mkdir -p "$1"
    openssl req -x509 -nodes -newkey rsa:2048 -days "$2" -subj "/CN=$DOMAIN" \
        -addext "subjectAltName=DNS:$DOMAIN,DNS:www.$DOMAIN" \
        -keyout "$1/privkey.pem" -out "$1/fullchain.pem" >/dev/null 2>&1 || fail "не удалось создать сертификат"
}
SSL_CERT_DIR=""
case "$TLS_MODE" in
    selfsigned)
        SSL_CERT_DIR=/etc/nginx/selfsigned
        if [ ! -s "$SSL_CERT_DIR/fullchain.pem" ]; then make_cert "$SSL_CERT_DIR" 365; fi
        ;;
    letsencrypt)
        SSL_CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
        if [ ! -s "$SSL_CERT_DIR/fullchain.pem" ]; then
            make_cert "$SSL_CERT_DIR" 30
            : > "$SSL_CERT_DIR/.dummy"   # метка временного сертификата для scripts/init-letsencrypt.sh
        fi
        # nginx читает сертификат один раз: перечитываем раз в 6 часов (certbot продлевает раз в 12).
        ( while :; do sleep 21600; nginx -s reload >/dev/null 2>&1 || true; done ) &
        ;;
esac

# ─── www -> основной домен (DOMAIN_WWW=true): 301 ───────────────────────────────────
: > "$GEN/www-redirect.conf"
if [ "$DOMAIN_WWW" = "true" ]; then
    if [ "$TLS_MODE" = "off" ] || [ "$TLS_MODE" = "external" ]; then
        cat > "$GEN/www-redirect.conf" <<WWW
server {
    listen 80;
    server_name www.$DOMAIN;
    return 301 \$forwarded_proto://$DOMAIN\$request_uri;
}
WWW
    else
        cat > "$GEN/www-redirect.conf" <<WWW
server {
    listen 443 ssl;
    http2 on;
    server_name www.$DOMAIN;
    ssl_certificate     $SSL_CERT_DIR/fullchain.pem;
    ssl_certificate_key $SSL_CERT_DIR/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    return 301 https://$DOMAIN\$request_uri;
}
WWW
    fi
fi

# ─── Рендер шаблонов (envsubst по белому списку: переменные nginx $host и т.п. не трогаются) ──
export DOMAIN SERVER_NAMES TLS_MODE NGINX_MAX_BODY_SIZE NGINX_AUTH_RATE INTERNAL_HOST \
       CSP_VALUE CSP_HEADER_NAME SSL_CERT_DIR
VARS='${DOMAIN} ${SERVER_NAMES} ${NGINX_MAX_BODY_SIZE} ${NGINX_AUTH_RATE} ${INTERNAL_HOST} ${CSP_VALUE} ${CSP_HEADER_NAME} ${SSL_CERT_DIR}'
render() { envsubst "$VARS" < "$SRC/templates/$1.template" > "$2"; }

render default.conf "$CONF_OUT"
render security-headers.conf "$GEN/security-headers.conf"
render security-headers-media.conf "$GEN/security-headers-media.conf"
render media-location.conf "$GEN/media-location.conf"
render locations.conf "$GEN/locations.conf"
if [ "$TLS_MODE" = "off" ] || [ "$TLS_MODE" = "external" ]; then
    render server-http.conf "$GEN/server-http.conf"
    printf 'include %s/server-http.conf;\ninclude %s/www-redirect.conf;\n' "$GEN" "$GEN" > "$GEN/active-servers.conf"
else
    render server-redirect.conf "$GEN/server-redirect.conf"
    render server-https.conf "$GEN/server-https.conf"
    printf 'include %s/server-redirect.conf;\ninclude %s/server-https.conf;\ninclude %s/www-redirect.conf;\n' \
        "$GEN" "$GEN" "$GEN" > "$GEN/active-servers.conf"
fi
echo "[afy-nginx] TLS_MODE=$TLS_MODE, DOMAIN=$DOMAIN, CSP=$CSP_HEADER_NAME"
