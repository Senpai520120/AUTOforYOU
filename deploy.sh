#!/bin/bash
# deploy.sh — запуск стека на сервере.
# Использование: ./deploy.sh [--build]
set -euo pipefail

# ─── Проверка обязательных переменных ────────────────────────────────────────

require_var() {
    local name="$1"
    local value="${!name:-}"
    if [[ -z "$value" ]]; then
        echo "ERROR: $name is not set. Add it to .env before deploying." >&2
        exit 1
    fi
}

require_var SECRET_KEY
require_var POSTGRES_PASSWORD
require_var DATABASE_URL

# ─── Страховка от копипасты из .env.example ───────────────────────────────────

if echo "$SECRET_KEY" | grep -qi "REPLACE"; then
    echo "ERROR: SECRET_KEY looks like a placeholder (contains 'REPLACE')." >&2
    echo "       Generate a real key:" >&2
    echo "       python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\"" >&2
    exit 1
fi

if echo "$SECRET_KEY" | grep -qi "local-docker-dev"; then
    echo "ERROR: SECRET_KEY is the dev fallback from .env.docker.example — do not use on prod." >&2
    exit 1
fi

if echo "$POSTGRES_PASSWORD" | grep -qiE "^(autoforyou_dev_pass|autopass123|password|changeme)$"; then
    echo "ERROR: POSTGRES_PASSWORD is a known dev/placeholder value — change it before deploying." >&2
    exit 1
fi

if echo "$DATABASE_URL" | grep -q "host.docker.internal"; then
    echo "ERROR: DATABASE_URL still points to host.docker.internal — update to db:5432 for Docker deployment." >&2
    exit 1
fi

# DEBUG=true в проде отключает SECURE_*-заголовки, показывает трейсбеки
# с полным URLconf и переводит Celery в синхронный режим.
if [[ "$(echo "${DEBUG:-false}" | tr '[:upper:]' '[:lower:]')" =~ ^(true|1|yes)$ ]]; then
    echo "ERROR: DEBUG is enabled. Set DEBUG=false in .env before deploying." >&2
    exit 1
fi

# В паре с CORS_ALLOW_CREDENTIALS=true открытый CORS позволяет любому сайту
# обращаться к API от имени залогиненного пользователя.
if [[ "$(echo "${CORS_ALLOW_ALL_ORIGINS:-false}" | tr '[:upper:]' '[:lower:]')" =~ ^(true|1|yes)$ ]]; then
    echo "ERROR: CORS_ALLOW_ALL_ORIGINS is enabled. Set it to false and list real origins in CORS_ALLOWED_ORIGINS." >&2
    exit 1
fi

echo "[deploy] Pre-flight checks passed."

# ─── Запуск стека ─────────────────────────────────────────────────────────────

BUILD_FLAG=""
if [[ "${1:-}" == "--build" ]]; then
    BUILD_FLAG="--build"
fi

echo "[deploy] Starting stack..."
docker compose up -d $BUILD_FLAG

echo "[deploy] Waiting for backend to become healthy..."
timeout 120 bash -c 'until [ "$(docker inspect --format="{{.State.Health.Status}}" autoforyou-backend-1 2>/dev/null)" = "healthy" ]; do sleep 3; done'

echo "[deploy] Stack is up."
docker compose ps
