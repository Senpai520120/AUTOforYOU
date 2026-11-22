#!/usr/bin/env bash
# pre-push: быстрые проверки CI (lint, check, migrations, LF, tsc). Тесты и сборка - нет (долго).
# Python-шаги - если в пушимых коммитах есть *.py/requirements*, frontend-шаги - если есть frontend/.
set -uo pipefail
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT" || exit 1

if changed=$(git diff --name-only '@{push}..HEAD' 2>/dev/null); then :
elif changed=$(git diff --name-only origin/main...HEAD 2>/dev/null); then :
else changed=""; echo "[pre-push] не удалось определить изменения - запускаю всё"; ALL=1; fi
ALL=${ALL:-${PRE_PUSH_ALL:-0}}   # PRE_PUSH_ALL=1 - прогнать всё независимо от диффа

want_py=$ALL; want_fe=$ALL
printf '%s\n' "$changed" | grep -Eq '\.py$|^requirements.*\.txt$|^ruff\.toml$' && want_py=1
printf '%s\n' "$changed" | grep -q '^frontend/' && want_fe=1

# Интерпретатор: $VIRTUAL_ENV, ./.venv, .venv основного репо, иначе python из PATH.
find_python() {
    local cand common
    common=$(cd "$ROOT" && cd "$(git rev-parse --git-common-dir)/.." 2>/dev/null && pwd)
    for base in "${VIRTUAL_ENV:-}" "$ROOT/.venv" "$common/.venv"; do
        [ -n "$base" ] || continue
        for cand in "$base/Scripts/python.exe" "$base/bin/python"; do
            [ -x "$cand" ] && { echo "$cand"; return; }
        done
    done
    command -v python || command -v python3
}

fail=0
step() { # step <имя> <команда...>
    local name=$1; shift
    echo "[pre-push] $name..."
    if "$@"; then echo "[pre-push] $name ok"; else echo "[pre-push] $name ОШИБКА" >&2; fail=1; fi
}

PY=$(find_python)
# Окружение как в CI: без .env (его нет в worktree) и без БД/Redis/внешних токенов.
DJ_ENV=(DATABASE_URL= REDIS_URL= SECRET_KEY=pre-push-not-used DEBUG=true LIQPAY_PUBLIC_KEY=dummy LIQPAY_PRIVATE_KEY=dummy TELEGRAM_BOT_TOKEN=)
if [ "$want_py" = 1 ]; then
    [ -n "$PY" ] || { echo "[pre-push] python не найден" >&2; exit 1; }
    step ruff "$PY" -m ruff check .
    step "manage.py check" env "${DJ_ENV[@]}" "$PY" manage.py check
    step "makemigrations --check" env "${DJ_ENV[@]}" "$PY" manage.py makemigrations --check --dry-run
else
    echo "[pre-push] python: изменений нет, пропуск"
fi
step "LF в *.sh" scripts/check-infra.sh lf
if [ "$want_fe" = 1 ]; then
    step "eslint" bash -c 'cd frontend && npm run lint'
    step "tsc" bash -c 'cd frontend && npx tsc --noEmit'
else
    echo "[pre-push] frontend: изменений нет, пропуск"
fi

echo "[pre-push] НЕ проверено здесь: тесты (scripts/test-backend.ps1), openapi.yaml, build, e2e - их гоняет CI."
exit "$fail"
