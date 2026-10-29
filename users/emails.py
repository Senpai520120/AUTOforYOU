"""Письма пользователю (задача 1.6). Тексты - в users/templates/users/email/*.txt.

Отправитель - settings.DEFAULT_FROM_EMAIL. Ошибка отправки логируется и не валит вызывающего.
Доставка - через адаптер почты `integrations.email.send_email` (3.4a): режим `EMAIL_MODE`, очередь Celery.
"""
import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from integrations.email import send_email

from .tokens import email_verification_token

logger = logging.getLogger(__name__)


def _site_url():
    return (settings.SITE_URL or '').rstrip('/')


def build_verification_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return f'{_site_url()}/verify-email?uid={uid}&token={token}'


def _send(user, subject, template, context, kind, to=None, direct=False):
    if not _site_url():
        logger.warning('SITE_URL не задан: письмо %s не отправлено', kind)
        return False
    body = render_to_string(template, context)
    # Адрес и ссылки в лог не попадают. Почта не настроена или очередь недоступна - вызывающий не падает.
    result = send_email(to or user.email, subject, body, sync=direct, raise_errors=direct)
    if not result['queued']:
        logger.warning('Письмо %s не поставлено в очередь (configured=%s)', kind, result['configured'])
    return result['queued']


def send_verification_email(user):
    if not _site_url():
        logger.warning('SITE_URL не задан: письмо verify_email не отправлено')
        return False
    return _send(
        user, 'AUTOforYOU: підтвердіть email', 'users/email/verify_email.txt',
        {'url': build_verification_url(user), 'ttl_hours': settings.EMAIL_VERIFY_TTL_HOURS},
        'verify_email',
    )


def build_password_reset_url(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f'{_site_url()}/password-reset/confirm?uid={uid}&token={token}'


def send_password_reset_email(user, direct=False):
    if not _site_url():
        logger.warning('SITE_URL не задан: письмо password_reset не отправлено')
        return False
    return _send(
        user, 'AUTOforYOU: скидання пароля', 'users/email/password_reset.txt',
        {'url': build_password_reset_url(user), 'ttl_minutes': max(1, settings.PASSWORD_RESET_TIMEOUT // 60)},
        'password_reset', direct=direct,
    )


def send_already_registered_email(user):
    return _send(
        user, 'AUTOforYOU: у вас вже є акаунт', 'users/email/already_registered.txt',
        {'login_url': f'{_site_url()}/login', 'reset_url': f'{_site_url()}/password-reset'},
        'already_registered',
    )


def send_account_deletion_scheduled_email(user, due_at):
    """Задача 1.8: письмо о запросе удаления со ссылкой на отмену (раздел «Мої дані»)."""
    return _send(
        user, 'AUTOforYOU: видалення акаунту заплановано', 'users/email/account_deletion_scheduled.txt',
        {'due_date': timezone.localtime(due_at).strftime('%d.%m.%Y'), 'cancel_url': f'{_site_url()}/me/data'},
        'account_deletion_scheduled',
    )


def send_account_deleted_email(email):
    """Задача 1.8: письмо после обезличивания. Адрес передаётся отдельно - в аккаунте его уже нет."""
    return _send(None, 'AUTOforYOU: акаунт видалено', 'users/email/account_deleted.txt', {}, 'account_deleted', to=email)
