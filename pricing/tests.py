"""
Юнит-тесты для pricing/calculator.py.

Тестируем чистую функцию calculate_landed_cost без БД.

ПРИМЕР: Toyota Camry 2019, бензин, 2500 cc, куплена на Copart за $10 000.
Ставки — плейсхолдеры, аналогичные тем, что будут в БД при деплое.
ПРОВЕРИТЬ реальные ставки по действующему законодательству Украины.
"""
from decimal import Decimal
from django.test import SimpleTestCase

from .calculator import (
    LandedCostInputs,
    RateSnapshot,
    AuctionFeeRateSnapshot,
    calculate_landed_cost,
)

D = Decimal


def _make_standard_rates(fuel_type='petrol') -> RateSnapshot:
    """Тестовый снимок ставок с плейсхолдер-значениями."""
    return RateSnapshot(
        auction_fee=AuctionFeeRateSnapshot(
            fee_fixed_usd=D('0'),
            fee_pct=D('0.10'),      # 10% для Copart при цене >$5000
        ),
        us_land_cost_usd=D('600.00'),
        ocean_freight_usd=D('1300.00'),
        eu_to_ua_cost_usd=D('300.00'),
        usd_to_uah=D('41.00'),
        usd_to_eur=D('0.92'),
        # ПРОВЕРИТЬ по действующему законодательству Украины
        excise_eur_per_100cc=D('1.00'),     # placeholder
        age_coefficient=D('1.00'),           # placeholder, 3–5 лет
        duty_rate=D('0.10'),
        vat_rate=D('0.20'),
        # ПРОВЕРИТЬ по действующему законодательству Украины
        pension_fund_rate=D('0.03'),         # placeholder, 3% для базовой шкалы
    )


class TestCalculateLandedCostPetrol(SimpleTestCase):
    """Toyota Camry 2019, бензин, 2500 cc, $10 000 на аукционе."""

    def setUp(self):
        self.inputs = LandedCostInputs(
            auction_price_usd=D('10000.00'),
            engine_cc=2500,
            fuel_type='petrol',
            vehicle_year=2019,
            calculation_year=2024,
        )
        self.rates = _make_standard_rates('petrol')

    def test_auction_fee_is_10_percent(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.auction_fee_usd, D('1000.00'))

    def test_customs_value(self):
        # customs_value = auction_price + us_land + ocean_freight
        result = calculate_landed_cost(self.inputs, self.rates)
        expected = D('10000') + D('600') + D('1300')
        self.assertEqual(result.customs_value_usd, expected)

    def test_duty_is_10_percent_of_customs_value(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.duty_usd, D('1190.00'))  # 11900 * 0.10

    def test_excise_calculation(self):
        # excise = 1.00 EUR/100cc * 25 (2500/100) * 1.00 (age_coeff) = 25 EUR
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertEqual(result.excise_eur, D('25.00'))

    def test_vat_is_20_percent(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        # vat_base = customs_value_uah + duty_uah + excise_uah
        customs_uah = D('11900') * D('41')
        duty_uah = D('1190') * D('41')
        eur_to_uah = D('41') / D('0.92')
        excise_uah = (D('25') * eur_to_uah).quantize(D('0.01'))
        vat_expected = ((customs_uah + duty_uah + excise_uah) * D('0.20')).quantize(D('0.01'))
        self.assertEqual(result.vat_uah, vat_expected)

    def test_is_estimate_always_true(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        self.assertTrue(result.is_estimate)

    def test_total_usd_components(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        # total_usd = price + fee + us_land + ocean + eu_to_ua + duty
        expected = D('10000') + D('1000') + D('600') + D('1300') + D('300') + D('1190')
        self.assertEqual(result.total_usd, expected)

    def test_total_uah_greater_than_total_usd_times_rate(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        # UAH total должен быть больше USD total * курс (из-за таможни)
        self.assertGreater(result.total_uah, result.total_usd * D('41'))

    def test_to_dict_serializable(self):
        result = calculate_landed_cost(self.inputs, self.rates)
        d = result.to_dict()
        self.assertIsInstance(d['total_usd'], str)
        self.assertIsInstance(d['is_estimate'], bool)
        self.assertTrue(d['is_estimate'])


class TestCalculateLandedCostElectric(SimpleTestCase):
    """Tesla Model 3, электро, 0 cc (условно 1 cc), $25 000."""

    def test_electric_excise_is_symbolic(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('25000.00'),
            engine_cc=1,
            fuel_type='electric',
            vehicle_year=2022,
            calculation_year=2024,
        )
        rates = _make_standard_rates('electric')
        result = calculate_landed_cost(inputs, rates)
        # Для электро — символический 1 EUR
        self.assertEqual(result.excise_eur, D('1.00'))


class TestCalculateLandedCostDecimalPrecision(SimpleTestCase):
    """Проверяем, что нет float — только Decimal."""

    def test_all_monetary_fields_are_decimal(self):
        inputs = LandedCostInputs(
            auction_price_usd=D('7500.00'),
            engine_cc=1600,
            fuel_type='diesel',
            vehicle_year=2018,
            calculation_year=2024,
        )
        rates = _make_standard_rates('diesel')
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
            calculation_year=2024,
        )
        rates = _make_standard_rates()
        result = calculate_landed_cost(inputs, rates)
        self.assertGreaterEqual(result.total_usd, D('0'))
        self.assertGreaterEqual(result.total_uah, D('0'))
