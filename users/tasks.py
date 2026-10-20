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
