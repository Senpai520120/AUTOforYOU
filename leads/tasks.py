import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from . import notify
from .models import Lead, LeadNotificationSettings, NotifyStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def _mark(lead: Lead, status: str, error: str = '') -> None:
    lead.telegram_status = status
    lead.telegram_error = error[:200]
    fields = ['telegram_status', 'telegram_error']
    if status == NotifyStatus.SENT:
        lead.telegram_sent_at = timezone.now()
        fields.append('telegram_sent_at')
    lead.save(update_fields=fields)


def _release(lead: Lead) -> None:
    Lead.objects.filter(pk=lead.pk, telegram_status=NotifyStatus.SENDING).update(
        telegram_status=NotifyStatus.PENDING)


def _in_app_once(lead: Lead, cfg: LeadNotificationSettings) -> None:
    if not cfg.notify_brokers_in_app or lead.broker_in_app_sent:
        return
    # Флаг ставится атомарно, чтобы повтор задачи не задвоил уведомления.
    if Lead.objects.filter(pk=lead.pk, broker_in_app_sent=False).update(broker_in_app_sent=True):
        lead.broker_in_app_sent = True
        notify.notify_brokers_in_app(f'Нова заявка {lead.public_id}', notify.cabinet_url(lead))


@shared_task(bind=True, name='leads.tasks.notify_broker_new_lead')
def notify_broker_new_lead(self, lead_id: int, force: bool = False):
    from telegram_bot import sender

    lead = Lead.objects.filter(pk=lead_id).first()
    if lead is None:
        logger.warning('lead.notify lead_id=%s not found', lead_id)
        return {'status': 'not_found'}
    cfg = LeadNotificationSettings.get_solo()
    _in_app_once(lead, cfg)

    if lead.telegram_status == NotifyStatus.SENT and not force:
        return {'status': 'already_sent'}

    chat_id = notify.broker_chat_id()
    if not cfg.telegram_enabled or not chat_id or not getattr(settings, 'TELEGRAM_BOT_TOKEN', ''):
        logger.warning('lead.notify lead_id=%s telegram not configured', lead_id)
        _mark(lead, NotifyStatus.SKIPPED)
        return {'status': NotifyStatus.SKIPPED}

    try:
        text = notify.render_new_lead_text(lead, cfg.new_lead_template)
    except notify.MessageTooLong:
        logger.warning('lead.notify lead_id=%s message_too_long', lead_id)
        _mark(lead, NotifyStatus.FAILED, 'message_too_long')
        return {'status': NotifyStatus.FAILED}
    except Exception as exc:  # битый шаблон из админки: {0}, {x.y}
        logger.warning('lead.notify lead_id=%s template_error=%s', lead_id, type(exc).__name__)
        _mark(lead, NotifyStatus.FAILED, 'template_error')
        return {'status': NotifyStatus.FAILED}

    # Telegram отклоняет не-https ссылки в кнопках (dev/localhost), поэтому без https кнопки нет.
    url = notify.cabinet_url(lead)
    buttons = [{'text': 'Відкрити заявку', 'url': url}] if url.startswith('https://') else None
    # Атомарный захват: второй параллельный запуск не шлёт дубль.
    claim = Lead.objects.filter(pk=lead.pk).exclude(telegram_status=NotifyStatus.SENDING)
    if not force:
        claim = claim.exclude(telegram_status=NotifyStatus.SENT)
    if not claim.update(telegram_status=NotifyStatus.SENDING):
        return {'status': 'in_progress'}
    # В eager-режиме (dev без Redis, тесты) self.retry не перезапускает задачу: повторяем в цикле.
    eager = bool(getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False))
    attempts = MAX_RETRIES + 1 if eager else 1
    try:
        for attempt in range(attempts):
            try:
                result = sender.send_message(chat_id, text, buttons=buttons)
                break
            except (OSError, ConnectionError):
                if attempt == attempts - 1:
                    raise
    except (OSError, ConnectionError) as exc:
        if eager or self.request.retries >= MAX_RETRIES:
            logger.warning('lead.notify lead_id=%s failed after retries', lead_id)
            _mark(lead, NotifyStatus.FAILED, type(exc).__name__)
            return {'status': NotifyStatus.FAILED}
        _release(lead)
        raise self.retry(exc=exc, countdown=30, max_retries=MAX_RETRIES)
    except Exception as exc:  # в т.ч. TelegramRetryAfter
        retry_after = getattr(exc, 'retry_after', None)
        if retry_after is not None and self.request.retries < MAX_RETRIES:
            # exc не передаём: в TelegramRetryAfter текст сообщения может содержать ПДн.
            _release(lead)
            raise self.retry(countdown=int(retry_after) + 1, max_retries=MAX_RETRIES)
        logger.warning('lead.notify lead_id=%s error=%s', lead_id, type(exc).__name__)
        _mark(lead, NotifyStatus.FAILED, type(exc).__name__)
        return {'status': NotifyStatus.FAILED}

    if result.ok:
        _mark(lead, NotifyStatus.SENT)
        return {'status': NotifyStatus.SENT}
    status = NotifyStatus.SKIPPED if result.reason == 'not_configured' else NotifyStatus.FAILED
    logger.warning('lead.notify lead_id=%s reason=%s', lead_id, result.reason)
    _mark(lead, status, '' if status == NotifyStatus.SKIPPED else result.reason)
    return {'status': status}


@shared_task(bind=True, name='leads.tasks.send_journal')
def send_journal_task(self, lead_id: int):
    """Запись в журнал-группу; независима от личного уведомления брокеру. Повтор без объекта исключения."""
    from .services import send_journal_message
    result = send_journal_message(lead_id)
    eager = bool(getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False))
    if result == 'failed' and not eager and self.request.retries < MAX_RETRIES:
        # Следующий шанс - периодическая задача resend_journal.
        raise self.retry(countdown=60 * (self.request.retries + 1), max_retries=MAX_RETRIES)
    return {'status': result}


RESEND_BATCH = 50
RESEND_MAX_AGE = timedelta(days=7)


@shared_task(name='leads.tasks.resend_journal')
def resend_journal():
    """Периодический досыл журнала для заявок без journal_message_id (старше N минут из админки)."""
    from .models import LeadJournalSettings
    from .services import send_journal_message

    if not str(getattr(settings, 'LEAD_JOURNAL_CHAT_ID', '') or '').strip():
        return {'sent': 0}
    now = timezone.now()
    older = now - timedelta(minutes=LeadJournalSettings.get_solo().journal_retry_minutes)
    ids = list(Lead.objects.filter(
        journal_message_id__isnull=True, created_at__lte=older, created_at__gte=now - RESEND_MAX_AGE,
    ).order_by('created_at').values_list('pk', flat=True)[:RESEND_BATCH])
    sent = sum(1 for pk in ids if send_journal_message(pk) == 'sent')
    return {'sent': sent, 'tried': len(ids)}
