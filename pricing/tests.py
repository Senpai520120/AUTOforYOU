"""
Юнит-тесты для pricing/calculator.py.

Тестируем чистую функцию calculate_landed_cost без БД.
Ставки растаможки актуальны на янв–июнь 2026.
Источник: ставки растаможки Украины; финал подтверждает таможенный брокер.
"""
from decimal import Decimal
from django.test import SimpleTestCase

from .calculator import (
    LandedCostInputs,
    RateSnapshot,
    AuctionFeeRateSnapshot,
    calculate_landed_cost,
    calc_age_coeff,
)

D = Decimal


def _make_rates(
    fuel_type='petrol',
    excise_eur_per_100cc=D('5.00'),
    ev_excise_eur_per_kwh=D('1.00'),
    age_coefficient=D('1.00'),
    duty_rate=D('0.10'),
    vat_rate=D('0.20'),
    pension_fund_rate=D('0.03'),
) -> RateSnapshot:
    """Тестовый снимок ставок. По умолчанию — реальные ставки бензин ≤3000 cc."""
    return RateSnapshot(
        auction_fee=AuctionFeeRateSnapshot(
            fee_fixed_usd=D('0'),
            fee_pct=D('0.10'),
        ),
        us_land_cost_usd=D('600.00'),
        ocean_freight_usd=D('1300.00'),
        eu_to_ua_cost_usd=D('300.00'),
        usd_to_uah=D('41.00'),
        usd_to_eur=D('0.92'),
        excise_eur_per_100cc=excise_eur_per_100cc,
        ev_excise_eur_per_kwh=ev_excise_eur_per_kwh,
        age_coefficient=age_coefficient,
        duty_rate=duty_rate,
        vat_rate=vat_rate,
        pension_fund_rate=pension_fund_rate,
    )


# ---------------------------------------------------------------------------
# Формула age_coeff
# ---------------------------------------------------------------------------

class TestCalcAgeCoeff(SimpleTestCase):
    def test_age_8(self):
        self.assertEqual(calc_age_coeff(2018, 2026), D('8'))

    def test_age_1_minimum(self):
        # max(1, 2026-2026) = 1
        self.assertEqual(calc_age_coeff(2026, 2026), D('1'))

    def test_age_negative_clamped_to_1(self):
        self.assertEqual(calc_age_coeff(2027, 2026), D('1'))


# ---------------------------------------------------------------------------
# Акциз — ключевые тест-кейсы из спецификации
# ---------------------------------------------------------------------------

class TestExcisePetrol2000cc8years(SimpleTestCase):
    """Бензин 2000 см³, возраст 8 лет: акциз = 50 × 2.0 × 8 = 800 EUR."""

    def test_excise_eur(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('10000.00'),
            engine_cc=2000,
            fuel_type='petrol',
            vehicle_year=2018,
            calculation_year=2026,
        )
        rates = _make_rates(
            excise_eur_per_100cc=D('5.00'),   # 50 EUR/1000cc = 5 EUR/100cc
            age_coefficient=D('8'),            # max(1, 2026-2018)=8
        )
        result = calculate_landed_cost(inputs, rates)
        # 5.00 × (2000/100) × 8 = 5 × 20 × 8 = 800 EUR
        self.assertEqual(result.excise_eur, D('800.00'))


class TestExciseDiesel2000cc7years(SimpleTestCase):
    """Дизель 2000 см³, возраст 7 лет: акциз = 75 × 2.0 × 7 = 1050 EUR."""

    def test_excise_eur(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('10000.00'),
            engine_cc=2000,
            fuel_type='diesel',
            vehicle_year=2019,
            calculation_year=2026,
        )
        rates = _make_rates(
            fuel_type='diesel',
            excise_eur_per_100cc=D('7.50'),   # 75 EUR/1000cc = 7.5 EUR/100cc
            age_coefficient=D('7'),            # max(1, 2026-2019)=7
        )
        result = calculate_landed_cost(inputs, rates)
        # 7.50 × (2000/100) × 7 = 7.5 × 20 × 7 = 1050 EUR
        self.assertEqual(result.excise_eur, D('1050.00'))


class TestExciseEV60kwh(SimpleTestCase):
    """
    EV, таможенная стоимость 30 000 EUR (USD≈EUR при usd_to_eur=1.0),
    батарея 60 кВт·ч:
      акциз = 60 EUR, пошлина = 0, НДС = (30000+0+60)×0.20 = 6012,
      итог растаможки = 6072 EUR.
    """

    def setUp(self):
        # usd_to_eur=1 и us_land=ocean=0 → customs_value_usd = auction_price = 30000
        self.inputs = LandedCostInputs(
            auction_price_usd=D('30000.00'),
            engine_cc=0,
            fuel_type='electric',
            vehicle_year=2023,
            calculation_year=2026,
            battery_capacity_kwh=60,
        )
        self.rates = RateSnapshot(
            auction_fee=AuctionFeeRateSnapshot(fee_fixed_usd=D('0'), fee_pct=D('0')),
            us_land_cost_usd=D('0'),
            ocean_freight_usd=D('0'),
            eu_to_ua_cost_usd=D('0'),
            usd_to_uah=D('1.00'),   # 1:1 чтобы проверять EUR-значения напрямую
            usd_to_eur=D('1.00'),
            excise_eur_per_100cc=D('0'),
            ev_excise_eur_per_kwh=D('1.00'),
            age_coefficient=D('3'),
            duty_rate=D('0'),       # EV: пошлина 0%
            vat_rate=D('0.20'),     # с 01.01.2026 EV платит НДС 20%
            pension_fund_rate=D('0'),
        )

    def test_excise_eur(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.excise_eur, D('60.00'))   # 1 EUR/кВт·ч × 60

    def test_duty_is_zero(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.duty_usd, D('0.00'))

    def test_vat(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        # vat_base = customs_value_uah + duty_uah + excise_uah = 30000+0+60 = 30060
        # vat = 30060 × 0.20 = 6012
        self.assertEqual(result.vat_uah, D('6012.00'))

    def test_customs_total_without_pension(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        # excise+duty+vat = 60+0+6012 = 6072 (пенсионный 0 в тестовом снимке)
        self.assertEqual(result.excise_uah + result.duty_uah + result.vat_uah, D('6072.00'))


class TestUSOriginDuty10Percent(SimpleTestCase):
    """US-origin бензин: льгота EUR.1 не применяется, пошлина 10%."""

    def test_duty_10_percent(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('10000.00'),
            engine_cc=2000,
            fuel_type='petrol',
            vehicle_year=2020,
            calculation_year=2026,
        )
        rates = _make_rates(duty_rate=D('0.10'))
        result = calculate_landed_cost(inputs, rates)
        # customs_value = 10000+600+1300 = 11900; duty = 11900*0.10 = 1190
        self.assertEqual(result.duty_usd, D('1190.00'))


# ---------------------------------------------------------------------------
# Старые тесты — Toyota Camry 2019, обновлены под реальные ставки
# ---------------------------------------------------------------------------

class TestCalculateLandedCostPetrol(SimpleTestCase):
    """Toyota Camry 2019, бензин 2500 cc, $10 000, calc_year=2026 → age=7."""

    def setUp(self):
        self.inputs = LandedCostInputs(
            auction_price_usd=D('10000.00'),
            engine_cc=2500,
            fuel_type='petrol',
            vehicle_year=2019,
            calculation_year=2026,
        )
        # age=7; excise = 5.00 × 25 × 7 = 875 EUR
        self.rates = _make_rates(
            excise_eur_per_100cc=D('5.00'),
            age_coefficient=D('7'),
        )

    def test_auction_fee_is_10_percent(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.auction_fee_usd, D('1000.00'))

    def test_customs_value(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.customs_value_usd, D('10000') + D('600') + D('1300'))

    def test_duty_is_10_percent_of_customs_value(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.duty_usd, D('1190.00'))  # 11900 * 0.10

    def test_excise_calculation(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        # 5.00 × (2500/100) × 7 = 5 × 25 × 7 = 875 EUR
        self.assertEqual(result.excise_eur, D('875.00'))

    def test_vat_is_20_percent(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        eur_to_uah = D('41') / D('0.92')
        excise_uah = (D('875') * eur_to_uah).quantize(D('0.01'))
        customs_uah = D('11900') * D('41')
        duty_uah = D('1190') * D('41')
        vat_expected = ((customs_uah + duty_uah + excise_uah) * D('0.20')).quantize(D('0.01'))
        self.assertEqual(result.vat_uah, vat_expected)

    def test_is_estimate_always_true(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertTrue(result.is_estimate)

    def test_total_usd_components(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        expected = D('10000') + D('1000') + D('600') + D('1300') + D('300') + D('1190')
        self.assertEqual(result.total_usd, expected)

    def test_total_uah_greater_than_total_usd_times_rate(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertGreater(result.total_uah, result.total_usd * D('41'))

    def test_to_dict_serializable(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        d = result.to_dict()
        self.assertIsInstance(d['total_usd'], str)
        self.assertIsInstance(d['is_estimate'], bool)
        self.assertTrue(d['is_estimate'])


class TestCalculateLandedCostElectric(SimpleTestCase):
    """Tesla Model 3, электро, 75 кВт·ч, $25 000."""

    def test_electric_excise_per_kwh(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('25000.00'),
            engine_cc=0,
            fuel_type='electric',
            vehicle_year=2022,
            calculation_year=2026,
            battery_capacity_kwh=75,
        )
        rates = _make_rates(
            fuel_type='electric',
            excise_eur_per_100cc=D('0'),
            ev_excise_eur_per_kwh=D('1.00'),
            duty_rate=D('0'),
        )
        result = calculate_landed_cost(inputs, rates)
        self.assertEqual(result.excise_eur, D('75.00'))   # 1 EUR × 75 кВт·ч

    def test_electric_duty_is_zero(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('25000.00'),
            engine_cc=0,
            fuel_type='electric',
            vehicle_year=2022,
            calculation_year=2026,
            battery_capacity_kwh=75,
        )
        rates = _make_rates(
            fuel_type='electric',
            excise_eur_per_100cc=D('0'),
            ev_excise_eur_per_kwh=D('1.00'),
            duty_rate=D('0'),
        )
        result = calculate_landed_cost(inputs, rates)
        self.assertEqual(result.duty_usd, D('0.00'))

    def test_electric_vat_20_percent(self):
        """С 01.01.2026 льгота по НДС для EV отменена — EV платит 20%."""
        inputs = LandedCostInputs(
            auction_price_usd=D('25000.00'),
            engine_cc=0,
            fuel_type='electric',
            vehicle_year=2022,
            calculation_year=2026,
            battery_capacity_kwh=75,
        )
        rates = _make_rates(
            fuel_type='electric',
            excise_eur_per_100cc=D('0'),
            ev_excise_eur_per_kwh=D('1.00'),
            duty_rate=D('0'),
            vat_rate=D('0.20'),
        )
        result = calculate_landed_cost(inputs, rates)
        self.assertGreater(result.vat_uah, D('0'))


class TestPHEV(SimpleTestCase):
    """PHEV: акциз по кВт·ч, пошлина 0%."""

    def test_phev_excise_per_kwh(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('20000.00'),
            engine_cc=1500,
            fuel_type='phev',
            vehicle_year=2021,
            calculation_year=2026,
            battery_capacity_kwh=20,
        )
        rates = _make_rates(
            fuel_type='phev',
            excise_eur_per_100cc=D('0'),
            ev_excise_eur_per_kwh=D('1.00'),
            duty_rate=D('0'),
        )
        result = calculate_landed_cost(inputs, rates)
        self.assertEqual(result.excise_eur, D('20.00'))   # 1 EUR × 20 кВт·ч
        self.assertEqual(result.duty_usd, D('0.00'))


class TestCalculateLandedCostDecimalPrecision(SimpleTestCase):
    """Проверяем, что нет float — только Decimal."""

    def test_all_monetary_fields_are_decimal(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('7500.00'),
            engine_cc=1600,
            fuel_type='diesel',
            vehicle_year=2018,
            calculation_year=2026,
        )
        rates = _make_rates(
            fuel_type='diesel',
            excise_eur_per_100cc=D('7.50'),
            age_coefficient=D('8'),
        )
        result = calculate_landed_cost(inputs, rates)

        for field_name in [
            'auction_price_usd', 'auction_fee_usd', 'us_land_usd',
            'ocean_freight_usd', 'eu_to_ua_usd', 'customs_value_usd',
            'excise_eur', 'excise_uah', 'duty_usd', 'duty_uah',
            'vat_base_uah', 'vat_uah', 'pension_fund_uah',
            'customs_total_uah', 'total_usd', 'total_uah',
        ]:
            val = getattr(result, field_name)
            self.assertIsInstance(val, Decimal, f'Поле {field_name} должно быть Decimal, а не {type(val)}')


class TestZeroPriceEdgeCase(SimpleTestCase):
    def test_zero_price(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('0'),
            engine_cc=1000,
            fuel_type='petrol',
            vehicle_year=2020,
            calculation_year=2026,
        )
        rates = _make_rates(age_coefficient=D('6'))
        result = calculate_landed_cost(inputs, rates)
        self.assertGreaterEqual(result.total_usd, D('0'))
        self.assertGreaterEqual(result.total_uah, D('0'))
