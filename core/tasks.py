"""Базовый класс Celery-задач с повторами (задача 8.9).

Для сетевых задач, где потеря недопустима (письма, Telegram, алерты). Подключается явно:
`@shared_task(base=ResilientTask)`. Глобальная подмена task_cls не используется.
Параметры читаются из settings при каждом обращении (RESILIENT_TASK_MAX_RETRIES, RESILIENT_TASK_ACKS_LATE;
не CELERY_*: такие имена Celery применил бы ко всем задачам).
"""
import hashlib
import logging
import re
from datetime import timedelta

import httpx
from celery import Task, shared_task
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count
from django.utils import timezone

logger = logging.getLogger(__name__)


class ResilientTask(Task):
    abstract = True
    autoretry_for = (OSError, ConnectionError)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    @property
    def max_retries(self):
        return int(getattr(settings, 'RESILIENT_TASK_MAX_RETRIES', 3))

    @max_retries.setter
    def max_retries(self, value):  # Celery присваивает атрибут при создании класса задачи
        pass

    @property
    def acks_late(self):
        return bool(getattr(settings, 'RESILIENT_TASK_ACKS_LATE', True))

    @acks_late.setter
    def acks_late(self, value):
        pass


@shared_task(ignore_result=True)
def send_celery_heartbeat():
    """Пинг внешнего сервиса-сторожа (9.55): доходит, только если живы beat, Redis и worker.

    Нет пинга - сторож сам шлёт оповещение. Повторов нет: следующий пинг придёт по расписанию.
    Адрес содержит секрет, поэтому в лог идёт только тип ошибки.
    """
    url = settings.CELERY_HEARTBEAT_URL
    if not url:
        return
    try:
        httpx.get(url, timeout=10).raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.warning('Celery heartbeat: сторож не ответил (%s)', type(exc).__name__)


# Имя задачи - путь вида `app.tasks.name`; всё остальное в алерт не попадает (защита от мусора и ПДн в имени).
_TASK_NAME_RE = re.compile(r'^[A-Za-z0-9_.]{1,100}$')
ALERT_MAX_NAMES = 10


def _build_failed_task_alert(total: int, window_minutes: int, per_task) -> str:
    """Текст алерта: счётчик и имена задач. Без текста ошибок, аргументов, id и ПДн."""
    lines = [f'⚠ AUTOforYOU: упавших Celery-задач за {window_minutes} хв: {total}.']
    for name, count in per_task:
        shown = name if _TASK_NAME_RE.fullmatch(name) else '(назву приховано)'
        lines.append(f'• {shown}: {count}')
    lines.append('Деталі: адмінка, «Невдалі завдання»; що робити: docs/RUNBOOK.md.')
    return '\n'.join(lines)


def _send_failed_task_alert(text: str) -> bool:
    """Шлёт во все настроенные каналы. True - дошло хотя бы в один. Сбой канала не роняет задачу."""
    delivered = False
    chat_id = settings.FAILED_TASK_ALERT_CHAT_ID
    if chat_id:
        try:
            from telegram_bot import sender
            delivered |= bool(sender.send_message(chat_id, text, parse_mode=None, demo_body='failed task alert').ok)
        except Exception as exc:  # сеть, flood control: текст исключения может содержать chat_id
            logger.warning('failed_task_alert: Telegram не доставлено (%s)', type(exc).__name__)
    email = settings.FAILED_TASK_ALERT_EMAIL
    if email:
        try:
            from integrations.email import send_email
            result = send_email(email, 'AUTOforYOU: ростуть невдалі завдання', text)
            delivered |= bool(result.get('queued'))
        except Exception as exc:
            logger.warning('failed_task_alert: email не поставлено (%s)', type(exc).__name__)
    return delivered


@shared_task(ignore_result=True)
def alert_failed_task_growth():
    """Алерт владельцу, если за окно накопилось >= порога окончательно упавших задач (9.55).

    Окно и порог - FAILED_TASK_ALERT_WINDOW_MINUTES / _THRESHOLD. Тот же набор задач не шлётся чаще, чем раз
    в FAILED_TASK_ALERT_COOLDOWN_MINUTES (кэш). Без настроенного канала задача только пишет предупреждение.
    """
    from task_ledger.models import FailedTask

    window = int(settings.FAILED_TASK_ALERT_WINDOW_MINUTES)
    since = timezone.now() - timedelta(minutes=window)
    rows = FailedTask.objects.filter(failed_at__gte=since)
    total = rows.count()
    if total < int(settings.FAILED_TASK_ALERT_THRESHOLD):
        return
    per_task = list(rows.values_list('task_name').annotate(n=Count('id')).order_by('-n', 'task_name')[:ALERT_MAX_NAMES])
    # Ключ: все имена упавших задач (не только топ-10) и порядок величины счётчика: рост 5 -> 500 даёт новый алерт.
    all_names = sorted(rows.order_by('task_name').values_list('task_name', flat=True).distinct())
    names_key = hashlib.sha256(f"{'|'.join(all_names)}#{len(str(total))}".encode()).hexdigest()[:16]
    cache_key = f'core:failed_task_alert:{names_key}'
    cooldown = int(settings.FAILED_TASK_ALERT_COOLDOWN_MINUTES) * 60
    try:
        if not cache.add(cache_key, 1, timeout=cooldown):
            return  # такой алерт уже отправлен недавно
    except Exception:  # Redis недоступен: лучше повторить алерт, чем промолчать
        logger.warning('failed_task_alert: кэш недоступен, дедупликации нет')
    if not (settings.FAILED_TASK_ALERT_CHAT_ID or settings.FAILED_TASK_ALERT_EMAIL):
        logger.warning('failed_task_alert: упавших задач %s за %s хв, но канал алерта не настроен', total, window)
        return
    if not _send_failed_task_alert(_build_failed_task_alert(total, window, per_task)):
        try:
            cache.delete(cache_key)  # не дошло ни в один канал: следующий запуск попробует снова
        except Exception:
            logger.warning('failed_task_alert: кэш недоступен')
