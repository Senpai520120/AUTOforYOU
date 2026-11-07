"""
Management-команда: обновляет ExchangeRate из API НБУ (бесплатно, без ключа).

Источник: https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange
Поддерживает параметр --date YYYYMMDD для получения курса на конкретную дату.
Без параметра — текущий курс (сегодняшняя дата по НБУ).

Для растаможки важно: таможенная стоимость пересчитывается по курсу НБУ
на ДАТУ ОФОРМЛЕНИЯ (не «сегодня»), поэтому команда принимает дату явно.
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from pricing.nbu import refresh_rates
from pricing.tasks import NBU_RETRYABLE


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

        try:
            updated = refresh_rates(rate_date)
        except NBU_RETRYABLE as exc:
            raise CommandError(f'Ошибка запроса к НБУ: {type(exc).__name__}')

        if updated:
            for item in updated:
                self.stdout.write(self.style.SUCCESS(f'Обновлён: {item} на {rate_date}'))
            self.stdout.write(f'Готово. Обновлено: {", ".join(updated)}')
        else:
            self.stdout.write(self.style.WARNING('Ни один курс не обновлён.'))
