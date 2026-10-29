#!/bin/sh
# Первичное получение сертификата Let's Encrypt (задача 7.1). Запуск один раз после первого деплоя:
#   ./scripts/init-letsencrypt.sh
# Нужны в .env: DOMAIN, TLS_MODE=letsencrypt, LETSENCRYPT_EMAIL; опционально DOMAIN_WWW=true,
# LETSENCRYPT_STAGING=true (пробный запуск без лимитов Let's Encrypt).
# Порядок: nginx стартует с временным сертификатом (его создаёт сам nginx) -> certbot получает
# настоящий через webroot -> nginx перечитывает конфиг. Повторный запуск при настоящем
# сертификате ничего не меняет.
set -eu

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "Нет файла .env" >&2; exit 1; }
# Берём только нужные переменные, а не весь .env (в нём могут быть значения с пробелами).
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r"' || true; }
DOMAIN="$(env_get DOMAIN)"
TLS_MODE="$(env_get TLS_MODE)"
EMAIL="$(env_get LETSENCRYPT_EMAIL)"
WWW="$(env_get DOMAIN_WWW)"
STAGING="$(env_get LETSENCRYPT_STAGING)"

[ -n "$DOMAIN" ] || { echo "DOMAIN не задан в .env" >&2; exit 1; }
# DOMAIN попадает в `rm -rf` ниже: только буквы, цифры, точки и дефисы, без `..` и ведущей точки.
printf '%s
' "$DOMAIN" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9.-]*$' || { echo "DOMAIN содержит недопустимые символы" >&2; exit 1; }
case "$DOMAIN" in *..*) echo "DOMAIN не должен содержать '..'" >&2; exit 1;; esac
[ "$TLS_MODE" = "letsencrypt" ] || { echo "Нужен TLS_MODE=letsencrypt в .env (сейчас: '${TLS_MODE}')" >&2; exit 1; }
[ -n "$EMAIL" ] || { echo "LETSENCRYPT_EMAIL не задан в .env" >&2; exit 1; }

DC="docker compose --profile letsencrypt"

echo "==> Запуск nginx (временный сертификат создаётся автоматически)"
$DC up -d nginx

# Настоящий сертификат уже есть (нет метки .dummy) - ничего не делаем.
if $DC exec -T nginx sh -c "[ -s /etc/letsencrypt/live/$DOMAIN/fullchain.pem ] && [ ! -e /etc/letsencrypt/live/$DOMAIN/.dummy ]"; then
    echo "Сертификат для $DOMAIN уже получен, ничего не делаю."
    $DC up -d certbot
    exit 0
fi

DOMAINS="-d $DOMAIN"
[ "$WWW" = "true" ] && DOMAINS="$DOMAINS -d www.$DOMAIN"
STAGING_ARG=""
[ "$STAGING" = "true" ] && STAGING_ARG="--staging"

echo "==> Удаление временного сертификата"
$DC run --rm --entrypoint sh certbot -c \
    "rm -rf /etc/letsencrypt/live/$DOMAIN /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf"

echo "==> Запрос сертификата"
# shellcheck disable=SC2086
if ! $DC run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
        $DOMAINS --email "$EMAIL" --agree-tos --no-eff-email $STAGING_ARG; then
    echo "Не удалось получить сертификат. Проверьте DNS (A-запись на этот сервер) и открытые порты 80/443." >&2
    echo "Временный сертификат будет создан заново при перезапуске nginx: docker compose restart nginx" >&2
    exit 1
fi

echo "==> Перезагрузка nginx"
$DC restart nginx
$DC up -d certbot
echo "Готово. Проверка: curl -I https://$DOMAIN"
