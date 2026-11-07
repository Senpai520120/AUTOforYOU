#!/usr/bin/env bash
# e2e-run.sh - один прогон Playwright на e2e-стеке одной командой (задача 9.58).
#
# Делает по порядку:
#   1. сверяет ключи .env.e2e с .env.e2e.example (печатает только ИМЕНА недостающих ключей, не значения);
#   2. останавливает dev-стек: `docker compose down` БЕЗ -v (тома dev-стека не трогаются никогда);
#   3. поднимает e2e-стек (`up -d --build`) и ждёт, пока сервисы станут healthy;
#   4. сбрасывает Redis (FLUSHALL) и засевает данные (`manage.py e2e_seed`);
#   5. запускает Playwright из frontend/ с вашими аргументами; E2E_PASSWORD берётся из .env.e2e и не печатается;
#   6. ВСЕГДА, даже после падения: `scripts/e2e-cleanup.sh` и `docker compose up -d --scale bot=0` (dev-стек обратно).
# Код возврата = код Playwright (2 - не хватает ключей в .env.e2e, 1 - стек не поднялся).
#
# Примеры:
#   ./scripts/e2e-run.sh                                   # весь набор
#   ./scripts/e2e-run.sh e2e/lead.spec.ts --project=chromium
#   ./scripts/e2e-run.sh --grep @smoke
# Один раз: cp .env.e2e.example .env.e2e (и впишите SECRET_KEY). Из PowerShell: scripts\e2e-run.ps1.

ENV_FILE=.env.e2e
EXAMPLE_FILE=.env.e2e.example
STACK=(docker compose -p autoforyou-e2e --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml)

log() { echo "[e2e-run] $*"; }

# Имена ключей KEY=... (без комментариев и пустых строк), по одному в строке, без значений.
env_keys() { sed -n 's/^[[:space:]]*\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' "$1" | sort -u; }

# check_env_keys <env> <example>: 0 - все ключи шаблона есть; 2 - есть недостающие (печатаются только имена);
# 1 - нет файла. Лишние ключи в .env.e2e не мешают. Значения нигде не выводятся.
check_env_keys() {
    local env_file=$1 example=$2
    [ -f "$example" ] || { echo "Нет шаблона $example" >&2; return 1; }
    if [ ! -f "$env_file" ]; then
        echo "Нет файла $env_file. Создайте: cp $example $env_file (и впишите SECRET_KEY)" >&2
        return 1
    fi
    local missing
    missing=$(comm -23 <(env_keys "$example") <(env_keys "$env_file") | paste -sd, - | sed 's/,/, /g')
    if [ -n "$missing" ]; then
        echo "В $env_file нет ключей из $example: $missing" >&2
        echo "Добавьте их строками KEY=значение из шаблона (значения по умолчанию - в $example)." >&2
        return 2
    fi
    return 0
}

wait_healthy() {
    local deadline=$((SECONDS + 420)) svc state
    for svc in backend frontend nginx; do
        while :; do
            state=$(docker inspect -f '{{.State.Health.Status}}' "autoforyou-e2e-$svc-1" 2> /dev/null || echo missing)
            [ "$state" = healthy ] && break
            if [ "$SECONDS" -ge "$deadline" ]; then
                log "Сервис $svc не стал healthy (состояние: $state)"
                return 1
            fi
            sleep 4
        done
    done
}

restore() {
    local rc=$?
    log "Очистка e2e-стека и возврат dev-стека (без -v)"
    bash scripts/e2e-cleanup.sh || log "e2e-cleanup.sh завершился с ошибкой (код $?)"
    docker compose up -d --scale bot=0 || log "Не удалось поднять dev-стек: docker compose up -d --scale bot=0"
    exit "$rc"
}

main() {
    cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
    check_env_keys "$ENV_FILE" "$EXAMPLE_FILE" || exit $?
    trap restore EXIT

    log "Останавливаю dev-стек (docker compose down, без -v)"
    docker compose down || { log "Не удалось остановить dev-стек"; exit 1; }
    log "Поднимаю e2e-стек"
    "${STACK[@]}" up -d --build || { log "Не удалось поднять e2e-стек"; exit 1; }
    wait_healthy || exit 1

    log "FLUSHALL и e2e_seed"
    "${STACK[@]}" exec -T redis redis-cli FLUSHALL > /dev/null || { log "FLUSHALL не выполнен"; exit 1; }
    "${STACK[@]}" exec -T backend python manage.py e2e_seed > /dev/null || { log "e2e_seed не выполнен"; exit 1; }

    # Как читает Compose: без \r (CRLF) и без обрамляющих кавычек.
    E2E_PASSWORD=$(grep -E '^E2E_PASSWORD=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\r' | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\\(.*\\)'\$/\\1/")
    export E2E_PASSWORD
    log "Playwright: npx playwright test $*"
    (cd frontend && npx playwright test "$@")
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
