"""Точки расширения калькулятора (2.6, шаг 13; подключено в 8.7).

Счётчик расчётов пишется в момент создания, а не по таблице Calculation: очистка анонимных расчётов
(pricing.tasks.purge_anonymous_calculations) статистику не уменьшает. Вызывается из CalculateView
через transaction.on_commit и только на 201. ПДн и IP не передаются.
"""
from metrics.models import MetricKey
from metrics.services import record_metric


def on_calculation_saved(calculation) -> None:
    record_metric(MetricKey.CALCULATION)  # сам не падает: ошибки записи логирует record_metric
