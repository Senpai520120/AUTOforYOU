"""
Команда начального наполнения тарифных справочников.

Ставки растаможки (акциз, пошлина, НДС, пенсионный сбор):
  Источник: ставки растаможки Украины, актуальны на янв–июнь 2026.
  Финальный расчёт подтверждает таможенный брокер.

Ставки логистики (Copart/IAAI, фрахт) — ПЛЕЙСХОЛДЕРЫ, остаются блокерами.
Запуск: python manage.py seed_rates
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from pricing.models import (
    CustomsExciseRate, EuToUaDeliveryRate,
    ExchangeRate, OceanFreightRate, PensionFundBracket, UsLandRoute,
)

# ПРОВЕРИТЬ — прожиточный минимум 2026 (Украина, грн/месяц)
# https://minfin.com.ua/ua/economy/budget/subsistence/
LIVING_WAGE_UAH = Decimal('3028')


class Command(BaseCommand):
    help = 'Создаёт начальные тарифы (плейсхолдеры). Проверьте ставки растаможки!'

    def handle(self, *args, **options):
        today = date.today()

        # --- Аукционные сборы ---
        # Используй отдельную команду: python manage.py seed_auction_fees
        # (детальные сетки Copart/IAAI с member_type/payment_type/title_type)

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

        # --- Ставки акциза ---
        # Источник: ставки растаможки Украины, актуальны на янв–июнь 2026;
        # финал подтверждает таможенный брокер.
        # Формула ДВС: акциз = eur_per_100cc × (engine_cc/100) × age_coeff
        # Формула EV/PHEV: акциз = ev_excise_eur_per_kwh × battery_kwh
        # age_coeff = max(1, год_расчёта − год_выпуска) — см. calculator.calc_age_coeff()
        #
        # Бензин ≤3000 см³ → base 50 EUR/л = 5.0 EUR/100cc
        # Бензин >3000 см³ → base 100 EUR/л = 10.0 EUR/100cc
        # Дизель ≤3500 см³ → base 75 EUR/л = 7.5 EUR/100cc
        # Дизель >3500 см³ → base 150 EUR/л = 15.0 EUR/100cc
        # Электро/PHEV → 1 EUR/кВт·ч, пошлина 0%
        # Гибрид HEV → как бензин ≤3000 (гибриды — уточнить у брокера)
        excise_rates = [
            # (fuel_type, engine_cc_min, engine_cc_max, eur_per_100cc, ev_kwh, duty, vat)
            ('petrol',   0,    3000, '5.0000',  None,     '0.1000', '0.2000'),
            ('petrol',   3001, None, '10.0000', None,     '0.1000', '0.2000'),
            ('diesel',   0,    3500, '7.5000',  None,     '0.1000', '0.2000'),
            ('diesel',   3501, None, '15.0000', None,     '0.1000', '0.2000'),
            ('electric', 0,    None, '0.0000',  '1.0000', '0.0000', '0.2000'),
            ('phev',     0,    None, '0.0000',  '1.0000', '0.0000', '0.2000'),  # гибриды — уточнить у брокера
            ('hybrid',   0,    None, '5.0000',  None,     '0.1000', '0.2000'),  # HEV как бензин; уточнить у брокера
        ]
        for fuel, cc_min, cc_max, eur_per_100cc, ev_kwh, duty, vat in excise_rates:
            CustomsExciseRate.objects.get_or_create(
                fuel_type=fuel,
                engine_cc_min=cc_min,
                engine_cc_max=cc_max,
                defaults=dict(
                    eur_per_100cc=Decimal(eur_per_100cc),
                    ev_excise_eur_per_kwh=Decimal(ev_kwh) if ev_kwh else None,
                    duty_rate=Decimal(duty),
                    vat_rate=Decimal(vat),
                    valid_from=today,
                )
            )

        # --- Пенсионный сбор ---
        # Источник: ставки растаможки Украины, актуальны на янв–июнь 2026.
        # Пороги = кратное прожиточного минимума (LIVING_WAGE_UAH):
        #   ≤165×  → 3%  |  165×–290×  → 4%  |  >290×  → 5%
        # LIVING_WAGE_UAH = 3028 грн — ПРОВЕРИТЬ актуальный показатель на дату оформления.
        bracket_1 = (LIVING_WAGE_UAH * 165).quantize(Decimal('0.01'))   # ≈ 499 620 грн
        bracket_2 = (LIVING_WAGE_UAH * 290).quantize(Decimal('0.01'))   # ≈ 878 120 грн
        pension_brackets = [
            (Decimal('0'),   bracket_1, Decimal('0.0300')),
            (bracket_1,      bracket_2, Decimal('0.0400')),
            (bracket_2,      None,      Decimal('0.0500')),
        ]
        for min_v, max_v, rate in pension_brackets:
            PensionFundBracket.objects.get_or_create(
                min_value_uah=min_v,
                defaults=dict(max_value_uah=max_v, rate=rate, valid_from=today)
            )

        self.stdout.write(self.style.SUCCESS(
            'Тарифы созданы. Ставки акциза/пошлины/НДС — актуальны на янв–июнь 2026. '
            'Логистика (Copart/IAAI, фрахт) — плейсхолдеры, требуют уточнения у владельца. '
            'Прожиточный минимум (LIVING_WAGE_UAH) — ПРОВЕРИТЬ перед деплоем!'
        ))
