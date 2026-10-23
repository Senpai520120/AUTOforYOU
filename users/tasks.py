"""Фоновые задачи пользователей (задача 1.7)."""
import logging

from celery import shared_task
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task
def flush_expired_tokens():
    """Чистит просроченные JWT в blacklist и сессии Django (01-Q1). Раз в сутки."""
    call_command('flushexpiredtokens')
    call_command('clearsessions')


@shared_task
def send_password_reset_email_task(email):
    """Письмо сброса: поиск аккаунта и отправка в воркере, чтобы запрос не выдавал, есть ли аккаунт."""
    from django.contrib.auth import get_user_model

    from .emails import send_password_reset_email

    user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if user is not None:
        send_password_reset_email(user)


@shared_task
def anonymize_due_accounts():
    """Раз в сутки: аккаунты, у которых истёк период отмены, обезличиваются (1.8, Q3).

    Период - SiteSettings.account_deletion_grace_days. Ошибка одного аккаунта не останавливает
    остальные; в лог - только pk и тип ошибки.
    """
    from datetime import timedelta

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from .services import anonymize_user, deletion_grace_days

    cutoff = timezone.now() - timedelta(days=deletion_grace_days())
    due = get_user_model().objects.filter(
        deletion_scheduled_at__isnull=False, deletion_scheduled_at__lte=cutoff, deleted_at__isnull=True,
    ).order_by('pk')
    done = 0
    for user in due.iterator():
        try:
            done += anonymize_user(user, due_before=cutoff)
        except Exception as exc:
            logger.error('anonymize_due_accounts: user=%s не обезличен: %s', user.pk, type(exc).__name__)
    return done
