#!/bin/sh
# Обновляет nginx/cloudflare-ips.conf из официальных списков диапазонов Cloudflare (задача 7.1).
# ПРОВЕРИТЬ при выполнении: адреса списков по документации Cloudflare ("IP Ranges"),
# на момент написания это https://www.cloudflare.com/ips-v4 и https://www.cloudflare.com/ips-v6.
# Диапазоны не вшиваются в код "по памяти": файл формируется только из ответа Cloudflare.
# Запускать вручную раз в квартал и из deploy.sh (7.5), затем: docker compose restart nginx
set -eu

cd "$(dirname "$0")/.."
OUT=nginx/cloudflare-ips.conf
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

{
    echo "# Сгенерировано scripts/update-cloudflare-ips.sh $(date -u +%Y-%m-%dT%H:%MZ). Не править вручную."
    for url in https://www.cloudflare.com/ips-v4 https://www.cloudflare.com/ips-v6; do
        list="$(curl -fsS --max-time 20 "$url")" || { echo "Не удалось скачать $url" >&2; exit 1; }
        # Принимаем только строки-диапазоны, всё остальное - ошибка (защита от подмены ответа).
        printf '%s\n' "$list" | while IFS= read -r line; do
            line="$(printf '%s' "$line" | tr -d '\r')"
            [ -z "$line" ] && continue
            printf '%s\n' "$line" | grep -Eq '^[0-9a-fA-F:.]+/[0-9]+$' || { echo "Неожиданная строка: $line" >&2; exit 1; }
            echo "set_real_ip_from $line;"
        done
    done
} > "$TMP"

[ "$(grep -c '^set_real_ip_from ' "$TMP")" -ge 2 ] || { echo "Список диапазонов пуст, файл не обновлён" >&2; exit 1; }
mv "$TMP" "$OUT"
trap - EXIT
echo "Обновлено: $OUT ($(grep -c '^set_real_ip_from ' "$OUT") диапазонов)"
