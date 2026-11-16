#!/bin/sh
# Подключается (source) скриптами, которые зовут docker compose с хоста, ПОСЛЕ cd в корень проекта.
# Только POSIX sh: подключается и из bash, и из /bin/sh-скриптов (init-letsencrypt.sh; на Ubuntu sh = dash).
# deploy.sh собирает образы с тегом IMAGE_TAG=<git sha> и пишет его в .deploy/current_tag;
# без IMAGE_TAG docker-compose.yml берёт ${IMAGE_TAG:-local} -> образ :local не найден / собирается лишний.
# Если IMAGE_TAG не задан и есть непустой .deploy/current_tag - берём тег оттуда. Иначе (локальная разработка) без изменений.
if [ -z "${IMAGE_TAG:-}" ] && [ -s .deploy/current_tag ]; then
    _image_tag="$(tr -d '[:space:]' < .deploy/current_tag)"
    # Тег попадает в команды docker: только git sha или 'local' (как read_state в deploy.sh).
    if printf '%s\n' "$_image_tag" | grep -Eqx '[0-9a-f]{7,40}|local'; then
        IMAGE_TAG="$_image_tag"
        export IMAGE_TAG
    else
        echo "ПРЕДУПРЕЖДЕНИЕ: .deploy/current_tag повреждён, IMAGE_TAG не выставлен" >&2
    fi
    unset _image_tag
fi
