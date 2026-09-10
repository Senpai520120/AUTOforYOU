#!/bin/bash
set -e

echo "[entrypoint] Running database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Seeding reference data (idempotent)..."

# Раньше было `2>/dev/null || true`: любая ошибка сида уходила в никуда.
# Так, seed_rates падал при недоступном Redis, тарифы не применялись, и
# калькулятор молча отдавал 422 «Отсутствуют активные тарифы».
# Теперь ошибка видна в логах, но не роняет весь стек: сиды идемпотентны и
# их можно повторить вручную.
run_seed() {
    if ! python manage.py "$1" --no-color; then
        echo "[entrypoint] ВНИМАНИЕ: $1 завершился с ошибкой — справочники могут быть неполными" >&2
    fi
}

run_seed seed_regions
run_seed seed_rates
run_seed seed_auction_fees

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "[entrypoint] Starting Gunicorn (workers=${GUNICORN_WORKERS:-3}, port=${PORT:-8000})..."
exec gunicorn core.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
