"""
Management-команда: обновляет ExchangeRate из API НБУ (бесплатно, без ключа).

Источник: https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange
Поддерживает параметр --date YYYYMMDD для получения курса на конкретную дату.
Без параметра — текущий курс (сегодняшняя дата по НБУ).

Для растаможки важно: таможенная стоимость пересчитывается по курсу НБУ
на ДАТУ ОФОРМЛЕНИЯ (не «сегодня»), поэтому команда принимает дату явно.
"""
import json
from datetime import date
from decimal import Decimal
from urllib.request import urlopen
from urllib.error import URLError

from django.core.management.base import BaseCommand, CommandError

from pricing.models import ExchangeRate


class Command(BaseCommand):
    help = 'Получить курсы USD/UAH и EUR/UAH из API НБУ и сохранить в ExchangeRate'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            metavar='YYYYMMDD',
            help='Дата курса в формате YYYYMMDD (по умолчанию: сегодня)',
        )

    def handle(self, *args, **options):
        raw_date = options.get('date')
        if raw_date:
            try:
                rate_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
            except (ValueError, IndexError):
                raise CommandError(f'Неверный формат даты: {raw_date!r}. Ожидается YYYYMMDD.')
        else:
            rate_date = date.today()

        date_str = rate_date.strftime('%Y%m%d')
        updated = []

        for valcode in ('USD', 'EUR'):
            url = (
                f'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange'
                f'?valcode={valcode}&date={date_str}&json'
            )
            try:
                with urlopen(url, timeout=10) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
            except URLError as exc:
                self.stderr.write(self.style.ERROR(f'Ошибка запроса {valcode}: {exc}'))
                continue

            if not data:
                self.stderr.write(self.style.WARNING(
                    f'НБУ вернул пустой ответ для {valcode} на {rate_date}. '
                    f'Возможно, нерабочий день или дата в будущем.'
                ))
                continue

            nbu_rate = Decimal(str(data[0]['rate']))

            obj, created = ExchangeRate.objects.update_or_create(
                from_currency=valcode,
                to_currency='UAH',
                date=rate_date,
                defaults={'rate': nbu_rate},
            )
            action = 'Создан' if created else 'Обновлён'
            updated.append(f'{valcode}/UAH = {nbu_rate}')
            self.stdout.write(self.style.SUCCESS(
                f'{action}: {valcode}/UAH = {nbu_rate} на {rate_date}'
            ))

        # USD/EUR — вычисляем через кросс-курс UAH: USD/EUR = USD_UAH / EUR_UAH
        usd_uah = ExchangeRate.objects.filter(
            from_currency='USD', to_currency='UAH', date=rate_date
        ).first()
        eur_uah = ExchangeRate.objects.filter(
            from_currency='EUR', to_currency='UAH', date=rate_date
        ).first()

        if usd_uah and eur_uah and eur_uah.rate:
            usd_eur = (usd_uah.rate / eur_uah.rate).quantize(Decimal('0.000001'))
            obj, created = ExchangeRate.objects.update_or_create(
                from_currency='USD',
                to_currency='EUR',
                date=rate_date,
                defaults={'rate': usd_eur},
            )
            action = 'Создан' if created else 'Обновлён'
            self.stdout.write(self.style.SUCCESS(
                f'{action}: USD/EUR = {usd_eur} на {rate_date} (кросс-курс)'
            ))
            updated.append(f'USD/EUR = {usd_eur}')

        if updated:
            self.stdout.write(f'Готово. Обновлено: {", ".join(updated)}')
        else:
            self.stdout.write(self.style.WARNING('Ни один курс не обновлён.'))
