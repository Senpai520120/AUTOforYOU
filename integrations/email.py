"""Отправка писем через адаптер (задача 3.4a, 01-C3, 01-C7, 03-C10, Н-28).

`send_email(to, subject, body)` - единственная точка отправки писем проекта. Отправитель всегда
`settings.DEFAULT_FROM_EMAIL`. Режим - `EMAIL_MODE`:
- auto: real, если `EMAIL_BACKEND` - smtp и заданы `EMAIL_HOST` и `DEFAULT_FROM_EMAIL`; иначе «не налаштовано»;
- real: письма уходят в настроенный бекенд (smtp, в тестах locmem); консольный бекенд = ошибка конфигурации;
- demo: console + `OutboxMessage`, наружу ничего не уходит;
- off: письма не отправляются.

Отправка асинхронная (Celery `send_email_task`, таймаут `EMAIL_TIMEOUT`). Ошибки SMTP пишутся в
`IntegrationHealth`; адрес получателя и секреты в лог и журнал не попадают.
"""
import logging
import re

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from core.test_runner import ExternalNetworkBlocked

from .base import (
    MODE_DEMO,
    MODE_REAL,
    BaseProvider,
    ModeResolution,
    configured_mode,
    is_placeholder,
    mask_secrets,
    record_error,
    record_success,
    resolve_mode,
)

logger = logging.getLogger(__name__)

CONSOLE_BACKEND = 'django.core.mail.backends.console.EmailBackend'
LOCMEM_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_UNAVAILABLE_DETAIL = 'Відправка листів тимчасово не налаштована, зверніться до підтримки'

_EMAIL_RE = re.compile(r'[\w.+%-]+@[\w-]+(?:\.[\w-]+)+')


class EmailDeliveryError(OSError):
    """Сбой отправки (сеть, SMTP). OSError: Celery `ResilientTask` повторяет такие задачи."""


class EmailRejected(Exception):
    """Письмо не принято по не-сетевой причине (например, недопустимый заголовок). Не повторяется."""


def email_timeout() -> int:
    return int(getattr(settings, 'EMAIL_TIMEOUT', 10))


def _redact(text) -> str:
    """Убирает адреса и секреты: в журнал и лог не попадает получатель (03-S4)."""
    return _EMAIL_RE.sub('***', mask_secrets(text))


class EmailProvider(BaseProvider):
    key = 'email'
    title = 'Пошта (SMTP)'
    env_vars = ('EMAIL_BACKEND', 'EMAIL_HOST', 'DEFAULT_FROM_EMAIL', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD')
    checklist_anchor = '2.4'

    @staticmethod
    def _backend() -> str:
        return str(getattr(settings, 'EMAIL_BACKEND', '') or '')

    @staticmethod
    def _from_ok() -> bool:
        """Отправитель задан, не заглушка и не служебный домен (localhost, example.*): с него письма не доставятся."""
        value = str(getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip()
        if is_placeholder(value):
            return False
        domain = value.rsplit('@', 1)[-1].rstrip('>').lower()
        return not (domain == 'localhost' or domain.endswith('.localhost') or domain.startswith('example.'))

    def _smtp_ok(self) -> bool:
        """smtp-бекенд с заданным хостом (без хоста письма падают в воркере)."""
        host_ok = not is_placeholder(getattr(settings, 'EMAIL_HOST', ''))
        return 'smtp' in self._backend().lower() and host_ok

    def _real_backend_ok(self) -> bool:
        """Рабочий бекенд для real: smtp с хостом; locmem - только в тестах (IS_TESTING)."""
        if self._smtp_ok():
            return True
        return self._backend() == LOCMEM_BACKEND and bool(getattr(settings, 'IS_TESTING', False))

    def has_credentials(self) -> bool:
        return self._smtp_ok() and self._from_ok()

    def resolution(self) -> ModeResolution:
        if configured_mode(self.key) == 'real':
            if not self._from_ok():
                return ModeResolution(MODE_REAL, False, 'Помилка конфігурації: EMAIL_MODE=real, але немає DEFAULT_FROM_EMAIL')
            if self._backend() == CONSOLE_BACKEND:
                return ModeResolution(
                    MODE_REAL, False, 'Помилка конфігурації: EMAIL_MODE=real, але EMAIL_BACKEND - консольний',
                )
            if not self._real_backend_ok():
                return ModeResolution(
                    MODE_REAL, False, 'Помилка конфігурації: EMAIL_MODE=real потребує smtp-бекенд і EMAIL_HOST',
                )
            return ModeResolution(MODE_REAL, True, 'Налаштовано')
        res = resolve_mode(self.key, self.has_credentials(), env_vars=('EMAIL_BACKEND', 'EMAIL_HOST', 'DEFAULT_FROM_EMAIL'))
        if res.valid and not res.configured and res.reason.startswith('Не налаштовано'):
            return ModeResolution(
                res.mode, False, 'Не налаштовано: потрібні EMAIL_BACKEND (smtp), EMAIL_HOST, DEFAULT_FROM_EMAIL',
            )
        return res


def email_configured() -> bool:
    return EmailProvider().is_configured()


def _deliver_demo(to, subject, body) -> None:
    """Демо: тело и адрес - только в OutboxMessage (админка superuser). В stdout и лог - лишь тема."""
    from .models import write_outbox

    write_outbox('email', recipient=to, subject=subject, body=body)
    logger.info('Email (demo): «%s» записано в Outbox, адрес и тело в лог не выводятся', subject)


def deliver_email(to, subject, body) -> str:
    """Синхронная доставка по текущему режиму. Возвращает 'real', 'demo' или 'skipped'.

    Ошибки не глотаются: пишутся в IntegrationHealth (без адреса) и пробрасываются в обезличенном виде,
    чтобы Celery повторил задачу, а окончательная неудача попала в учёт упавших задач (8.9).
    """
    res = EmailProvider().resolution()
    if not res.configured:
        logger.info('Email не отправлен: %s', res.reason)
        return 'skipped'
    if res.mode == MODE_DEMO:
        _deliver_demo(to, subject, body)
        return 'demo'
    try:
        connection = get_connection(timeout=email_timeout())
        EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [to], connection=connection).send()
    except ExternalNetworkBlocked:
        raise
    except Exception as exc:
        safe = f'{type(exc).__name__}: {_redact(exc)}'
        record_error('email', EmailDeliveryError(safe))
        logger.warning('Email: ошибка отправки (%s)', type(exc).__name__)
        if isinstance(exc, OSError):
            raise EmailDeliveryError(safe) from None
        raise EmailRejected(safe) from None
    record_success('email')
    return 'real'


def send_email(to, subject, body, *, sync=False, raise_errors=False) -> dict:
    """Ставит письмо в очередь. Никогда не бросает исключение: бизнес-операция не падает из-за почты.

    Ответ: {'configured', 'queued', 'mode', 'reason'|'error'}. `configured: False` - письмо не поставлено,
    вызывающий код может предложить резервный канал (2.12) или показать «не налаштовано».
    `sync=True` - доставить сразу (кнопка «Надіслати тестовий лист»), ошибка вернётся в `error`.
    `raise_errors=True` (вместе с sync) - для кода внутри воркера: ошибка пробрасывается, Celery повторит задачу.
    """
    res = EmailProvider().resolution()
    if not res.configured:
        return {'configured': False, 'queued': False, 'mode': res.mode, 'reason': res.reason}
    result = {'configured': True, 'queued': True, 'mode': res.mode}
    try:
        if sync:
            deliver_email(to, subject, body)
        else:
            from .tasks import send_email_task
            send_email_task.delay(to, subject, body)
    except ExternalNetworkBlocked:
        raise
    except Exception as exc:
        if raise_errors:
            raise
        logger.warning('Email: письмо не отправлено (%s)', type(exc).__name__)
        return {**result, 'queued': False, 'error': type(exc).__name__}
    return result
