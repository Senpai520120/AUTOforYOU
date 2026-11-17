#!/bin/sh
# Подключается (source) скриптами, которые зовут docker compose с хоста, ПОСЛЕ cd в корень проекта.
# Только POSIX sh: подключается и из bash, и из /bin/sh-скриптов (init-letsencrypt.sh; на Ubuntu sh = dash).
# deploy.sh собирает образы с тегом IMAGE_TAG=<git sha> и пишет его в .deploy/current_tag;
# без IMAGE_TAG docker-compose.yml берёт ${IMAGE_TAG:-local} -> образ :local не найден / собирается лишний.
#
# Общее с deploy.sh: каталог состояния STATE_DIR и проверка тега is_image_tag.
# Автоподстановка IMAGE_TAG: если он не задан и есть непустой $STATE_DIR/current_tag - берём тег оттуда.
# Не подставляем, если задан COMPOSE_CMD (нестандартный/чужой compose-проект, например e2e: у него свои образы,
# а .deploy относится к боевому стеку) и если deploy.sh попросил только функции (IMAGE_TAG_LIB_NO_AUTO=1).
STATE_DIR="${STATE_DIR:-.deploy}"

# Тег попадает в команды docker: только git sha или 'local'.
is_image_tag() { # $1 = тег
    printf '%s\n' "$1" | grep -Eqx '[0-9a-f]{7,40}|local'
}

if [ -z "${IMAGE_TAG:-}" ] && [ -z "${COMPOSE_CMD:-}" ] && [ -z "${IMAGE_TAG_LIB_NO_AUTO:-}" ] && [ -s "$STATE_DIR/current_tag" ]; then
    _image_tag="$(tr -d '[:space:]' < "$STATE_DIR/current_tag")"
    if is_image_tag "$_image_tag"; then
        IMAGE_TAG="$_image_tag"
        export IMAGE_TAG
    else
        echo "ПРЕДУПРЕЖДЕНИЕ: $STATE_DIR/current_tag повреждён, IMAGE_TAG не выставлен" >&2
    fi
    unset _image_tag
fi
