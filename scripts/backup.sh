#!/usr/bin/env bash
# Ручной бэкап Postgres (задача 7.4): ./scripts/backup.sh --now
# Запускает docker/backup/backup.sh одноразовым контейнером сервиса backup (тот же образ и настройки, что у ночного).
# Код возврата 0 - дамп создан и прошёл pg_restore --list (и, если настроено, отправлен вне сервера).
# Для нестандартного запуска compose (CI): COMPOSE_CMD="docker compose -p имя --env-file .env.e2e -f ...".
set -euo pipefail

usage() {
    echo "Использование: $0 --now" >&2
    echo "  --now   сделать бэкап прямо сейчас (дамп, медиа, шифрование и отправка, если настроены, ротация)" >&2
    exit 2
}

if [ "$#" -ne 1 ] || [ "$1" != "--now" ]; then
    usage
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
read -r -a DC <<< "${COMPOSE_CMD:-docker compose}"

"${DC[@]}" run --rm -T backup /usr/local/bin/backup.sh
