"""Единая точка записи счётчиков (8.7).

Принимает только ключ и количество: никаких user, IP и иных идентификаторов.
Запись идёт после фиксации транзакции (откатившаяся операция не засчитывается),
любая ошибка логируется без данных и не пробрасывается в бизнес-операцию.
"""
import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import DailyMetric, MetricKey

logger = logging.getLogger(__name__)

_ATTEMPTS = 3


def _increment(key: str, amount: int, day) -> None:
    try:
        for _ in range(_ATTEMPTS):
            try:
                with transaction.atomic():
                    DailyMetric.objects.get_or_create(date=day, key=key, defaults={'value': 0})
                    DailyMetric.objects.filter(date=day, key=key).update(value=F('value') + amount)
                return
            except IntegrityError:
                continue  # гонка за создание строки: повторяем, строка уже есть
        logger.warning('metrics.record_failed key=%s reason=integrity', key)
    except Exception:
        logger.warning('metrics.record_failed key=%s', key, exc_info=True)


def record_metric(key, amount: int = 1, day=None) -> None:
    """Увеличивает счётчик key за день (по умолчанию - сегодня по TIME_ZONE, Europe/Kyiv). Не бросает."""
    try:
        key = str(key)
        if key not in MetricKey.values:
            logger.warning('metrics.unknown_key key=%s', key)
            return
        day = day or timezone.localdate()
        transaction.on_commit(lambda: _increment(key, amount, day))
    except Exception:
        logger.warning('metrics.record_failed', exc_info=True)
