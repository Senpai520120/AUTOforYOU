"""Чистка журнала упавших задач (8.9)."""
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone


@shared_task(name='task_ledger.tasks.purge_failed_tasks')
def purge_failed_tasks() -> int:
    from .models import FailedTask

    cutoff = timezone.now() - timedelta(days=int(settings.FAILED_TASK_RETENTION_DAYS))
    deleted, _ = FailedTask.objects.filter(failed_at__lt=cutoff).delete()
    return deleted
