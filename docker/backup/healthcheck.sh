#!/bin/sh
# Здоров, если последний успешный бэкап (метка .last_success) не старше 26 часов.
# Метки ещё нет (первый запуск) - отсчёт от старта контейнера (/tmp/backup_started), тоже 26 часов.
set -eu
dir="${BACKUP_DIR_IN_CONTAINER:-/backups}"
max_min=1560
if [ -f "$dir/.last_success" ]; then
    ref="$dir/.last_success"
elif [ -f /tmp/backup_started ]; then
    ref=/tmp/backup_started
else
    echo "нет ни метки успеха, ни метки старта" >&2
    exit 1
fi
if [ -n "$(find "$ref" -mmin "-$max_min" 2>/dev/null)" ]; then
    exit 0
fi
echo "последний успешный бэкап старше 26 часов" >&2
exit 1
