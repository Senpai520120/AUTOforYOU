"""Единая точка записи счётчиков (8.7). Принимает только ключ: никаких идентификаторов людей и запросов."""
import logging

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import DailyMetric, MetricKey

logger = logging.getLogger(__name__)


def record_metric(key: str, amount: int = 1, day=None) -> None:
    """Атомарный инкремент счётчика за день (по Europe/Kyiv). Ошибка логируется и не ломает операцию."""
    try:
        key = MetricKey(key).value
        day = day or timezone.localdate()
        with transaction.atomic():
            updated = DailyMetric.objects.filter(date=day, key=key).update(value=F('value') + amount)
            if updated:
                return
            try:
                with transaction.atomic():
                    DailyMetric.objects.create(date=day, key=key, value=amount)
            except IntegrityError:  # строку успел создать параллельный запрос
                DailyMetric.objects.filter(date=day, key=key).update(value=F('value') + amount)
    except Exception:
        logger.warning('metrics: не вдалося записати лічильник %s', key, exc_info=True)


def record_metric_on_commit(key: str) -> None:
    """Засчитать событие только после фиксации транзакции: откат операции счётчик не меняет."""
    transaction.on_commit(lambda: record_metric(key))
