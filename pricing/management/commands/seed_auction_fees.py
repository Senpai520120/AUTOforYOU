"""
Сетки аукционных сборов Copart и IAAI.

Два источника (9.51):
- публичные страницы аукционов, снятые вручную в CSV `pricing/data/` (с `source_url` и `checked_at`):
  Copart public и licensed (<25 авто/год), IAA public, фиксированные сборы Copart и IAA, virtual bid по цене;
- baseline в этом файле, помечен «# baseline»: брокерская сетка Copart, лицензионная сетка IAA, IAA environmental.
  Публичного источника для них нет: реальные ставки - тариф вашего брокера.
Запуск: python manage.py seed_auction_fees [--clear] [--force] [--update]

Безопасность старта контейнера (1.18, E2): каждая таблица (AuctionFeeTier, AuctionFixedFee) засевается
только если пуста. Удалённые и закрытые админом записи не воскрешаются. `--force` досоздаёт недостающие
записи по ключу (без valid_from) и печатает, сколько создано.
`--update` приводит ставки из CSV к актуальным: расходящиеся действующие записи закрываются датой «по»,
новые создаются, ничего не удаляется (правки в админке для групп CSV будут закрыты, группы вне CSV не трогаются).
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from pricing import fee_tables
from pricing.models import AuctionFeeTier, AuctionFixedFee

TODAY = date(2026, 1, 1)   # baseline-дата; актуализировать перед деплоем


class Command(BaseCommand):
    help = 'Создаёт baseline-сетки buyer fee Copart/IAAI (сверить с тарифом брокера!)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Удалить все существующие записи перед заполнением',
        )
        parser.add_argument(
            '--update', action='store_true',
            help='Привести ставки из CSV (публичные страницы) к актуальным: закрыть расходящиеся, создать новые.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Досоздать недостающие записи и в непустых таблицах',
        )

    def handle(self, *args, **options):
        if options['update']:
            result = fee_tables.apply_csv()
            self.stdout.write(self.style.SUCCESS(
                'Сетки из CSV применены: '
                f"тиры закрыто {result['tiers_closed']}, создано {result['tiers_created']}; "
                f"фикс. сборы закрыто {result['fixed_closed']}, создано {result['fixed_created']}."
            ))
            return

        if options['clear']:
            AuctionFeeTier.objects.all().delete()
            AuctionFixedFee.objects.all().delete()
            self.stdout.write('Существующие записи удалены.')

        # Решение «сеять или пропустить» - один раз до заполнения (иначе вторая сетка видела бы первую).
        self.seed_tiers = options['force'] or not AuctionFeeTier.objects.exists()
        self.seed_fixed = options['force'] or not AuctionFixedFee.objects.exists()
        if not self.seed_tiers:
            self.stdout.write('  AuctionFeeTier: пропущено, справочник не пуст.')
        if not self.seed_fixed:
            self.stdout.write('  AuctionFixedFee: пропущено, справочник не пуст.')

        self._seed_csv()
        self._seed_copart_broker()
        self._seed_iaai_licensed()
        self._seed_iaai_fixed_fees()

        self.stdout.write(self.style.SUCCESS(
            'Baseline-сетки созданы. '
            'ВАЖНО: сверить с офиц. прайс-листом аукциона и тарифом брокера!'
        ))

    # ── Публичные страницы (CSV) ──────────────────────────────────────────────

    def _seed_csv(self):
        """Ставки с `source_url`/`checked_at` из pricing/data/*.csv; создаются только недостающие по ключу."""
        if self.seed_tiers:
            count = 0
            for row in fee_tables.load_tier_rows():
                key = {f: row[f] for f in fee_tables.TIER_KEY}
                if not AuctionFeeTier.objects.filter(**key).exists():
                    AuctionFeeTier.objects.create(**{f: row[f] for f in fee_tables.TIER_CREATE})
                    count += 1
            self.stdout.write(f'  buyer fee из CSV: {count} тиров создано.')
        if self.seed_fixed:
            count = 0
            for row in fee_tables.load_fixed_rows():
                key = {f: row[f] for f in fee_tables.FIXED_KEY}
                if not AuctionFixedFee.objects.filter(**key).exists():
                    AuctionFixedFee.objects.create(**{f: row[f] for f in fee_tables.FIXED_CREATE})
                    count += 1
            self.stdout.write(f'  фикс. сборы из CSV: {count} создано.')

    # ── Copart, broker (baseline: публичной страницы нет) ─────────────────────

    def _seed_copart_broker(self):
        """
        Copart broker, secured/unsecured. Публичной сетки нет: тариф брокера.
        ~6% от ставки (min ~$100 → выражен через flat для нижнего диапазона).
        # baseline — сверить с офиц. сеткой и тарифом брокера
        """
        for member in ('broker',):
            secured_tiers = [
                # $0–1666: flat $100 (6% от 1666 ≈ $100 — выражен через floor)
                (0,    1666,  100,   None),   # baseline min fee
                (1667, None,  None,  '0.0600'),  # 6% baseline
            ]
            self._bulk_create_tiers('copart', member, 'secured', 'any', secured_tiers)

            # unsecured — дороже (~8%)
            unsecured_tiers = [
                (0,    1249,  100,   None),   # baseline
                (1250, None,  None,  '0.0800'),  # 8% baseline
            ]
            self._bulk_create_tiers('copart', member, 'unsecured', 'any', unsecured_tiers)

    # ── IAAI, licensed ────────────────────────────────────────────────────────

    def _seed_iaai_licensed(self):
        """
        IAAI licensed/broker buyer fee (публичная сетка IAA public - в CSV).
        IAAI не различает title_type в тиерах → 'any'.
        # baseline — сверить с офиц. сеткой IAAI и тарифом брокера
        """
        licensed_tiers = [
            (0,     499,   75,   None),   # baseline
            (500,   999,   100,  None),   # baseline
            (1000,  1499,  125,  None),   # baseline
            (1500,  1999,  150,  None),   # baseline
            (2000,  2999,  200,  None),   # baseline
            (3000,  3999,  250,  None),   # baseline
            (4000,  4999,  325,  None),   # baseline
            (5000,  7499,  None, '0.0800'),  # 8% baseline
            (7500,  None,  None, '0.1000'),  # 10% baseline (нелицензионные доп. %)
        ]
        for member in ('licensed', 'broker'):
            self._bulk_create_tiers('iaai', member, 'secured', 'any', licensed_tiers)

    # ── Фиксированные сборы IAAI ──────────────────────────────────────────────

    def _seed_iaai_fixed_fees(self):
        """
        IAAI: service fee, title handling и internet bid - в CSV (страница IAA, с 01.10.2026).
        EH&S and Fuel Surcharge страница суммой не называет: $15 - baseline.
        # baseline — сверить с тарифом брокера
        """
        fixed = [
            ('environmental', 'any', '15.00'),  # baseline: сумма EH&S surcharge не опубликована
        ]
        self._bulk_create_fixed('iaai', fixed)

    # ── Вспомогательные методы ────────────────────────────────────────────────

    def _bulk_create_tiers(self, auction, member_type, payment_type, title_type, tiers):
        if not self.seed_tiers:
            return
        count = 0
        for bid_min, bid_max, fee_flat, fee_percent in tiers:
            key = dict(auction=auction, member_type=member_type, payment_type=payment_type,
                       title_type=title_type, bid_min=Decimal(str(bid_min)))
            if AuctionFeeTier.objects.filter(**key).exists():
                continue
            AuctionFeeTier.objects.create(
                **key,
                bid_max=Decimal(str(bid_max)) if bid_max is not None else None,
                fee_flat=Decimal(str(fee_flat)) if fee_flat is not None else None,
                fee_percent=Decimal(fee_percent) if fee_percent is not None else None,
                valid_from=TODAY,
            )
            count += 1
        self.stdout.write(f'  {auction}/{member_type}/{payment_type}/{title_type}: {count} тиров создано.')

    def _bulk_create_fixed(self, auction, fees):
        if not self.seed_fixed:
            return
        count = 0
        for fee_type, title_type, amount in fees:
            key = dict(auction=auction, fee_type=fee_type, title_type=title_type)
            if AuctionFixedFee.objects.filter(**key).exists():
                continue
            AuctionFixedFee.objects.create(**key, amount=Decimal(amount), valid_from=TODAY)
            count += 1
        self.stdout.write(f'  {auction} fixed fees: {count} создано.')
