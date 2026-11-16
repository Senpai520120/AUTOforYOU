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
if [ ! -e "$TMP/PWNED" ]; then ok "повреждённый тег не выполняется"; else bad "выполнился код из current_tag"; fi

echo a1b2c3d > "$TMP/.deploy/current_tag"
# init-letsencrypt.sh и update-cloudflare-ips.sh - /bin/sh (на Ubuntu dash): библиотека обязана быть POSIX.
SH=$(command -v dash || command -v sh)
check "подключение из POSIX sh ($SH): тег из current_tag" "a1b2c3d"     "$(cd "$TMP" && env -u IMAGE_TAG "$SH" -c '. scripts/lib-image-tag.sh; echo "${IMAGE_TAG:-unset}"' 2>&1)"
check "docker compose видит IMAGE_TAG из current_tag" "TAG=a1b2c3d" "$(cd "$TMP" && env -u IMAGE_TAG PATH="$TMP/bin:$PATH" bash -c '. scripts/lib-image-tag.sh; docker compose ps')"

# Чужой compose-проект (COMPOSE_CMD): .deploy относится к боевому стеку, тег из него не берём.
check "COMPOSE_CMD задан: тег из current_tag не берётся" "unset" "$(get COMPOSE_CMD='docker compose -p e2e')"
check "COMPOSE_CMD задан: явный IMAGE_TAG сохраняется" "manual" "$(get COMPOSE_CMD='docker compose -p e2e' IMAGE_TAG=manual)"
check "COMPOSE_CMD пуст: тег из current_tag берётся" "a1b2c3d" "$(get COMPOSE_CMD=)"
check "IMAGE_TAG_LIB_NO_AUTO: тег не подставляется" "unset" "$(get IMAGE_TAG_LIB_NO_AUTO=1)"
check "is_image_tag принимает sha и local" "yes" "$(cd "$TMP" && bash -c '. scripts/lib-image-tag.sh; is_image_tag a1b2c3d && is_image_tag local && echo yes' 2> /dev/null)"
check "is_image_tag отвергает мусор" "no" "$(cd "$TMP" && bash -c '. scripts/lib-image-tag.sh; is_image_tag "a1b2c3d; x" || is_image_tag "" || echo no' 2> /dev/null)"

if [ "$fails" -eq 0 ]; then echo "Все проверки пройдены"; exit 0; else echo "Провалено: $fails"; exit 1; fi
