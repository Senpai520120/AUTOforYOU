import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from core.tasks import ResilientTask

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
    """Личное уведомление брокеру: Telegram, затем (если Telegram не доставил) резервный email (2.12)."""
    lead = Lead.objects.filter(pk=lead_id).first()
    if lead is None:
        logger.warning('lead.notify lead_id=%s not found', lead_id)
        return {'status': 'not_found'}
    cfg = LeadNotificationSettings.get_solo()
    _in_app_once(lead, cfg)

    result = _telegram_step(self, lead, cfg, force)
    # Повтор Telegram (self.retry) сюда не доходит: письмо идёт после окончательного итога.
    if result['status'] not in ('in_progress', 'already_sent') and (
            result['status'] != NotifyStatus.SENT or force):
        # Аргумент - только id заявки: учёт упавших задач (8.9) хранит аргументы.
        notify_broker_email.delay(lead_id, force=force)
    return result


def _telegram_step(self, lead: Lead, cfg: LeadNotificationSettings, force: bool) -> dict:
    from telegram_bot import sender
    from telegram_bot.provider import telegram_configured

    lead_id = lead.pk
    if lead.telegram_status == NotifyStatus.SENT and not force:
        return {'status': 'already_sent'}

    chat_id = notify.broker_chat_id()
    if not cfg.telegram_enabled or not chat_id or not telegram_configured():
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
                result = sender.send_message(chat_id, text, buttons=buttons, demo_body=f'lead #{lead_id}')
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


def _mark_email(lead: Lead, status: str, error: str = '') -> None:
    lead.email_status = status
    lead.email_error = error[:200]
    fields = ['email_status', 'email_error']
    if status == NotifyStatus.SENT:
        lead.email_sent_at = timezone.now()
        fields.append('email_sent_at')
    lead.save(update_fields=fields)


def _finish_round(lead: Lead) -> None:
    """Конец круга доставки: если заявка не доставлена и есть что повторять, считаем попытку.
    Если оба канала не настроены, попытки не растут (досыл не зацикливается)."""
    lead.refresh_from_db(fields=['telegram_status', 'email_status'])
    if NotifyStatus.SENT in (lead.telegram_status, lead.email_status):
        return
    if lead.telegram_status == lead.email_status == NotifyStatus.SKIPPED:
        return
    Lead.objects.filter(pk=lead.pk).update(
        notify_attempts=F('notify_attempts') + 1, last_notify_attempt_at=timezone.now())


@shared_task(bind=True, base=ResilientTask, name='leads.tasks.notify_broker_email')
def notify_broker_email(self, lead_id: int, force: bool = False):
    """Резервное письмо брокеру через integrations.email.send_email (единственная точка отправки писем).

    Идемпотентна по email_status == sent. Работает в воркере, поэтому письмо уходит синхронно в
    рамках задачи (таймаут EMAIL_TIMEOUT), а итог (sent/failed) честно пишется в заявку.
    Лог и email_error - только lead_id и имя класса ошибки, без адресов, имени и телефона.
    """
    from integrations.email import send_email

    lead = Lead.objects.filter(pk=lead_id).first()
    if lead is None:
        return {'status': 'not_found'}
    if lead.email_status == NotifyStatus.SENT and not force:
        return {'status': 'already_sent'}
    claim = Lead.objects.filter(pk=lead.pk).exclude(email_status=NotifyStatus.SENDING)
    if not force:
        claim = claim.exclude(email_status=NotifyStatus.SENT)
    if not claim.update(email_status=NotifyStatus.SENDING):
        return {'status': 'in_progress'}

    status, error = NotifyStatus.FAILED, ''
    try:
        recipients = notify.broker_emails()
        if not recipients:
            status = NotifyStatus.SKIPPED
        else:
            try:
                subject, body = notify.render_new_lead_email(lead, LeadNotificationSettings.get_solo())
            except Exception as exc:  # битый шаблон из админки
                error = 'template_error'
                logger.warning('lead.email lead_id=%s template_error=%s', lead_id, type(exc).__name__)
            else:
                status, error = _send_to_all(send_email, recipients, subject, body, lead_id)
    except Exception as exc:
        status, error = NotifyStatus.FAILED, type(exc).__name__
        logger.warning('lead.email lead_id=%s error=%s', lead_id, type(exc).__name__)
    finally:
        # Любой выход, включая исключение: статус не должен остаться «sending».
        if Lead.objects.filter(pk=lead.pk, email_status=NotifyStatus.SENDING).exists():
            _mark_email(lead, status, error)
    if status == NotifyStatus.SKIPPED:
        logger.warning('lead.email lead_id=%s email not configured', lead_id)
    _finish_round(lead)
    return {'status': status}


def _send_to_all(send_email, recipients, subject, body, lead_id):
    """Письмо уходит на каждый адрес; итог sent, если принят хотя бы одним. Не настроена почта - skipped."""
    ok, skipped, error = 0, 0, ''
    for address in recipients:
        try:
            res = send_email(address, subject, body, sync=True)
        except Exception as exc:
            error = type(exc).__name__
            continue
        if not res.get('configured'):
            skipped += 1
        elif res.get('queued'):
            ok += 1
        else:
            error = str(res.get('error') or 'send_failed')
    if ok:
        # Часть адресов не приняла письмо: sent, но код ошибки виден в админке.
        return NotifyStatus.SENT, f'partial:{error}' if error else ''
    if skipped == len(recipients):
        return NotifyStatus.SKIPPED, ''
    logger.warning('lead.email lead_id=%s failed error=%s', lead_id, error)
    return NotifyStatus.FAILED, error or 'send_failed'


RESEND_NOTIFY_BATCH = 50


@shared_task(base=ResilientTask, name='leads.tasks.resend_undelivered_leads')
def resend_undelivered_leads():
    """Периодический досыл личного уведомления брокеру (Telegram + email) и предупреждение админам.

    Недоставлена = ни один канал не sent. Не повторяем, если оба канала не настроены (нечего повторять).
    Выборка под select_for_update(skip_locked) с отметкой времени попытки: второй воркер те же заявки не берёт.
    """
    now = timezone.now()
    cutoff = now - timedelta(minutes=int(settings.LEAD_NOTIFY_RETRY_MINUTES))
    max_attempts = int(settings.LEAD_NOTIFY_MAX_ATTEMPTS)
    skipped = NotifyStatus.SKIPPED
    undelivered = Lead.objects.exclude(telegram_status=NotifyStatus.SENT).exclude(
        email_status=NotifyStatus.SENT).exclude(telegram_status=skipped, email_status=skipped)

    with transaction.atomic():
        due = undelivered.filter(notify_attempts__lt=max_attempts).filter(
            Q(last_notify_attempt_at__lte=cutoff)
            | Q(last_notify_attempt_at__isnull=True, created_at__lte=cutoff))
        ids = list(due.select_for_update(skip_locked=True).order_by('created_at')
                   .values_list('pk', flat=True)[:RESEND_NOTIFY_BATCH])
        # Зависший «sending» (воркер упал посреди отправки): считаем попытку и возвращаем в «pending»,
        # иначе claim видит SENDING, задача отвечает in_progress, а попытки не растут.
        stuck = Q(telegram_status=NotifyStatus.SENDING) | Q(email_status=NotifyStatus.SENDING)
        stuck_ids = list(Lead.objects.filter(pk__in=ids).filter(stuck).values_list('pk', flat=True))
        Lead.objects.filter(pk__in=stuck_ids).update(notify_attempts=F('notify_attempts') + 1)
        Lead.objects.filter(pk__in=ids, telegram_status=NotifyStatus.SENDING).update(
            telegram_status=NotifyStatus.PENDING)
        Lead.objects.filter(pk__in=ids, email_status=NotifyStatus.SENDING).update(
            email_status=NotifyStatus.PENDING)
        Lead.objects.filter(pk__in=ids).update(last_notify_attempt_at=now)

    alerted = 0
    exhausted = undelivered.filter(notify_attempts__gte=max_attempts, undelivered_alerted_at__isnull=True)
    for lead in exhausted[:RESEND_NOTIFY_BATCH]:
        # Метка ставится атомарно: второй запуск не пришлёт то же предупреждение.
        if Lead.objects.filter(pk=lead.pk, undelivered_alerted_at__isnull=True).update(undelivered_alerted_at=now):
            notify.alert_admins_undelivered(lead)
            logger.warning('lead.undelivered lead_id=%s attempts=%s', lead.pk, lead.notify_attempts)
            alerted += 1

    for lead_id in ids:
        notify_broker_new_lead.delay(lead_id)  # повторяет Telegram и, если он не доставил, email
    return {'resent': len(ids), 'alerted': alerted}


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
