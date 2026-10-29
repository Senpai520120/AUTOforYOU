#!/bin/sh
# Ротация резервных копий (задача 7.4). Чистая функция без обращения к диску и сети:
#   rotate.sh plan KEEP_DAILY KEEP_WEEKLY KEEP_MONTHLY < метки
# Метки (YYYY-MM-DD_HHMM) читаются со stdin, на stdout идут метки, которые нужно УДАЛИТЬ.
# Хранится: KEEP_DAILY последних дней (из нескольких копий за день - самая поздняя),
# KEEP_WEEKLY последних воскресных и KEEP_MONTHLY копий за первое число месяца.
# Строки, не похожие на метку, игнорируются (ничего чужого не удаляем).
set -eu

usage() {
    echo "Использование: rotate.sh plan KEEP_DAILY KEEP_WEEKLY KEEP_MONTHLY < метки" >&2
    exit 2
}

if [ "$#" -ne 4 ] || [ "$1" != "plan" ]; then
    usage
fi
for n in "$2" "$3" "$4"; do
    case "$n" in
        '' | *[!0-9]*) echo "rotate.sh: срок хранения должен быть неотрицательным числом, получено '$n'" >&2; exit 2 ;;
    esac
done

grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}$' | sort -r | awk -v kd="$2" -v kw="$3" -v km="$4" '
{
    stamp = $0
    day = substr(stamp, 1, 10)
    if (day == prev_day) { print stamp; next }   # не последняя копия за этот день
    prev_day = day
    y = substr(day, 1, 4) + 0; m = substr(day, 6, 2) + 0; d = substr(day, 9, 2) + 0
    if (m < 3) { y -= 1; m += 12 }
    c = int(y / 100); yy = y % 100
    dow = (d + int(13 * (m + 1) / 5) + yy + int(yy / 4) + int(c / 4) + 5 * c) % 7   # 1 = воскресенье
    keep = 0
    if (nd < kd) { nd++; keep = 1 }
    if (dow == 1 && nw < kw) { nw++; keep = 1 }
    if (d == 1 && nm < km) { nm++; keep = 1 }
    if (!keep) print stamp
}'
