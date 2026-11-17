#!/bin/sh
# Цикл ожидания BACKUP_TIME без cron-демона (задача 7.4). Часовой пояс - переменная TZ контейнера.
set -eu

log() { printf '%s [loop] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

time_of_day="${BACKUP_TIME:-03:30}"
case "$time_of_day" in
    [0-1][0-9]:[0-5][0-9] | 2[0-3]:[0-5][0-9]) ;;
    *) log "ОШИБКА: BACKUP_TIME='$time_of_day' - нужен формат ЧЧ:ММ (00:00-23:59)"; exit 2 ;;
esac

touch /tmp/backup_started
trap 'log "получен сигнал остановки"; exit 0' TERM INT

seconds_until_next() {
    now=$(date +%s)
    target=$(date -d "$(date +%Y-%m-%d) $time_of_day:00" +%s)
    if [ "$target" -le "$now" ]; then
        target=$((target + 86400))
    fi
    echo $((target - now))
}

run_backup() {
    # Ошибка бэкапа не должна ронять цикл: следующая попытка - в следующее окно, healthcheck покажет unhealthy.
    if /usr/local/bin/backup.sh; then
        log "бэкап завершён успешно"
    else
        log "ОШИБКА: бэкап завершился с ошибкой (см. строки выше)"
    fi
}

if [ "${BACKUP_ON_START:-false}" = "true" ]; then
    log "BACKUP_ON_START=true: бэкап сразу при старте"
    run_backup
fi

while :; do
    wait_s=$(seconds_until_next)
    log "следующий бэкап в $time_of_day (${TZ:-UTC}), через ${wait_s} с"
    sleep "$wait_s" &
    wait $!
    run_backup
    sleep 60   # защита от повторного запуска в ту же минуту
done
