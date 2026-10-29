#!/usr/bin/env bash
# e2e-cleanup.sh - снять e2e-стек и освободить диск после прогона Playwright.
#
# Каждый `up --build` оставляет прежние слои образов «висячими» (~0,5 ГБ на сервис), поэтому
# после нескольких прогонов диск заполняется. Скрипт запускать после КАЖДОГО e2e-прогона.
#
# Удаляет: e2e-стек с томами; «висячие» образы; кэш сборки старше 7 дней; устаревшие образы
#          AUTOforYOU (старое именование autoforyou-e2e-*, :latest, теги деплоя с sha), которые
#          не используются контейнерами; frontend/test-results.
# Не трогает: контейнеры и тома dev-стека, образы с тегом :local (их использует dev-стек),
#          текущий и предыдущий теги деплоя (.deploy/), образы других проектов.
#
# Использование: ./scripts/e2e-cleanup.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

log() { echo "[e2e-cleanup] $*"; }

log "Занято до очистки:"
docker system df

# Compose требует обязательные переменные даже для down: без .env.e2e берём шаблон.
ENV_FILE=.env.e2e
[ -f "$ENV_FILE" ] || ENV_FILE=.env.e2e.example
log "Снимаю e2e-стек с томами (проект autoforyou-e2e)"
docker compose -p autoforyou-e2e --env-file "$ENV_FILE" \
    -f docker-compose.yml -f docker-compose.e2e.yml down -v --remove-orphans

# Теги деплоя, которые нужны для отката.
keep_tags=" local "
for f in .deploy/current_tag .deploy/previous_tag; do
    if [ -f "$f" ]; then keep_tags+="$(cat "$f") "; fi
done

log "Удаляю устаревшие образы AUTOforYOU (кроме тегов:${keep_tags}и используемых контейнерами)"
docker image ls --format '{{.Repository}}:{{.Tag}}' |
    grep -E '^autoforyou(-e2e)?-[a-z_]+:' |
    while read -r ref; do
        tag="${ref##*:}"
        if [[ "$keep_tags" == *" $tag "* ]]; then continue; fi
        # Занятый контейнером образ docker не удалит - это нормально.
        if docker image rm "$ref" > /dev/null 2>&1; then log "  удалён $ref"; fi
    done

log "Удаляю висячие образы и кэш сборки старше 7 дней"
docker image prune -f
docker builder prune -f --filter until=168h

rm -rf frontend/test-results

log "Занято после очистки:"
docker system df
