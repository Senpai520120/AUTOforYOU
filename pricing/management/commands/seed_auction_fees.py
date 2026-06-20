"""
Baseline-сетки аукционных сборов Copart и IAAI.

ВАЖНО: все числа помечены «# baseline».
Реальные ставки — тариф вашего брокера или офиц. прайс-лист аукциона.
Запуск: python manage.py seed_auction_fees [--clear]
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from pricing.models import AuctionFeeTier, AuctionFixedFee

TODAY = date(2026, 1, 1)   # baseline-дата; актуализировать перед деплоем


class Command(BaseCommand):
    help = 'Создаёт baseline-сетки buyer fee Copart/IAAI (сверить с тарифом брокера!)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Удалить все существующие записи перед заполнением',
        )

    def handle(self, *args, **options):
        if options['clear']:
            AuctionFeeTier.objects.all().delete()
            AuctionFixedFee.objects.all().delete()
            self.stdout.write('Существующие записи удалены.')

        self._seed_copart_public_salvage_secured()
        self._seed_copart_licensed_broker()
        self._seed_copart_public_unsecured()
        self._seed_iaai_licensed()
        self._seed_copart_fixed_fees()
        self._seed_iaai_fixed_fees()

        self.stdout.write(self.style.SUCCESS(
            'Baseline-сетки созданы. '
            'ВАЖНО: сверить с офиц. прайс-листом аукциона и тарифом брокера!'
        ))

    # ── Copart, public, salvage, secured ─────────────────────────────────────

    def _seed_copart_public_salvage_secured(self):
        """
        Copart buyer fee для публичных покупателей, salvage, обеспечённый счёт.
        Источник: офиц. сайт Copart (approximation).
        # baseline — сверить с офиц. сеткой и тарифом брокера
        """
        tiers = [
            # (bid_min, bid_max,  fee_flat, fee_percent)
            (0,     399,    75,    None),   # baseline
            (400,   899,    135,   None),   # baseline
            (900,   1399,   185,   None),   # baseline
            (1400,  1999,   235,   None),   # baseline
            (2000,  2499,   285,   None),   # baseline
            (2500,  2999,   335,   None),   # baseline
            (3000,  3499,   385,   None),   # baseline
            (3500,  3999,   435,   None),   # baseline
            (4000,  4499,   485,   None),   # baseline
            (4500,  4999,   535,   None),   # baseline
            (5000,  None,   None,  '0.1000'),  # 10% baseline
        ]
        self._bulk_create_tiers('copart', 'public', 'secured', 'salvage', tiers)

    # ── Copart, licensed + broker ─────────────────────────────────────────────

    def _seed_copart_licensed_broker(self):
        """
        Copart licensed/broker, secured.
        ~6% от ставки (min ~$100 → выражен через flat для нижнего диапазона).
        # baseline — сверить с офиц. сеткой и тарифом брокера
        """
        for member in ('licensed', 'broker'):
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

    # ── Copart, public, unsecured ─────────────────────────────────────────────

    def _seed_copart_public_unsecured(self):
        """
        Copart public, unsecured — дороже secured.
        # baseline — сверить с офиц. сеткой и тарифом брокера
        """
        tiers = [
            (0,    399,   100,   None),   # baseline
            (400,  899,   175,   None),   # baseline
            (900,  1399,  225,   None),   # baseline
            (1400, 1999,  300,   None),   # baseline
            (2000, 2999,  375,   None),   # baseline
            (3000, 3999,  450,   None),   # baseline
            (4000, 4999,  525,   None),   # baseline
            (5000, None,  None,  '0.1100'),  # 11% baseline
        ]
        self._bulk_create_tiers('copart', 'public', 'unsecured', 'salvage', tiers)

    # ── IAAI, licensed ────────────────────────────────────────────────────────

    def _seed_iaai_licensed(self):
        """
        IAAI licensed dealer buyer fee.
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

        # IAAI public — упрощённо выше licensed
        public_tiers = [
            (0,    499,   100,  None),   # baseline
            (500,  999,   150,  None),   # baseline
            (1000, 1999,  225,  None),   # baseline
            (2000, 3999,  350,  None),   # baseline
            (4000, None,  None, '0.0900'),  # 9% baseline
        ]
        self._bulk_create_tiers('iaai', 'public', 'secured', 'any', public_tiers)

    # ── Фиксированные сборы Copart ────────────────────────────────────────────

    def _seed_copart_fixed_fees(self):
        """
        Copart фиксированные сборы.
        # baseline — сверить с офиц. сеткой и тарифом брокера
        """
        fixed = [
            # (fee_type, title_type, amount)
            ('gate', 'clean',   '79.00'),   # gate clean baseline
            ('gate', 'salvage', '95.00'),   # gate salvage baseline
            ('environmental', 'any', '10.00'),  # baseline
            ('virtual_bid',   'any', '99.00'),  # baseline
        ]
        self._bulk_create_fixed('copart', fixed)

    # ── Фиксированные сборы IAAI ──────────────────────────────────────────────

    def _seed_iaai_fixed_fees(self):
        """
        IAAI фиксированные сборы.
        # baseline — сверить с офиц. сеткой IAAI и тарифом брокера
        """
        fixed = [
            ('gate',          'any', '95.00'),  # service fee baseline
            ('environmental', 'any', '15.00'),  # baseline
            ('virtual_bid',   'any', '75.00'),  # baseline (29–89 range; берём середину)
        ]
        self._bulk_create_fixed('iaai', fixed)

    # ── Вспомогательные методы ────────────────────────────────────────────────

    def _bulk_create_tiers(self, auction, member_type, payment_type, title_type, tiers):
        count = 0
        for bid_min, bid_max, fee_flat, fee_percent in tiers:
            _, created = AuctionFeeTier.objects.get_or_create(
                auction=auction,
                member_type=member_type,
                payment_type=payment_type,
                title_type=title_type,
                bid_min=Decimal(str(bid_min)),
                defaults=dict(
                    bid_max=Decimal(str(bid_max)) if bid_max is not None else None,
                    fee_flat=Decimal(str(fee_flat)) if fee_flat is not None else None,
                    fee_percent=Decimal(fee_percent) if fee_percent is not None else None,
                    valid_from=TODAY,
                ),
            )
            if created:
                count += 1
        self.stdout.write(f'  {auction}/{member_type}/{payment_type}/{title_type}: {count} тиров создано.')

    def _bulk_create_fixed(self, auction, fees):
        count = 0
        for fee_type, title_type, amount in fees:
            _, created = AuctionFixedFee.objects.get_or_create(
                auction=auction,
                fee_type=fee_type,
                title_type=title_type,
                defaults=dict(amount=Decimal(amount), valid_from=TODAY),
            )
            if created:
                count += 1
        self.stdout.write(f'  {auction} fixed fees: {count} создано.')
