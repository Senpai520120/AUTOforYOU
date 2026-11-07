"""Очистка журнала аудита по сроку хранения (1.13)."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='audit.tasks.purge_audit_log')
def purge_audit_log() -> int:
    from .models import AuditAction, AuditLog
    from .services import log_action

    days = int(settings.AUDIT_LOG_RETENTION_DAYS or 0)
    if days <= 0:
        return 0  # 0 = хранить без ограничения
    cutoff = timezone.now() - timedelta(days=days)
    with transaction.atomic():
        # _base_manager: менеджер objects запрещает delete() (журнал только на добавление).
        deleted, _ = AuditLog._base_manager.filter(created_at__lt=cutoff).delete()
        log_action(None, AuditAction.AUDIT_PURGE, after={'deleted': deleted, 'retention_days': days})
    logger.info('audit log purged: deleted=%s retention_days=%s', deleted, days)
    return deleted
