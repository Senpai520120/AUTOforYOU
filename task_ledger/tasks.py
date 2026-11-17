"""Чистка журнала упавших задач (8.9)."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


# Пакетная задача: глобальный лимит 120/180 с (CELERY_TASK_SOFT_TIME_LIMIT) мал для большого объёма, поэтому свой лимит.
@shared_task(name='task_ledger.tasks.purge_failed_tasks', soft_time_limit=900, time_limit=960)
def purge_failed_tasks() -> int:
    from .models import FailedTask

    cutoff = timezone.now() - timedelta(days=int(settings.FAILED_TASK_RETENTION_DAYS))
    deleted, _ = FailedTask.objects.filter(failed_at__lt=cutoff).delete()
    return deleted
