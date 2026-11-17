#!/usr/bin/env bash
# Тесты scripts/check-memory.sh (задача 7.7a). Без Docker: docker - заглушка в PATH.
# Запуск: ./scripts/tests/test_check_memory.sh   Код возврата 0 = все проверки прошли.
# shellcheck disable=SC2015,SC2016  # A && B || C в проверках намеренно; одинарные кавычки - тексты заглушек
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (ожидалось: $2 | получено: $3)"; fi; }
contains() { if grep -qF -- "$3" <<< "$2"; then ok "$1"; else bad "$1 (нет '$3' в: $(head -c 300 <<< "$2"))"; fi; }

BIN="$TMP/bin"
mkdir -p "$BIN"
# Заглушка: два контейнера. Состояние задаётся переменными STUB_*.
#   STUB_WEB_USED - использование web (формат docker stats), STUB_WEB_OOM - OOMKilled web,
#   STUB_NO_CONTAINERS=1 - compose ps -q пуст, STUB_WEB_LIMIT - HostConfig.Memory web (байты).
cat > "$BIN/docker" <<'MOCK'
#!/bin/sh
case "$1" in
    compose)
        [ "${STUB_NO_CONTAINERS:-0}" = 1 ] && exit 0
        echo aaaaaaaaaaaa1111
        echo bbbbbbbbbbbb2222
        ;;
    stats)
        echo "aaaaaaaaaaaa|${STUB_WEB_USED:-100MiB} / 640MiB"
        echo "bbbbbbbbbbbb|50MiB / 256MiB"
        ;;
    inspect)
        for last; do :; done
        case "$last" in
            aaaaaaaaaaaa1111) echo "${STUB_WEB_LIMIT:-671088640}|${STUB_WEB_OOM:-false}|web" ;;
            bbbbbbbbbbbb2222) echo "268435456|false|worker" ;;
        esac
        ;;
esac
MOCK
chmod +x "$BIN/docker"

run() { # run <имя> <ожидаемый код> [VAR=значение ...]
    local name="$1" want="$2"
    shift 2
    local out code
    set +e
    out=$(cd "$TMP" && env -u MEM_ALERT_PERCENT PATH="$BIN:$PATH" ENV_FILE="$TMP/none.env" "$@" "$ROOT/scripts/check-memory.sh" 2>&1)
    code=$?
    set -e
    LAST_OUT="$out"
    check "$name: код возврата" "$want" "$code"
}

run "норма (16% и 20%)" 0
contains "норма: таблица с сервисами" "$LAST_OUT" "web"
contains "норма: подсказка об итоге" "$LAST_OUT" "усі контейнери в межах 85%"

run "превышение порога по умолчанию (600 из 640 МиБ = 94%)" 1 STUB_WEB_USED=600MiB
contains "превышение: помечено в таблице" "$LAST_OUT" "ПЕРЕВИЩЕННЯ"

run "ровно на пороге не превышение (85% при пороге 85)" 0 STUB_WEB_USED=544MiB
run "порог из окружения: 50% при 330 МиБ (51%) -> превышение" 1 STUB_WEB_USED=330MiB MEM_ALERT_PERCENT=50
run "порог из окружения: 90% при 600 МиБ (94%) -> превышение" 1 STUB_WEB_USED=600MiB MEM_ALERT_PERCENT=90
run "порог из окружения: 99% при 600 МиБ (94%) -> норма" 0 STUB_WEB_USED=600MiB MEM_ALERT_PERCENT=99

printf 'MEM_ALERT_PERCENT=40\n' > "$TMP/low.env"
run "порог из ENV_FILE (40%) при 330 МиБ (51%) -> превышение" 1 STUB_WEB_USED=330MiB ENV_FILE="$TMP/low.env"

run "OOMKilled при малой памяти -> ошибка" 1 STUB_WEB_OOM=true
contains "OOM: помечено в таблице" "$LAST_OUT" "OOMKilled"

run "гибибайты в stats разбираются (1GiB > 640 МиБ)" 1 STUB_WEB_USED=1GiB
run "контейнер без mem_limit: проценты не считаются, код 0" 0 STUB_WEB_LIMIT=0
contains "без лимита: пометка" "$LAST_OUT" "немає mem_limit"

run "неверный порог -> код 2" 2 MEM_ALERT_PERCENT=abc
run "порог 0 -> код 2" 2 MEM_ALERT_PERCENT=0
run "порог 101 -> код 2" 2 MEM_ALERT_PERCENT=101
run "стек не запущен -> код 2" 2 STUB_NO_CONTAINERS=1

if [ "$fails" -gt 0 ]; then
    echo "Провалено проверок: $fails"
    exit 1
fi
echo "Все проверки прошли."
