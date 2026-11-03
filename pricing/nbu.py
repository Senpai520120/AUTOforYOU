"""
Загрузка курсов в ExchangeRate через провайдера (`pricing/rates_provider.py`, режим `NBU_MODE`).
Используется management-командой, Celery-задачей и кнопкой в админке.

Сетевой сбой (URLError) и пустой/нечитаемый ответ (RatesUnavailable) пробрасываются:
вызывающий код решает, ретраиться или логировать. Ошибка пишется в IntegrationHealth.
"""
import logging
from datetime import date

from django.db import transaction

from integrations.base import MODE_DEMO, record_error, record_success
from pricing import cache as pricing_cache
from pricing.models import ExchangeRate, RateSource
from pricing.rates_provider import (
    SOURCE_DEMO,
    NbuRateProvider,
    RatesUnavailable,
    get_rate_provider,
)

logger = logging.getLogger(__name__)


def _save(quote, rate_date: date) -> bool:
    """Сохраняет курс; True, если строка создана или изменена. Ручной курс (manual) не затирается (A7)."""
    keys = dict(from_currency=quote.from_currency, to_currency=quote.to_currency, date=rate_date)
    row, created = ExchangeRate.objects.get_or_create(**keys, defaults={'rate': quote.rate, 'source': quote.source})
    if created:
        return True
    if quote.source == SOURCE_DEMO or row.source == RateSource.MANUAL:
        # Демо и автозагрузка никогда не затирают настоящий (nbu) или введённый вручную курс на ту же дату.
        return False
    if row.rate == quote.rate and row.source == quote.source:
        return False
    row.rate, row.source = quote.rate, quote.source
    row.save(update_fields=['rate', 'source'])
    return True


def fetch_and_save_rates(rate_date: date | None = None) -> list[str]:
    """
    Получает курсы у провайдера (НБУ или демо) и сохраняет с пометкой источника.

    Запись атомарна: при ошибке на любой валюте откатываются все (нет смеси дат).

    Returns:
        Список строк вида 'USD/UAH = 41.5' только для реально созданных или изменённых курсов;
        пустой, если NBU_MODE=off или всё уже актуально.

    Raises:
        URLError: сетевая ошибка. RatesUnavailable: пустой или нечитаемый ответ.
    """
    if rate_date is None:
        rate_date = date.today()
    provider = get_rate_provider()
    if provider is None:
        logger.info('NBU: загрузка курса пропущена (NBU_MODE выключает провайдера)')
        return []
    try:
        quotes = provider.fetch(rate_date)
        if not quotes:
            raise RatesUnavailable('источник курсов вернул пустой список')
        with transaction.atomic():
            changed = [q for q in quotes if _save(q, rate_date)]
    except Exception as exc:
        record_error('nbu', exc)
        raise
    if NbuRateProvider().resolution().mode != MODE_DEMO:
        record_success('nbu')
    return [f'{q.from_currency}/{q.to_currency} = {q.rate}' for q in changed]


def refresh_rates(rate_date: date | None = None) -> list[str]:
    """Загрузка курса + сброс кэша курсов: единая точка для задачи, команды и кнопки админки."""
    updated = fetch_and_save_rates(rate_date)
    if updated:
        pricing_cache.invalidate('exchange')
    return updated
