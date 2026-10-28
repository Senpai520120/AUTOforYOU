#!/usr/bin/env bash
# Восстановление БД (и медиа) из бэкапа (задача 7.4).
#   ./scripts/restore.sh <файл.dump|файл.dump.gpg> [--media <архив.tar.gz>] [--yes]
# ЗАТИРАЕТ данные рабочей БД этого compose-проекта (pg_restore --clean). Поэтому: файл обязателен (умолчаний нет),
# нужно подтверждение (ввести имя проекта; --yes только для CI), перед затиранием делается страховочный дамп.
# Для проверки бэкапа БЕЗ риска для рабочей базы используйте ./scripts/backup-verify.sh.
# Нестандартный запуск compose (CI): COMPOSE_CMD="docker compose -p имя --env-file .env.e2e -f ...".
set -euo pipefail

usage() {
    echo "Использование: $0 <файл.dump|файл.dump.gpg> [--media <архив.tar.gz>] [--yes]" >&2
    exit 2
}

file=""
media=""
assume_yes=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes) assume_yes=1; shift ;;
        --media) [ "$#" -ge 2 ] || usage; media="$2"; shift 2 ;;
        -h | --help) usage ;;
        -*) echo "Неизвестный параметр: $1" >&2; usage ;;
        *) [ -z "$file" ] || usage; file="$1"; shift ;;
    esac
done
[ -n "$file" ] || usage

[ -f "$file" ] && [ -r "$file" ] || { echo "ОШИБКА: файл не найден или не читается: $file (каталог бэкапов принадлежит root с правами 700: запустите через sudo)" >&2; exit 2; }
case "$file" in
    *.dump) mode=dump ;;
    *.dump.gpg) mode=dump-gpg ;;
    *) echo "ОШИБКА: ожидается файл *.dump или *.dump.gpg, получено: $file" >&2; exit 2 ;;
esac
if [ -n "$media" ]; then
    [ -f "$media" ] && [ -r "$media" ] || { echo "ОШИБКА: архив медиа не найден: $media" >&2; exit 2; }
    case "$media" in *.tar.gz) ;; *) echo "ОШИБКА: архив медиа должен быть *.tar.gz" >&2; exit 2 ;; esac
    # Защита от выхода за пределы томов: внутри только media/ и private_media/, без '..'.
    entries=$(tar -tzf "$media") || { echo "ОШИБКА: архив медиа повреждён: $media" >&2; exit 2; }
    if printf '%s\n' "$entries" | grep -Ev '^(media|private_media)(/|$)' > /dev/null || printf '%s\n' "$entries" | grep -F '..' > /dev/null; then
        echo "ОШИБКА: в архиве медиа есть пути вне media/ и private_media/ или '..': восстановление отменено" >&2
        exit 2
    fi
    # Симлинки и хардлинки в архиве запрещены: через них распаковка могла бы писать за пределы томов.
    if tar -tvzf "$media" | grep -E '^[lh]' > /dev/null; then
        echo "ОШИБКА: в архиве медиа есть символические или жёсткие ссылки: восстановление отменено" >&2
        exit 2
    fi
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
read -r -a DC <<< "${COMPOSE_CMD:-docker compose}"

# Контрольная сумма: считаем сами и сравниваем с первым полем .sha256. Нет файла .sha256 - предупреждение.
for f in "$file" "$media"; do
    [ -n "$f" ] || continue
    if [ -f "$f.sha256" ]; then
        expected=$(cut -d' ' -f1 "$f.sha256" | head -n 1)
        actual=$(sha256sum "$f" | cut -d' ' -f1)
        [ -n "$expected" ] && [ "$expected" = "$actual" ]             || { echo "ОШИБКА: контрольная сумма не совпала: $f" >&2; exit 2; }
        echo "Контрольная сумма совпала: $f"
    else
        echo "ПРЕДУПРЕЖДЕНИЕ: нет файла $f.sha256, целостность файла не проверена" >&2
    fi
done

project=$("${DC[@]}" config --format json 2> /dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])' 2> /dev/null) || project=""
[ -n "$project" ] || { echo "ОШИБКА: не удалось определить имя compose-проекта (docker compose config / python3). Ничего не тронуто." >&2; exit 2; }
echo "Будет ПЕРЕЗАПИСАНА рабочая база compose-проекта '$project' данными из: $file"
[ -z "$media" ] || echo "и файлы медиа из: $media (существующие файлы с теми же именами будут заменены)"
if [ "$assume_yes" -ne 1 ]; then
    [ -t 0 ] || { echo "ОШИБКА: нет терминала для подтверждения. Запустите интерактивно или добавьте --yes." >&2; exit 2; }
    read -r -p "Для подтверждения введите имя проекта ($project): " answer
    [ "$answer" = "$project" ] || { echo "Отменено." >&2; exit 1; }
fi

echo "== 1/5 Остановка backend, celery_worker, celery_beat, bot"
"${DC[@]}" stop backend celery_worker celery_beat bot

echo "== 2/5 Страховочный дамп текущей базы (pre-restore_*.dump в каталоге бэкапов, сам не удаляется)"
# shellcheck disable=SC2016  # переменные раскрываются внутри контейнера, одинарные кавычки намеренно
"${DC[@]}" run --rm -T backup sh -c '
    set -eu; umask 077
    f=/backups/pre-restore_$(date +%Y-%m-%d_%H%M%S).dump
    pg_dump -Fc -Z 6 -f "$f.part" && pg_restore --list "$f.part" > /dev/null && mv "$f.part" "$f"
    echo "страховочный дамп: $f"
' || { echo "ОШИБКА: страховочный дамп не создан, восстановление остановлено (база не тронута; сервисы остановлены: docker compose up -d)" >&2; exit 1; }

echo "== 3/5 Восстановление базы"
if ! "${DC[@]}" run --rm -T backup /usr/local/bin/restore-inner.sh "$mode" < "$file"; then
    echo "ОШИБКА: восстановление не удалось. Сервисы остановлены. Откат: ./scripts/restore.sh <pre-restore_*.dump>" >&2
    exit 1
fi

if [ -n "$media" ]; then
    echo "== 4/5 Восстановление медиа"
    "${DC[@]}" run --rm -T --no-deps --entrypoint tar backend --no-same-owner --no-overwrite-dir -xzf - -C /app < "$media"
else
    echo "== 4/5 Медиа не указаны (--media), пропускаю"
fi

echo "== 5/5 Запуск сервисов и проверка"
"${DC[@]}" up -d backend celery_worker celery_beat bot
"${DC[@]}" up -d --wait backend celery_worker celery_beat
"${DC[@]}" exec -T backend python manage.py check
echo "Готово: база восстановлена, backend здоров (/healthz), manage.py check без ошибок."
