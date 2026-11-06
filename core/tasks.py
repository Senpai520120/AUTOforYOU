"""Базовый класс Celery-задач с повторами (задача 8.9).

Для сетевых задач, где потеря недопустима (письма, Telegram, алерты). Подключается явно:
`@shared_task(base=ResilientTask)`. Глобальная подмена task_cls не используется.
Параметры читаются из settings при каждом обращении (RESILIENT_TASK_MAX_RETRIES, RESILIENT_TASK_ACKS_LATE;
не CELERY_*: такие имена Celery применил бы ко всем задачам).
"""
import logging

import httpx
from celery import Task, shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


class ResilientTask(Task):
    abstract = True
    autoretry_for = (OSError, ConnectionError)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    @property
    def max_retries(self):
        return int(getattr(settings, 'RESILIENT_TASK_MAX_RETRIES', 3))

    @max_retries.setter
    def max_retries(self, value):  # Celery присваивает атрибут при создании класса задачи
        pass

    @property
    def acks_late(self):
        return bool(getattr(settings, 'RESILIENT_TASK_ACKS_LATE', True))

    @acks_late.setter
    def acks_late(self, value):
        pass


@shared_task(ignore_result=True)
def send_celery_heartbeat():
    """Пинг внешнего сервиса-сторожа (9.55): доходит, только если живы beat, Redis и worker.

    Нет пинга - сторож сам шлёт оповещение. Повторов нет: следующий пинг придёт по расписанию.
    Адрес содержит секрет, поэтому в лог идёт только тип ошибки.
    """
    url = settings.CELERY_HEARTBEAT_URL
    if not url:
        return
    try:
        httpx.get(url, timeout=10).raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.warning('Celery heartbeat: сторож не ответил (%s)', type(exc).__name__)
