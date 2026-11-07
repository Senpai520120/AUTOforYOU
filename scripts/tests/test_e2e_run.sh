#!/usr/bin/env bash
# Тесты сверки ключей scripts/e2e-run.sh (задача 9.58). Без Docker: проверяется только check_env_keys.
# Запуск: ./scripts/tests/test_e2e_run.sh   Код возврата 0 = все проверки прошли.
# shellcheck disable=SC2015  # A && B || C в проверках намеренно
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (ожидалось: $2 | получено: $3)"; fi; }
contains() { if grep -qF -- "$3" <<< "$2"; then ok "$1"; else bad "$1 (нет '$3' в: $(head -c 300 <<< "$2"))"; fi; }
lacks() { if grep -qF -- "$3" <<< "$2"; then bad "$1 (найдено '$3')"; else ok "$1"; fi; }

# shellcheck disable=SC1091  # путь строится из $ROOT во время выполнения
source "$ROOT/scripts/e2e-run.sh"

EXAMPLE="$TMP/example"
ENVF="$TMP/env"
cat > "$EXAMPLE" << 'EOF'
# комментарий: COMMENTED_KEY=1 не считается ключом
# COMMENTED_KEY=1
POSTGRES_PASSWORD=e2e_local_db_pass
SECRET_KEY=
# пустое значение: ключ есть, сверка смотрит только на ключи
E2E_RELAX_THROTTLES=true
E2E_SEED_ALLOWED=true

LOGIN_MAX_FAILURES=5
EOF

run() { local rc=0 out; out=$(check_env_keys "$1" "$2" 2>&1) || rc=$?; echo "$rc|$out"; }

# 1. все ключи есть (значения другие, пустое значение тоже «есть») - код 0
cat > "$ENVF" << 'EOF'
POSTGRES_PASSWORD=другой
SECRET_KEY=
# пустое значение: ключ есть, сверка смотрит только на ключи
E2E_RELAX_THROTTLES=false
E2E_SEED_ALLOWED=true
LOGIN_MAX_FAILURES=9
EXTRA_KEY=лишний ключ не мешает
EOF
res=$(run "$ENVF" "$EXAMPLE")
check "полный файл проходит" "0" "${res%%|*}"

# 2. не хватает ключа: код 2, имя в выводе, значения секретов не печатаются
cat > "$ENVF" << 'EOF'
POSTGRES_PASSWORD=SUPER_SECRET_VALUE_123
SECRET_KEY=ANOTHER_SECRET_456
E2E_SEED_ALLOWED=true
EOF
res=$(run "$ENVF" "$EXAMPLE")
check "недостающие ключи: код 2" "2" "${res%%|*}"
contains "в ошибке имя E2E_RELAX_THROTTLES" "$res" "E2E_RELAX_THROTTLES"
contains "в ошибке имя LOGIN_MAX_FAILURES" "$res" "LOGIN_MAX_FAILURES"
lacks "значение секрета не печатается" "$res" "SUPER_SECRET_VALUE_123"
lacks "второй секрет не печатается" "$res" "ANOTHER_SECRET_456"
lacks "присутствующий ключ не в списке недостающих" "$res" "POSTGRES_PASSWORD,"

# 3. закомментированные ключи шаблона не считаются обязательными
res=$(run "$ENVF" "$EXAMPLE")
lacks "закомментированный ключ не требуется" "$res" "COMMENTED_KEY"

# 4. нет .env.e2e: код 1 и подсказка cp
res=$(run "$TMP/нет-такого" "$EXAMPLE")
check "нет файла: код 1" "1" "${res%%|*}"
contains "подсказка cp" "$res" "cp "

# 5. нет шаблона: код 1
res=$(run "$ENVF" "$TMP/нет-шаблона")
check "нет шаблона: код 1" "1" "${res%%|*}"

# 6. настоящий шаблон репозитория и сам себя проходят
res=$(run "$ROOT/.env.e2e.example" "$ROOT/.env.e2e.example")
check "шаблон проходит сверку сам с собой" "0" "${res%%|*}"

# 7. в шаблоне есть флаг, ради которого устаревшая копия .env.e2e должна падать
grep -q '^E2E_RELAX_THROTTLES=true' "$ROOT/.env.e2e.example" && ok "шаблон содержит E2E_RELAX_THROTTLES=true" \
    || bad "шаблон не содержит E2E_RELAX_THROTTLES=true"

# 8. скрипт сохраняет код Playwright и всегда чистит: ключевые строки на месте
grep -q 'trap restore EXIT' "$ROOT/scripts/e2e-run.sh" && ok "cleanup на EXIT" || bad "нет trap restore EXIT"
grep -q 'docker compose down || ' "$ROOT/scripts/e2e-run.sh" && ok "dev-стек останавливается" || bad "нет docker compose down"
if grep -nE 'down[^|]*-v|--volumes' "$ROOT/scripts/e2e-run.sh" | grep -v '^[0-9]*:#' | grep -v 'БЕЗ -v\|без -v' > /dev/null; then
    bad "в e2e-run.sh есть down с -v/--volumes для dev-стека"
else
    ok "dev-стек не снимается с томами"
fi

echo
if [ "$fails" -eq 0 ]; then echo "Все проверки пройдены."; else echo "Провалено проверок: $fails"; exit 1; fi
