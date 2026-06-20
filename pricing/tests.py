"""
Юнит-тесты для pricing/calculator.py.

Тестируем чистые функции calculate_landed_cost и calc_auction_fees без БД.
Ставки растаможки актуальны на янв–июнь 2026.
Источник: ставки растаможки Украины; финал подтверждает таможенный брокер.
Сетки аукционных сборов — baseline (сверить с тарифом брокера).
"""
from decimal import Decimal
from types import SimpleNamespace
from django.test import SimpleTestCase

from .calculator import (
    AuctionFeeBreakdown,
    LandedCostInputs,
    RateSnapshot,
    calc_auction_fees,
    calculate_landed_cost,
    calc_age_coeff,
)

D = Decimal


def _make_fee_breakdown(
    buyer_fee=D('0'),
    gate_fee=D('0'),
    environmental_fee=D('0'),
    virtual_bid_fee=D('0'),
) -> AuctionFeeBreakdown:
    total = (buyer_fee + gate_fee + environmental_fee + virtual_bid_fee).quantize(D('0.01'))
    return AuctionFeeBreakdown(
        buyer_fee=buyer_fee,
        gate_fee=gate_fee,
        environmental_fee=environmental_fee,
        virtual_bid_fee=virtual_bid_fee,
        total=total,
    )


def _make_rates(
    fuel_type='petrol',
    excise_eur_per_100cc=D('5.00'),
    ev_excise_eur_per_kwh=D('1.00'),
    age_coefficient=D('1.00'),
    duty_rate=D('0.10'),
    vat_rate=D('0.20'),
    pension_fund_rate=D('0.03'),
    auction_fee_breakdown=None,
) -> RateSnapshot:
    """Тестовый снимок ставок. По умолчанию — реальные ставки бензин ≤3000 cc."""
    if auction_fee_breakdown is None:
        auction_fee_breakdown = _make_fee_breakdown(buyer_fee=D('0'))
    return RateSnapshot(
        auction_fee=auction_fee_breakdown,
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


# Вспомогательные объекты для тестов calc_auction_fees (без DB)
def _tier(fee_flat=None, fee_percent=None):
    t = SimpleNamespace()
    t.fee_flat = Decimal(str(fee_flat)) if fee_flat is not None else None
    t.fee_percent = Decimal(str(fee_percent)) if fee_percent is not None else None
    return t


def _fixed(fee_type, amount):
    f = SimpleNamespace()
    f.fee_type = fee_type
    f.amount = Decimal(str(amount))
    return f


# ---------------------------------------------------------------------------
# Формула age_coeff
# ---------------------------------------------------------------------------

class TestCalcAgeCoeff(SimpleTestCase):
    def test_age_8(self):
        self.assertEqual(calc_age_coeff(2018, 2026), D('8'))

    def test_age_1_minimum(self):
        self.assertEqual(calc_age_coeff(2026, 2026), D('1'))

    def test_age_negative_clamped_to_1(self):
        self.assertEqual(calc_age_coeff(2027, 2026), D('1'))

    def test_age_20_capped_to_15(self):
        # Авто 2006 года в 2026 = 20 лет → потолок 15
        self.assertEqual(calc_age_coeff(2006, 2026), D('15'))

    def test_age_exactly_15(self):
        self.assertEqual(calc_age_coeff(2011, 2026), D('15'))

    def test_age_14_not_capped(self):
        self.assertEqual(calc_age_coeff(2012, 2026), D('14'))


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
            auction_fee=_make_fee_breakdown(),  # fee=0 для чистой проверки акциза
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
        # buyer_fee = 10% от 10000 = 1000
        self.rates = _make_rates(
            excise_eur_per_100cc=D('5.00'),
            age_coefficient=D('7'),
            auction_fee_breakdown=_make_fee_breakdown(buyer_fee=D('1000.00')),
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
            'auction_price_usd', 'auction_fee_usd',
            'auction_fee_buyer_usd', 'auction_fee_gate_usd',
            'auction_fee_environmental_usd', 'auction_fee_virtual_bid_usd',
            'us_land_usd', 'ocean_freight_usd', 'eu_to_ua_usd', 'customs_value_usd',
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


# ---------------------------------------------------------------------------
# Тесты calc_auction_fees — аукционные сетки Copart / IAAI
# baseline — сверить с офиц. сеткой и тарифом брокера
# ---------------------------------------------------------------------------

class TestCopartPublicSalvageFlat(SimpleTestCase):
    """
    Copart, public, salvage, secured, ставка $3200.
    По baseline-сетке тиер $3000–3499 → fee_flat=$385.
    + gate salvage $95 + environmental $10 + virtual_bid $99 → total $589.
    """

    def setUp(self):
        self.tier = _tier(fee_flat='385.00')
        self.fixed = [
            _fixed('gate', '95.00'),
            _fixed('environmental', '10.00'),
            _fixed('virtual_bid', '99.00'),
        ]

    def test_buyer_fee(self):
        result = calc_auction_fees(D('3200'), self.tier, self.fixed)
        self.assertEqual(result.buyer_fee, D('385.00'))

    def test_gate_fee(self):
        result = calc_auction_fees(D('3200'), self.tier, self.fixed)
        self.assertEqual(result.gate_fee, D('95.00'))

    def test_environmental_fee(self):
        result = calc_auction_fees(D('3200'), self.tier, self.fixed)
        self.assertEqual(result.environmental_fee, D('10.00'))

    def test_virtual_bid_fee(self):
        result = calc_auction_fees(D('3200'), self.tier, self.fixed)
        self.assertEqual(result.virtual_bid_fee, D('99.00'))

    def test_total(self):
        result = calc_auction_fees(D('3200'), self.tier, self.fixed)
        self.assertEqual(result.total, D('589.00'))  # 385+95+10+99


class TestCopartLicensedPercent(SimpleTestCase):
    """
    Copart licensed/broker, ставка $8000 → 6% = $480.
    """

    def test_buyer_fee_6pct(self):
        tier = _tier(fee_percent='0.0600')
        result = calc_auction_fees(D('8000'), tier, [])
        self.assertEqual(result.buyer_fee, D('480.00'))

    def test_total_no_fixed(self):
        tier = _tier(fee_percent='0.0600')
        result = calc_auction_fees(D('8000'), tier, [])
        self.assertEqual(result.total, D('480.00'))


class TestCopartPublicUpperTier(SimpleTestCase):
    """
    Copart public $5000+ → fee_percent=10%.
    $7500: buyer_fee = 7500 * 0.10 = 750.
    """

    def test_buyer_fee_10pct(self):
        tier = _tier(fee_percent='0.1000')
        result = calc_auction_fees(D('7500'), tier, [])
        self.assertEqual(result.buyer_fee, D('750.00'))


class TestIAAIPercentTier(SimpleTestCase):
    """
    IAAI licensed, верхний диапазон (baseline ~8%).
    $12000: buyer_fee = 12000 * 0.08 = 960.
    """

    def test_iaai_percent_upper(self):
        tier = _tier(fee_percent='0.0800')
        fixed = [
            _fixed('gate', '95.00'),
            _fixed('environmental', '15.00'),
            _fixed('virtual_bid', '75.00'),
        ]
        result = calc_auction_fees(D('12000'), tier, fixed)
        self.assertEqual(result.buyer_fee, D('960.00'))
        self.assertEqual(result.total, D('960.00') + D('95.00') + D('15.00') + D('75.00'))


class TestAuctionFeeBoundary(SimpleTestCase):
    """Проверка выбора тиера на границах диапазона."""

    def test_flat_fee_exact_bid_min(self):
        """bid == bid_min → должен попасть в тиер."""
        tier = _tier(fee_flat='335.00')
        result = calc_auction_fees(D('2500'), tier, [])
        self.assertEqual(result.buyer_fee, D('335.00'))

    def test_flat_fee_exact_bid_max(self):
        """bid == bid_max → должен попасть в тиер."""
        tier = _tier(fee_flat='335.00')
        result = calc_auction_fees(D('2999'), tier, [])
        self.assertEqual(result.buyer_fee, D('335.00'))

    def test_percent_fee_rounding(self):
        """Проверяем округление ROUND_HALF_UP при %."""
        tier = _tier(fee_percent='0.0600')
        # 8333 * 0.06 = 499.98 → 499.98 (нет округления)
        result = calc_auction_fees(D('8333'), tier, [])
        self.assertEqual(result.buyer_fee, D('499.98'))


class TestAuctionFeeBreakdownAllDecimal(SimpleTestCase):
    """Все поля AuctionFeeBreakdown — Decimal."""

    def test_all_decimal(self):
        tier = _tier(fee_flat='385.00')
        fixed = [_fixed('gate', '95.00'), _fixed('environmental', '10.00')]
        result = calc_auction_fees(D('3200'), tier, fixed)
        for attr in ('buyer_fee', 'gate_fee', 'environmental_fee', 'virtual_bid_fee', 'total'):
            val = getattr(result, attr)
            self.assertIsInstance(val, D, f'{attr} должен быть Decimal')


class TestAuctionFeeNoFixedFees(SimpleTestCase):
    """Нет фиксированных сборов → gate/env/vb = 0."""

    def test_no_fixed(self):
        tier = _tier(fee_flat='235.00')
        result = calc_auction_fees(D('1800'), tier, [])
        self.assertEqual(result.gate_fee, D('0'))
        self.assertEqual(result.environmental_fee, D('0'))
        self.assertEqual(result.virtual_bid_fee, D('0'))
        self.assertEqual(result.total, D('235.00'))
