"""
Загрузка курсов в ExchangeRate через провайдера (`pricing/rates_provider.py`, режим `NBU_MODE`).
Используется management-командой, Celery-задачей и кнопкой в админке.

Сетевой сбой (URLError) и пустой/нечитаемый ответ (RatesUnavailable) пробрасываются:
вызывающий код решает, ретраиться или логировать. Ошибка пишется в IntegrationHealth.
"""
import logging
from datetime import date

from integrations.base import MODE_DEMO, record_error, record_success
from pricing import cache as pricing_cache
from pricing.models import ExchangeRate
from pricing.rates_provider import (
    SOURCE_DEMO,
    NbuRateProvider,
    RatesUnavailable,
    get_rate_provider,
)

logger = logging.getLogger(__name__)


def _save(quote, rate_date: date) -> None:
    keys = dict(from_currency=quote.from_currency, to_currency=quote.to_currency, date=rate_date)
    if quote.source == SOURCE_DEMO:
        # Демо никогда не затирает настоящий (nbu) или введённый вручную курс на ту же дату.
        ExchangeRate.objects.get_or_create(**keys, defaults={'rate': quote.rate, 'source': quote.source})
    else:
        ExchangeRate.objects.update_or_create(**keys, defaults={'rate': quote.rate, 'source': quote.source})


def fetch_and_save_rates(rate_date: date | None = None) -> list[str]:
    """
    Получает курсы у провайдера (НБУ или демо) и сохраняет с пометкой источника.

    Returns:
        Список строк вида 'USD/UAH = 41.5'; пустой, если NBU_MODE=off.

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
    except Exception as exc:
        record_error('nbu', exc)
        raise
    for quote in quotes:
        _save(quote, rate_date)
    if NbuRateProvider().resolution().mode != MODE_DEMO:
        record_success('nbu')
    return [f'{q.from_currency}/{q.to_currency} = {q.rate}' for q in quotes]


def refresh_rates(rate_date: date | None = None) -> list[str]:
    """Загрузка курса + сброс кэша курсов: единая точка для задачи, команды и кнопки админки."""
    updated = fetch_and_save_rates(rate_date)
    if updated:
        pricing_cache.invalidate('exchange')
    return updated
