#!/bin/bash
set -e

# DEBUG на сервере (gunicorn) - только осознанно (задача 7.2): трассировки и выключенные SECURE_*.
case "${DEBUG,,}" in
  true|1|yes)
    case "${ALLOW_DEBUG_ON_PUBLIC_HOST,,}" in
      true|1|yes) echo "[entrypoint] ВНИМАНИЕ: DEBUG=true на сервере (ALLOW_DEBUG_ON_PUBLIC_HOST=true)" >&2 ;;
      *) echo "[entrypoint] DEBUG=true недопустим для gunicorn: поставьте DEBUG=false в .env" >&2; exit 1 ;;
    esac ;;
esac

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

# Воркеры: 2 рассчитано на сервер 4 ГБ; больше - только после замера `docker stats` (задача 7.3).
# --max-requests(+jitter) перезапускает воркеры и ограничивает утечки памяти; --worker-tmp-dir /dev/shm
# убирает блокировки heartbeat на диске контейнера. Формат access-лога не трогать (задача 7.2).
echo "[entrypoint] Starting Gunicorn (workers=${GUNICORN_WORKERS:-2}, port=${PORT:-8000})..."
exec gunicorn core.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --graceful-timeout 30 \
  --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
  --max-requests-jitter 100 \
  --worker-tmp-dir /dev/shm \
  --access-logfile - \
  --access-logformat '%(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s' \
  --error-logfile -
