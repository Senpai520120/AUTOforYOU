"""
Ядро логики получения курсов НБУ. Используется и management-командой, и Celery-задачей.

Бросает URLError при сетевой ошибке — вызывающий код решает, ретраиться или логировать.
"""
import json
from datetime import date
from decimal import Decimal
from urllib.request import urlopen

from pricing.models import ExchangeRate


def fetch_and_save_rates(rate_date: date | None = None) -> list[str]:
    """
    Получает USD/UAH, EUR/UAH из НБУ и вычисляет кросс-курс USD/EUR.

    Returns:
        Список строк вида 'USD/UAH = 41.5' для каждого обновлённого курса.

    Raises:
        URLError: при сетевой ошибке (HTTP или timeout).
    """
    if rate_date is None:
        rate_date = date.today()

    date_str = rate_date.strftime('%Y%m%d')
    updated: list[str] = []

    for valcode in ('USD', 'EUR'):
        url = (
            f'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange'
            f'?valcode={valcode}&date={date_str}&json'
        )
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        if not data:
            continue

        nbu_rate = Decimal(str(data[0]['rate']))
        ExchangeRate.objects.update_or_create(
            from_currency=valcode,
            to_currency='UAH',
            date=rate_date,
            defaults={'rate': nbu_rate},
        )
        updated.append(f'{valcode}/UAH = {nbu_rate}')

    # Кросс-курс USD/EUR через UAH
    usd_uah = ExchangeRate.objects.filter(
        from_currency='USD', to_currency='UAH', date=rate_date
    ).first()
    eur_uah = ExchangeRate.objects.filter(
        from_currency='EUR', to_currency='UAH', date=rate_date
    ).first()

    if usd_uah and eur_uah and eur_uah.rate:
        usd_eur = (usd_uah.rate / eur_uah.rate).quantize(Decimal('0.000001'))
        ExchangeRate.objects.update_or_create(
            from_currency='USD',
            to_currency='EUR',
            date=rate_date,
            defaults={'rate': usd_eur},
        )
        updated.append(f'USD/EUR = {usd_eur}')

    return updated
