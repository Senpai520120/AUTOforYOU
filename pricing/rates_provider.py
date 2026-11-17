"""Провайдеры курсов валют (задача 3.4a): НБУ и демо.

`ExchangeRateProvider.fetch(date) -> list[RateQuote]`. Режим - `NBU_MODE`: auto и real = НБУ (ключ не нужен),
demo = фиксированные демо-курсы с `source='demo'`, off = загрузка выключена.
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings

from integrations.base import MODE_DEMO, MODE_REAL, BaseProvider, http_timeout

SOURCE_NBU = 'nbu'
SOURCE_DEMO = 'demo'

DEMO_USD_UAH = Decimal('41.50')
DEMO_USD_EUR = Decimal('0.92')
CROSS_PLACES = Decimal('0.000001')
MAX_RESPONSE_BYTES = 1_000_000


def _reject_constant(name):
    raise ValueError(f'недопустимая константа JSON: {name}')


class RatesUnavailable(Exception):
    """Пустой или нечитаемый ответ источника курсов. Задача Celery такие сбои повторяет (02-Q13)."""


@dataclass(frozen=True)
class RateQuote:
    from_currency: str
    to_currency: str
    rate: Decimal
    source: str


class ExchangeRateProvider(ABC):
    @abstractmethod
    def fetch(self, rate_date: date) -> list[RateQuote]:
        """Курсы на дату. Пустой результат недопустим: источник бросает RatesUnavailable."""


class NbuRateProvider(ExchangeRateProvider, BaseProvider):
    """Курс НБУ (бесплатно, без ключа). URL - `NBU_API_URL`, таймаут - общий таймаут провайдеров."""
    key = 'nbu'
    title = 'Курс НБУ'
    env_vars = ('NBU_API_URL',)
    needs_credentials = False
    checklist_anchor = '2.5'

    def _request(self, valcode: str, rate_date: date) -> list:
        query = urlencode({'valcode': valcode, 'date': rate_date.strftime('%Y%m%d')}) + '&json'
        url = f'{settings.NBU_API_URL.rstrip("/")}?{query}'
        with urlopen(url, timeout=http_timeout()) as resp:  # noqa: S310 - URL из настроек владельца
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RatesUnavailable(f'НБУ {valcode}: ответ слишком большой')
        try:
            data = json.loads(raw.decode('utf-8'), parse_float=Decimal, parse_constant=_reject_constant)
        except ValueError as exc:
            raise RatesUnavailable(f'НБУ {valcode}: ответ не JSON') from exc
        if not isinstance(data, list) or not data:
            raise RatesUnavailable(f'НБУ {valcode}: пустой ответ на {rate_date.isoformat()}')
        return data

    def _rate(self, valcode: str, rate_date: date) -> Decimal:
        data = self._request(valcode, rate_date)
        try:
            rate = Decimal(str(data[0]['rate']))
        except (KeyError, TypeError, IndexError, InvalidOperation) as exc:
            raise RatesUnavailable(f'НБУ {valcode}: неожиданный формат ответа') from exc
        if not rate.is_finite() or rate <= 0:
            raise RatesUnavailable(f'НБУ {valcode}: курс не положительный')
        return rate

    def fetch(self, rate_date: date) -> list[RateQuote]:
        usd = self._rate('USD', rate_date)
        eur = self._rate('EUR', rate_date)
        cross = (usd / eur).quantize(CROSS_PLACES)
        return [
            RateQuote('USD', 'UAH', usd, SOURCE_NBU),
            RateQuote('EUR', 'UAH', eur, SOURCE_NBU),
            RateQuote('USD', 'EUR', cross, SOURCE_NBU),
        ]


class DemoRateProvider(ExchangeRateProvider):
    """Фиксированные демо-курсы. Всегда `source='demo'`: калькулятор показывает демо-пометку."""

    def fetch(self, rate_date: date) -> list[RateQuote]:
        return [
            RateQuote('USD', 'UAH', DEMO_USD_UAH, SOURCE_DEMO),
            RateQuote('USD', 'EUR', DEMO_USD_EUR, SOURCE_DEMO),
        ]


def get_rate_provider() -> ExchangeRateProvider | None:
    """Провайдер по `NBU_MODE`; None - загрузка выключена (off или недопустимое значение)."""
    mode = NbuRateProvider().resolution().mode
    if mode == MODE_DEMO:
        return DemoRateProvider()
    if mode == MODE_REAL:
        return NbuRateProvider()
    return None
