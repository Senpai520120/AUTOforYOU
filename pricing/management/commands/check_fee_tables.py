"""Сверка действующих сборов аукционов в БД с CSV из репозитория (9.51, шаг b). Только чтение, без сети.

Код 1 - есть расхождение. Раз в квартал: открыть публичные страницы Copart и IAA (адреса в CSV, колонка
source_url), обновить CSV, прогнать эту команду, применить `seed_auction_fees --update`.
Запуск: python manage.py check_fee_tables [--date YYYY-MM-DD]
"""
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from pricing import fee_tables
from pricing.calculator import FEES_STALE_DAYS


class Command(BaseCommand):
    help = 'Сравнить действующие сборы аукционов в БД с pricing/data/*.csv (расхождение = код 1)'

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Дата, на которую сверять (по умолчанию сегодня), YYYY-MM-DD')

    def handle(self, *args, **options):
        on_date = date.fromisoformat(options['date']) if options['date'] else date.today()
        tier_rows = fee_tables.load_tier_rows()
        fixed_rows = fee_tables.load_fixed_rows()
        found = fee_tables.compare_with_db(on_date, tier_rows, fixed_rows)

        oldest = min(r['checked_at'] for r in (*tier_rows, *fixed_rows))
        age = (on_date - oldest).days
        self.stdout.write(f'CSV: тиров {len(tier_rows)}, фикс. сборов {len(fixed_rows)}; '
                          f'самая старая сверка с источником: {oldest} ({age} дн.).')
        if age > FEES_STALE_DAYS:
            self.stdout.write(self.style.WARNING(
                f'CSV сверен с сайтами аукционов больше {FEES_STALE_DAYS} дней назад: пора перечитать страницы.'))
        if not found:
            self.stdout.write(self.style.SUCCESS('БД совпадает с CSV.'))
            return
        for d in found:
            self.stdout.write(self.style.ERROR(str(d)))
        raise CommandError(f'Расхождений: {len(found)}. Применить CSV: python manage.py seed_auction_fees --update')
