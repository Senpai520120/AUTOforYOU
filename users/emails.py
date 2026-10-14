"""Письма пользователю (задача 1.6). Тексты - в users/templates/users/email/*.txt.

Отправитель - settings.DEFAULT_FROM_EMAIL. Ошибка отправки логируется и не валит вызывающего.
Полноценный SMTP-адаптер со статусом - задача 3.4.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_verification_token

logger = logging.getLogger(__name__)


def _site_url():
    return (settings.SITE_URL or '').rstrip('/')


def build_verification_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return f'{_site_url()}/verify-email?uid={uid}&token={token}'


def _send(user, subject, template, context, kind):
    if not _site_url():
        logger.warning('SITE_URL не задан: письмо %s не отправлено', kind)
        return False
    body = render_to_string(template, context)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
    except Exception as exc:  # SMTP недоступен - регистрацию не валим
        logger.error('Не удалось отправить письмо %s: %s', kind, type(exc).__name__)
        return False
    return True


def send_verification_email(user):
    if not _site_url():
        logger.warning('SITE_URL не задан: письмо verify_email не отправлено')
        return False
    return _send(
        user, 'AUTOforYOU: підтвердіть email', 'users/email/verify_email.txt',
        {'url': build_verification_url(user), 'ttl_hours': settings.EMAIL_VERIFY_TTL_HOURS},
        'verify_email',
    )


def send_already_registered_email(user):
    return _send(
        user, 'AUTOforYOU: у вас вже є акаунт', 'users/email/already_registered.txt',
        {'login_url': f'{_site_url()}/login', 'reset_url': f'{_site_url()}/forgot-password'},
        'already_registered',
    )
