"""Проверка живости для healthcheck контейнеров и внешнего uptime-монитора (задача 7.3).

Без аутентификации и троттлинга: монитор приходит каждую минуту, healthcheck - каждые несколько
секунд. В ответе только статусы зависимостей: без версий, хостов и текста исключений.
"""
import logging
import os

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)

_CACHE_KEY = 'healthz:probe'


def _check_db() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - любая ошибка драйвера = БД недоступна; текст наружу не отдаём
        logger.warning('healthz: БД не отвечает (%s)', type(exc).__name__)
        return False
    return True


def _check_cache() -> bool:
    try:
        cache.set(_CACHE_KEY, '1', timeout=10)
        return cache.get(_CACHE_KEY) == '1'
    except Exception as exc:  # noqa: BLE001
        logger.warning('healthz: кэш не отвечает (%s)', type(exc).__name__)
        return False


@require_safe
@never_cache
def healthz(request):
    """GET /healthz: 200, если БД отвечает на SELECT 1 и (при заданном REDIS_URL) отвечает кэш."""
    db_ok = _check_db()
    if os.environ.get('REDIS_URL', '').strip():
        cache_ok = _check_cache()
        cache_state = 'ok' if cache_ok else 'error'
    else:
        cache_ok = True
        cache_state = 'skipped'
    ok = db_ok and cache_ok
    response = JsonResponse(
        {'status': 'ok' if ok else 'error', 'db': 'ok' if db_ok else 'error', 'cache': cache_state},
        status=200 if ok else 503,
    )
    response['Cache-Control'] = 'no-store'
    return response
