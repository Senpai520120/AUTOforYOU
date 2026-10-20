"""Точки расширения калькулятора (2.6, шаг 13).

Счётчик расчётов пишется в момент создания, а не по таблице Calculation: очистка анонимных расчётов
(pricing.tasks.purge_anonymous_calculations) статистику не уменьшает. Хранилище и record_metric - задача 8.7;
пока её нет, хук ничего не делает и расчёт не ломает. ПДн и IP не передаются.
"""
import logging

logger = logging.getLogger(__name__)


def on_calculation_saved(calculation) -> None:
    try:
        from reports.metrics import record_metric  # появится в задаче 8.7
    except ImportError:
        return
    try:
        record_metric('calculations')
    except Exception:
        logger.warning('pricing.hooks: не вдалося записати лічильник розрахунків', exc_info=True)
