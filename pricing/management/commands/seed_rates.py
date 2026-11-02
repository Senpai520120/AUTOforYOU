"""
Команда начального наполнения тарифных справочников.

Ставки растаможки (акциз, пошлина, НДС, пенсионный сбор):
  Источник: ставки растаможки Украины, актуальны на янв–июнь 2026.
  Финальный расчёт подтверждает таможенный брокер.

Ставки логистики (Copart/IAAI, фрахт) — ПЛЕЙСХОЛДЕРЫ, остаются блокерами.
Запуск: python manage.py seed_rates [--force]

Безопасность старта контейнера (1.18, E1/E2): каждый справочник засевается только если его таблица
пуста. Удалённые и закрытые админом записи не воскрешаются, дублей нет. Демо-курс - только при пустой
ExchangeRate или NBU_MODE=demo. `--force` досоздаёт недостающие записи по ключу (без valid_from)
и печатает, что создано.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand

from pricing.models import (
    CustomsCalcRule,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UsLandRoute,
)
from pricing.rates_provider import DemoRateProvider

# ПРОВЕРИТЬ — прожиточный минимум 2026 (Украина, грн/месяц)
# https://minfin.com.ua/ua/economy/budget/subsistence/
LIVING_WAGE_UAH = Decimal('3028')


class Command(BaseCommand):
    help = ('Создаёт начальные тарифы (плейсхолдеры) в пустых справочниках. '
            '--force: досоздать недостающие записи. Проверьте ставки растаможки!')

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Досоздать недостающие записи и в непустых справочниках')

    def _should_seed(self, model, force):
        """Пустая таблица (или --force) - сеять; иначе пропуск с сообщением."""
        if force or not model.objects.exists():
            return True
        self.stdout.write(f'  {model.__name__}: пропущено, справочник не пуст.')
        return False

    def _ensure(self, model, key, defaults):
        """Создать запись, если для ключа нет ни одной (любой период). Не get_or_create: нет MultipleObjectsReturned."""
        if model.objects.filter(**key).exists():
            return
        model.objects.create(**key, **defaults)
        self.created[model.__name__] = self.created.get(model.__name__, 0) + 1

    def handle(self, *args, **options):
        force = options['force']
        self.created = {}
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
        if self._should_seed(UsLandRoute, force):
            for location, port, cost in routes:
                self._ensure(UsLandRoute, dict(auction_location=location, us_port=port),
                             dict(cost_usd=cost, valid_from=today))

        # --- Морской фрахт ---
        ocean_routes = [
            ('houston', 'klaipeda', Decimal('1300')),
            ('houston', 'gdansk', Decimal('1250')),
            ('baltimore', 'klaipeda', Decimal('1100')),
            ('baltimore', 'gdansk', Decimal('1050')),
            ('new_jersey', 'klaipeda', Decimal('1050')),
            ('new_jersey', 'gdansk', Decimal('1000')),
        ]
        if self._should_seed(OceanFreightRate, force):
            for us_port, eu_port, cost in ocean_routes:
                self._ensure(OceanFreightRate, dict(us_port=us_port, eu_port=eu_port),
                             dict(cost_usd=cost, valid_from=today))

        # --- Доставка ЕС → Украина ---
        if self._should_seed(EuToUaDeliveryRate, force):
            for eu_port, cost in [('klaipeda', Decimal('350')), ('gdansk', Decimal('300'))]:
                self._ensure(EuToUaDeliveryRate, dict(eu_port=eu_port),
                             dict(cost_usd=cost, valid_from=today))

        # --- Курсы валют: демо-курсы из DemoRateProvider с source='demo' (02-C8) ---
        # E1: демо-курс не подменяет настоящий при рестарте контейнера. Только при пустой таблице,
        # NBU_MODE=demo или --force; (from, to, date) уникален - существующий курс дня не трогаем.
        demo_mode = getattr(settings, 'NBU_MODE', 'auto') == 'demo'
        if force or demo_mode or not ExchangeRate.objects.exists():
            for quote in DemoRateProvider().fetch(today):
                self._ensure(
                    ExchangeRate,
                    dict(from_currency=quote.from_currency, to_currency=quote.to_currency, date=today),
                    dict(rate=quote.rate, source=quote.source),
                )
        else:
            self.stdout.write('  ExchangeRate: демо-курс пропущено, курсы уже есть.')

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
        if self._should_seed(CustomsExciseRate, force):
            for fuel, cc_min, cc_max, eur_per_100cc, ev_kwh, duty, vat in excise_rates:
                self._ensure(
                    CustomsExciseRate,
                    dict(fuel_type=fuel, engine_cc_min=cc_min, engine_cc_max=cc_max),
                    dict(
                        eur_per_100cc=Decimal(eur_per_100cc),
                        ev_excise_eur_per_kwh=Decimal(ev_kwh) if ev_kwh else None,
                        duty_rate=Decimal(duty),
                        vat_rate=Decimal(vat),
                        valid_from=today,
                    ),
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
        if self._should_seed(PensionFundBracket, force):
            for min_v, max_v, rate in pension_brackets:
                self._ensure(PensionFundBracket, dict(min_value_uah=min_v),
                             dict(max_value_uah=max_v, rate=rate, valid_from=today))

        # --- Правило растаможки (2.5, Q5): значения по умолчанию = прежние формулы, их подтверждает брокер ---
        if not CustomsCalcRule.objects.exists():
            CustomsCalcRule.objects.create(valid_from=date(2000, 1, 1))
            self.created['CustomsCalcRule'] = 1

        summary = ', '.join(f'{k}: {v}' for k, v in self.created.items()) or 'ничего'
        self.stdout.write(f'Тарифы: создано - {summary}.')
        self.stdout.write(self.style.SUCCESS(
            'Тарифы обработаны. Ставки акциза/пошлины/НДС — актуальны на янв–июнь 2026. '
            'Логистика (Copart/IAAI, фрахт) — плейсхолдеры, требуют уточнения у владельца. '
            'Прожиточный минимум (LIVING_WAGE_UAH) — ПРОВЕРИТЬ перед деплоем!'
        ))
