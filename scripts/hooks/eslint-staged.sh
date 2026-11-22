#!/usr/bin/env bash
# pre-commit: eslint для изменённых frontend/**/*.{ts,tsx}. Получает пути от корня репо.
# Ошибки ломают коммит, предупреждения - нет.
set -uo pipefail
[ "$#" -eq 0 ] && exit 0
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT/frontend" || exit 1
files=()
for f in "$@"; do files+=("${f#frontend/}"); done
echo "[pre-commit] eslint: ${#files[@]} файл(ов)"
npx eslint --max-warnings=-1 "${files[@]}"
