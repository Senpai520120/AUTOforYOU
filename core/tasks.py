"""Базовый класс Celery-задач с повторами (задача 8.9).

Для сетевых задач, где потеря недопустима (письма, Telegram, алерты). Подключается явно:
`@shared_task(base=ResilientTask)`. Глобальная подмена task_cls не используется.
Параметры читаются из settings при каждом обращении (RESILIENT_TASK_MAX_RETRIES, RESILIENT_TASK_ACKS_LATE;
не CELERY_*: такие имена Celery применил бы ко всем задачам).
"""
from celery import Task
from django.conf import settings


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
