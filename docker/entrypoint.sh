#!/bin/bash
set -e

echo "[entrypoint] Running database migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Seeding reference data (idempotent)..."
python manage.py seed_regions --no-color 2>/dev/null || true
python manage.py seed_rates   --no-color 2>/dev/null || true
python manage.py seed_auction_fees --no-color 2>/dev/null || true

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "[entrypoint] Starting Gunicorn (workers=${GUNICORN_WORKERS:-3}, port=${PORT:-8000})..."
exec gunicorn core.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
