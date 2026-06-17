"""
Команда начального наполнения тарифных справочников.

Все ставки растаможки помечены # ПРОВЕРИТЬ по действующему законодательству Украины.
Запуск: python manage.py seed_rates
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from pricing.models import (
    AuctionFeeTier, CustomsExciseRate, EuToUaDeliveryRate,
    ExchangeRate, OceanFreightRate, PensionFundBracket, UsLandRoute,
)


class Command(BaseCommand):
    help = 'Создаёт начальные тарифы (плейсхолдеры). Проверьте ставки растаможки!'

    def handle(self, *args, **options):
        today = date.today()

        # --- Аукционные сборы Copart (упрощённая шкала) ---
        copart_tiers = [
            (Decimal('0'), Decimal('499.99'), Decimal('50'), Decimal('0')),
            (Decimal('500'), Decimal('999.99'), Decimal('75'), Decimal('0')),
            (Decimal('1000'), Decimal('1499.99'), Decimal('100'), Decimal('0')),
            (Decimal('1500'), Decimal('1999.99'), Decimal('125'), Decimal('0')),
            (Decimal('2000'), Decimal('2999.99'), Decimal('150'), Decimal('0')),
            (Decimal('3000'), Decimal('3999.99'), Decimal('175'), Decimal('0')),
            (Decimal('4000'), Decimal('4999.99'), Decimal('200'), Decimal('0')),
            (Decimal('5000'), None, Decimal('0'), Decimal('0.1000')),  # 10% от цены
        ]
        for min_p, max_p, fixed, pct in copart_tiers:
            AuctionFeeTier.objects.get_or_create(
                auction='copart', min_price_usd=min_p,
                defaults=dict(max_price_usd=max_p, fee_fixed_usd=fixed, fee_pct=pct, valid_from=today)
            )

        # IAAI — аналогично упрощённо
        AuctionFeeTier.objects.get_or_create(
            auction='iaai', min_price_usd=Decimal('0'),
            defaults=dict(max_price_usd=None, fee_fixed_usd=Decimal('0'),
                          fee_pct=Decimal('0.1000'), valid_from=today)
        )

        # --- Сухопутная логистика США ---
        routes = [
            ('general', 'houston', Decimal('500')),
            ('general', 'baltimore', Decimal('700')),
            ('general', 'new_jersey', Decimal('800')),
            ('california', 'houston', Decimal('900')),
            ('california', 'baltimore', Decimal('1100')),
        ]
        for location, port, cost in routes:
            UsLandRoute.objects.get_or_create(
                auction_location=location, us_port=port,
                defaults=dict(cost_usd=cost, valid_from=today)
            )

        # --- Морской фрахт ---
        ocean_routes = [
            ('houston', 'klaipeda', Decimal('1300')),
            ('houston', 'gdansk', Decimal('1250')),
            ('baltimore', 'klaipeda', Decimal('1100')),
            ('baltimore', 'gdansk', Decimal('1050')),
            ('new_jersey', 'klaipeda', Decimal('1050')),
            ('new_jersey', 'gdansk', Decimal('1000')),
        ]
        for us_port, eu_port, cost in ocean_routes:
            OceanFreightRate.objects.get_or_create(
                us_port=us_port, eu_port=eu_port,
                defaults=dict(cost_usd=cost, valid_from=today)
            )

        # --- Доставка ЕС → Украина ---
        for eu_port, cost in [('klaipeda', Decimal('350')), ('gdansk', Decimal('300'))]:
            EuToUaDeliveryRate.objects.get_or_create(
                eu_port=eu_port,
                defaults=dict(cost_usd=cost, valid_from=today)
            )

        # --- Курсы валют ---
        ExchangeRate.objects.get_or_create(
            from_currency='USD', to_currency='UAH', date=today,
            defaults=dict(rate=Decimal('41.50'))
        )
        ExchangeRate.objects.get_or_create(
            from_currency='USD', to_currency='EUR', date=today,
            defaults=dict(rate=Decimal('0.92'))
        )

        # --- Ставки акциза — ПРОВЕРИТЬ по действующему законодательству Украины ---
        excise_rates = [
            # (fuel_type, eur_per_100cc, age_0_1, age_1_3, age_3_5, age_5_7, age_7+, duty, vat)
            ('petrol', '0.7467', '1', '1', '1', '1.5', '2.25', '0.10', '0.20'),  # ПРОВЕРИТЬ
            ('diesel', '1.0304', '1', '1', '1', '1.5', '2.25', '0.10', '0.20'),  # ПРОВЕРИТЬ
            ('electric', '0.01', '1', '1', '1', '1', '1', '0', '0.20'),           # ПРОВЕРИТЬ
            ('hybrid', '0.7467', '1', '1', '1', '1.5', '2.25', '0.10', '0.20'),   # ПРОВЕРИТЬ
        ]
        for fuel, eur_per_100cc, c01, c13, c35, c57, c7p, duty, vat in excise_rates:
            CustomsExciseRate.objects.get_or_create(
                fuel_type=fuel,
                defaults=dict(
                    eur_per_100cc=Decimal(eur_per_100cc),
                    age_0_1_coeff=Decimal(c01),
                    age_1_3_coeff=Decimal(c13),
                    age_3_5_coeff=Decimal(c35),
                    age_5_7_coeff=Decimal(c57),
                    age_7_plus_coeff=Decimal(c7p),
                    duty_rate=Decimal(duty),
                    vat_rate=Decimal(vat),
                    valid_from=today,
                )
            )

        # --- Пенсионный сбор — ПРОВЕРИТЬ по действующему законодательству Украины ---
        pension_brackets = [
            (Decimal('0'), Decimal('375000'), Decimal('0.03')),           # ПРОВЕРИТЬ
            (Decimal('375000'), Decimal('750000'), Decimal('0.04')),       # ПРОВЕРИТЬ
            (Decimal('750000'), None, Decimal('0.05')),                    # ПРОВЕРИТЬ
        ]
        for min_v, max_v, rate in pension_brackets:
            PensionFundBracket.objects.get_or_create(
                min_value_uah=min_v,
                defaults=dict(max_value_uah=max_v, rate=rate, valid_from=today)
            )

        self.stdout.write(self.style.SUCCESS(
            'Тарифы созданы. ОБЯЗАТЕЛЬНО проверьте ставки акциза и пенсионного сбора '
            'по действующему законодательству Украины!'
        ))
