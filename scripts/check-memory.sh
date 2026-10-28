#!/usr/bin/env bash
# Проверка памяти контейнеров compose (задача 7.7a): ./scripts/check-memory.sh
# Снимает `docker stats --no-stream` по всем сервисам, печатает таблицу и завершается кодом 1, если
#   - любой контейнер занял больше MEM_ALERT_PERCENT процентов от своего mem_limit, или
#   - контейнер хотя бы раз убит по нехватке памяти (State.OOMKilled).
# Контейнер без mem_limit в проверке процентов не участвует (предупреждение), OOM проверяется всегда.
# Запускать под нагрузкой (после прогона Playwright) и вручную после открытия сайта: порог - сигнал, что пора
# поднять MEM_LIMIT_* в .env или тариф сервера. Коды: 0 - в норме, 1 - превышение или OOM, 2 - ошибка запуска.
# MEM_ALERT_PERCENT берётся из окружения, иначе из строки MEM_ALERT_PERCENT= файла ENV_FILE (по умолчанию .env),
# иначе 85. Нестандартный compose (CI): COMPOSE_CMD="docker compose -p имя --env-file .env.e2e -f ...".
set -euo pipefail

# ПРОВЕРИТЬ: порог 85% - стартовое значение; уточнить по замеру на целевом сервере (CX23, 4 ГБ) под нагрузкой.
DEFAULT_ALERT_PERCENT=85

cd "$(dirname "${BASH_SOURCE[0]}")/.."
read -r -a DC <<< "${COMPOSE_CMD:-docker compose}"

threshold="${MEM_ALERT_PERCENT:-}"
env_file="${ENV_FILE:-.env}"
if [ -z "$threshold" ] && [ -r "$env_file" ]; then
    # Только одна строка, без выполнения файла; кавычки по краям снимаются.
    threshold=$(grep -E '^MEM_ALERT_PERCENT=' "$env_file" | tail -n 1 | cut -d= -f2- | tr -d '"'"'"' \r' || true)
fi
threshold="${threshold:-$DEFAULT_ALERT_PERCENT}"
if ! [[ "$threshold" =~ ^[0-9]+$ ]] || [ "$threshold" -lt 1 ] || [ "$threshold" -gt 100 ]; then
    echo "ОШИБКА: MEM_ALERT_PERCENT должен быть целым числом от 1 до 100, получено: $threshold" >&2
    exit 2
fi

mapfile -t ids < <("${DC[@]}" ps -q)
if [ "${#ids[@]}" -eq 0 ]; then
    echo "ОШИБКА: запущенных контейнеров compose не найдено (стек поднят?)" >&2
    exit 2
fi

stats=$(docker stats --no-stream --format '{{.ID}}|{{.MemUsage}}' "${ids[@]}")

# Размер вида "45.3MiB" / "1.2GiB" / "800kB" -> байты.
to_bytes() {
    awk -v s="$1" 'BEGIN {
        n = s + 0; u = s; sub(/^[0-9.]+/, "", u)
        m = 1
        if (u == "KiB") m = 1024; else if (u == "MiB") m = 1048576; else if (u == "GiB") m = 1073741824
        else if (u == "kB" || u == "KB") m = 1000; else if (u == "MB") m = 1000000; else if (u == "GB") m = 1000000000
        printf "%.0f", n * m
    }'
}

problems=0
printf '%-18s %12s %12s %7s  %s\n' СЕРВІС ВИКОРИСТАНО ЛІМІТ '%' СТАТУС
for id in "${ids[@]}"; do
    short="${id:0:12}"
    info=$(docker inspect -f '{{.HostConfig.Memory}}|{{.State.OOMKilled}}|{{index .Config.Labels "com.docker.compose.service"}}' "$id")
    limit="${info%%|*}"
    rest="${info#*|}"
    oom="${rest%%|*}"
    service="${rest#*|}"
    usage_raw=$(grep -F "$short|" <<< "$stats" | head -n 1 | cut -d'|' -f2 | cut -d'/' -f1 | tr -d ' ' || true)
    used=$(to_bytes "${usage_raw:-0B}")
    status="ok"
    percent="-"
    if [ "$limit" -gt 0 ]; then
        percent=$(awk -v u="$used" -v l="$limit" 'BEGIN { printf "%.0f", u * 100 / l }')
        if [ "$percent" -gt "$threshold" ]; then
            status="ПЕРЕВИЩЕННЯ (> ${threshold}%)"
            problems=$((problems + 1))
        fi
    else
        status="немає mem_limit"
    fi
    if [ "$oom" = "true" ]; then
        status="OOMKilled"
        problems=$((problems + 1))
    fi
    printf '%-18s %10sMB %10sMB %6s%%  %s\n' "$service" "$((used / 1048576))" "$((limit / 1048576))" "$percent" "$status"
done

if [ "$problems" -gt 0 ]; then
    echo "ПІДСУМОК: проблем: $problems. Підніміть MEM_LIMIT_* у .env або тариф сервера (див. docs/LAUNCH_CHECKLIST.md)." >&2
    exit 1
fi
echo "ПІДСУМОК: усі контейнери в межах ${threshold}% від mem_limit, OOM не було."
