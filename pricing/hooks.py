"""Точки расширения калькулятора (2.6, шаг 13).

Счётчик расчётов пишется в момент создания, а не по таблице Calculation: очистка анонимных расчётов
(pricing.tasks.purge_anonymous_calculations) статистику не уменьшает. Хранилище и record_metric - metrics (8.7);
сбой записи расчёт не ломает. ПДн и IP не передаются.
"""
import logging

logger = logging.getLogger(__name__)


def on_calculation_saved(calculation) -> None:
    try:
        from metrics.models import MetricKey
        from metrics.services import record_metric
        record_metric(MetricKey.CALCULATION)
    except Exception:
        logger.warning('pricing.hooks: не вдалося записати лічильник розрахунків', exc_info=True)
