#!/bin/bash
# Backend-тесты через .venv. Обнуляем DATABASE_URL/REDIS_URL: локальный .env — docker-шаблон
# с хостами db/redis, а core/settings.py его подгружает (load_dotenv).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON="$ROOT/.venv/Scripts/python.exe"
elif [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON="$ROOT/.venv/bin/python"
else
    echo "Не найден .venv в $ROOT. Создайте: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi
cd "$ROOT"
DATABASE_URL= REDIS_URL= "$PYTHON" manage.py test "$@"
