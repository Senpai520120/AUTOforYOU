"""Celery-задачи еженедельного отчёта о воронке (9.50)."""
import logging

from celery import shared_task
from django.conf import settings

from core.tasks import ResilientTask

from . import reports

logger = logging.getLogger(__name__)

RETRY_AFTER_MAX_COUNTDOWN = 600


@shared_task(ignore_result=True)
def send_weekly_funnel_report(days: int = 7):
    reports.dispatch_report(reports.build_report(days))


@shared_task(base=ResilientTask, bind=True, ignore_result=True)
def send_funnel_report_telegram(self, text: str):
    """Сеть и flood control - повторы; отказ Telegram - падение, которое попадёт в FailedTask (8.9).

    Доставка «хотя бы раз»: при таймауте после приёма сообщения владелец получит копию. Там только счётчики.
    """
    from aiogram.exceptions import TelegramRetryAfter

    from telegram_bot import provider, sender

    if not provider.telegram_configured():
        logger.warning('funnel_report: Telegram не налаштовано')
        return
    retry_after = None
    try:
        result = sender.send_message(
            settings.FUNNEL_REPORT_CHAT_ID, text, parse_mode=None, demo_body='weekly funnel report')
    except TelegramRetryAfter as exc:
        retry_after = exc.retry_after  # в тексте исключения бывает chat_id, дальше он не идёт
    if retry_after is not None:
        if self.request.retries >= self.max_retries:
            raise ConnectionError('TelegramRetryAfter')
        raise self.retry(exc=ConnectionError('TelegramRetryAfter'),
                         countdown=min(int(retry_after) + 1, RETRY_AFTER_MAX_COUNTDOWN))
    if not result.ok:
        raise RuntimeError(f'Telegram відхилив звіт: {result.reason}')
