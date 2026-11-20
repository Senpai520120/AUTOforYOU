"""Throttle, переживающий падение кэша (задача 10.16, E3).

Решение оркестратора (допущение, владелец может поменять, см. LAUNCH_CHECKLIST «Redis»): при недоступном кэше
лимит заявки и калькулятора ПРОПУСКАЕТ запрос (fail-open). Заявку по-прежнему защищают капча и идемпотентность
(10.13), а отказ в приёме заявки из-за сбоя Redis стоил бы клиента. Остальные throttle (вход, телефоны) не
затрагиваются и остаются строгими.

Сбой: ``logger.warning`` без ПДн и алерт владельцу через ``core.tasks._send_failed_task_alert``. Дедуп алерта -
файл-маркер во временной папке (не Redis, он лежит): не чаще раза в ``ALERT_INTERVAL`` секунд на контейнер.
"""
import logging
import tempfile
import threading
import time
from pathlib import Path

from rest_framework.throttling import ScopedRateThrottle

logger = logging.getLogger(__name__)

ALERT_INTERVAL = 3600
CACHE_ALERT_SUBJECT = 'AUTOforYOU: кеш (Redis) недоступний, ліміти запитів пропускаються'

def cache_errors() -> tuple[type[BaseException], ...]:
    """Ошибки недоступного кэша: сырые redis, builtin и django_redis.ConnectionInterrupted (его кидает DefaultClient)."""
    errors: tuple[type[BaseException], ...] = (ConnectionError, TimeoutError)
    try:
        import redis
        errors += (redis.exceptions.RedisError,)
    except ImportError:  # pragma: no cover
        pass
    try:
        from django_redis.exceptions import ConnectionInterrupted
        errors += (ConnectionInterrupted,)
    except ImportError:  # pragma: no cover
        pass
    return errors


def _notify_owner() -> None:
    from core.tasks import _send_failed_task_alert
    _send_failed_task_alert(
        'Кеш (Redis) недоступний: ліміти заявок і калькулятора тимчасово не діють (fail-open), '
        'а заявки з капчею не приймаються. Перевірте контейнер redis, docs/RUNBOOK.md.',
        CACHE_ALERT_SUBJECT,
    )


def _marker_path() -> Path:
    return Path(tempfile.gettempdir()) / 'autoforyou_cache_down_alert'


def _alert_once() -> None:
    """Не чаще раза в ALERT_INTERVAL на контейнер: файл-маркер по mtime (Redis лежит, а память воркера у каждого своя)."""
    marker = _marker_path()
    try:
        if marker.exists() and time.time() - marker.stat().st_mtime < ALERT_INTERVAL:
            return
        marker.touch()
    except OSError:
        pass  # нет маркера - лучше лишний алерт, чем тишина
    threading.Thread(target=_notify_owner, daemon=True).start()


class FailOpenScopedRateThrottle(ScopedRateThrottle):
    """ScopedRateThrottle, который при сбое кэша пропускает запрос."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except cache_errors() as exc:
            logger.warning('throttle %s: кеш недоступний (%s), запит пропущено', self.scope, type(exc).__name__)
            _alert_once()
            return True
