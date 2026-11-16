#!/usr/bin/env bash
# Тесты scripts/lib-image-tag.sh: IMAGE_TAG берётся из .deploy/current_tag. Без Docker.
# Запуск: ./scripts/tests/test_image_tag.sh   Код возврата 0 = все проверки прошли.
# shellcheck disable=SC2016  # одинарные кавычки - тексты для bash -c
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (ожидалось: '$2' | получено: '$3')"; fi; }

mkdir -p "$TMP/scripts" "$TMP/bin"
cp "$ROOT/scripts/lib-image-tag.sh" "$TMP/scripts/"
# docker-заглушка печатает IMAGE_TAG, с которым её вызвали.
printf '#!/bin/sh\necho "TAG=${IMAGE_TAG:-unset}"\n' > "$TMP/bin/docker"
chmod +x "$TMP/bin/docker"

get() { # get [VAR=значение ...] -> IMAGE_TAG после подключения библиотеки
    (cd "$TMP" && env -u IMAGE_TAG "$@" bash -c '. scripts/lib-image-tag.sh; echo "${IMAGE_TAG:-unset}"' 2> /dev/null)
}

rm -rf "$TMP/.deploy"
check "нет current_tag: IMAGE_TAG не задан" "unset" "$(get)"

mkdir -p "$TMP/.deploy"; : > "$TMP/.deploy/current_tag"
check "пустой current_tag: IMAGE_TAG не задан" "unset" "$(get)"

echo a1b2c3d > "$TMP/.deploy/current_tag"
check "current_tag есть: IMAGE_TAG взят из него" "a1b2c3d" "$(get)"
check "явный IMAGE_TAG не перезаписывается" "manual" "$(get IMAGE_TAG=manual)"

echo 'a1b2c3d; touch PWNED' > "$TMP/.deploy/current_tag"
check "повреждённый current_tag: IMAGE_TAG не задан" "unset" "$(get)"
[ ! -e "$TMP/PWNED" ] && ok "повреждённый тег не выполняется" || bad "выполнился код из current_tag"

echo a1b2c3d > "$TMP/.deploy/current_tag"
check "docker compose видит IMAGE_TAG из current_tag" "TAG=a1b2c3d" "$(cd "$TMP" && env -u IMAGE_TAG PATH="$TMP/bin:$PATH" bash -c '. scripts/lib-image-tag.sh; docker compose ps')"

[ "$fails" -eq 0 ] && { echo "Все проверки пройдены"; exit 0; } || { echo "Провалено: $fails"; exit 1; }
