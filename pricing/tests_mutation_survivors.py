"""Тесты против выживших мутантов cosmic-ray в pricing/calculator.py (scripts/mutation.sh calculator).

Каждый тест закрывает конкретную мутацию: границы `>=`/`<=` (тариф в последний день, брекет
на верхней границе), выбор по равенству строк (порт, валюта), база пенсионного сбора.
Чистые функции калькулятора, без БД.
"""
from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

from django.test import SimpleTestCase

from pricing.calculator import (
    DEFAULT_RULE,
    PENSION_BASE_AUCTION_PRICE,
    LandedCostInputs,
    MissingRate,
    RateCatalog,
    calculate_landed_cost,
    exchange_rate_info,
    is_active,
    lookup_tier,
    pick_exchange_rate,
    pick_pension_bracket,
    select_rates,
)
from pricing.tests import _make_rates

ON = date(2026, 6, 1)
OLD, NEW = date(2026, 1, 1), date(2026, 3, 1)


def _r(pk, valid_from=OLD, valid_to=None, **kw):
    return SimpleNamespace(pk=pk, valid_from=valid_from, valid_to=valid_to, **kw)


class ActivePeriodBoundaryTests(SimpleTestCase):
    def test_rate_is_active_on_its_last_day(self):
        self.assertIs(is_active(_r(1, valid_to=ON), ON), True)
        self.assertIs(is_active(_r(1, valid_to=date(2026, 5, 31)), ON), False)


class TierBoundaryTests(SimpleTestCase):
    def test_bid_equal_to_bid_max_fits_tier(self):
        tier = _r(1, auction='copart', member_type='public', payment_type='card', title_type='clean',
                  bid_min=D('0'), bid_max=D('1000'))
        self.assertIs(lookup_tier([tier], 'copart', '1000', 'public', 'card', 'clean', ON), tier)

    def test_tier_of_other_auction_member_or_payment_is_ignored(self):
        # Чужие значения и «меньше», и «больше» по алфавиту: ловит `==` -> `<=` и `>=`.
        def tier(pk, **kw):
            base = dict(auction='copart', member_type='public', payment_type='card', title_type='clean',
                        bid_min=D('0'), bid_max=None)
            return _r(pk, valid_from=NEW, **{**base, **kw})
        own = _r(1, auction='copart', member_type='public', payment_type='card', title_type='clean',
                 bid_min=D('0'), bid_max=None)
        others = [tier(2, auction='aaa'), tier(3, auction='zzz'), tier(4, member_type='aaa'),
                  tier(5, member_type='zzz'), tier(6, payment_type='aaa'), tier(7, payment_type='zzz'),
                  tier(8, title_type='aaa')]
        self.assertIs(lookup_tier([own, *others], 'copart', '500', 'public', 'card', 'clean', ON), own)


class PensionBracketTests(SimpleTestCase):
    def _brackets(self):
        low = _r(1, min_value_uah=D('400000'), max_value_uah=D('410000'), rate=D('0.03'))
        high = _r(2, min_value_uah=D('410000.01'), max_value_uah=None, rate=D('0.04'))
        return low, high

    def test_base_equal_to_max_value_picks_bracket(self):
        low, high = self._brackets()
        self.assertIs(pick_pension_bracket([low, high], D('410000'), None), low)

    def test_bracket_is_chosen_by_auction_price_in_uah(self):
        # Правило по умолчанию: брекет по цене аукциона в UAH = 10000 × 41 = 410000 -> ставка 3%.
        # Мутанты `price * курс` -> `+ - /` дают базу вне брекетов (MissingRate) или другой брекет.
        inputs = LandedCostInputs(auction_price_usd=D('10000.00'), engine_cc=2000, fuel_type='petrol',
                                  vehicle_year=2018, calculation_year=2026)
        rates = _make_rates()
        calculate_landed_cost(inputs, rates, pension_brackets=list(self._brackets()))
        self.assertEqual(rates.meta['pension_bracket_id'], 1)
        self.assertEqual(rates.pension_fund_rate, D('0.03'))

    def test_pension_on_auction_price_base(self):
        rule = replace(DEFAULT_RULE, pension_rate_base=PENSION_BASE_AUCTION_PRICE)
        inputs = LandedCostInputs(auction_price_usd=D('10000.00'), engine_cc=2000, fuel_type='petrol',
                                  vehicle_year=2018, calculation_year=2026)
        result = calculate_landed_cost(inputs, _make_rates(pension_fund_rate=D('0.03')), rule=rule)
        # 10000 USD × 41 = 410000 UAH × 3% = 12300.00
        self.assertEqual(result.pension_fund_uah, D('12300.00'))

    def test_no_bracket_raises(self):
        low, _ = self._brackets()
        inputs = LandedCostInputs(auction_price_usd=D('100.00'), engine_cc=2000, fuel_type='petrol',
                                  vehicle_year=2018, calculation_year=2026)
        with self.assertRaisesMessage(MissingRate, 'PensionFundBracket'):
            calculate_landed_cost(inputs, _make_rates(), pension_brackets=[low])


class ExchangeRateTests(SimpleTestCase):
    def test_only_exact_currency_pair_is_used(self):
        usd_uah = _r(1, from_currency='USD', to_currency='UAH', date=OLD)
        decoys = [_r(2, from_currency='EUR', to_currency='UAH', date=NEW),
                  _r(3, from_currency='UZS', to_currency='UAH', date=NEW),
                  _r(4, from_currency='USD', to_currency='EUR', date=NEW),
                  _r(5, from_currency='USD', to_currency='ZAR', date=NEW)]
        self.assertIs(pick_exchange_rate([usd_uah, *decoys], 'USD', 'UAH', ON), usd_uah)

    def test_stale_only_after_max_age(self):
        rate = SimpleNamespace(date=date(2026, 5, 29), source='nbu')  # 3 дня до ON
        fresh = exchange_rate_info(rate, rate, ON, max_age_days=3)
        self.assertIs(fresh['exchange_rate_stale'], False)
        self.assertIsNone(fresh['exchange_rate_warning'])
        stale = exchange_rate_info(rate, rate, ON, max_age_days=2)
        self.assertIs(stale['exchange_rate_stale'], True)
        self.assertIn('Курс валют застарілий', stale['exchange_rate_warning'])
        self.assertIn('29.05.2026', stale['exchange_rate_warning'])


class SelectRatesTests(SimpleTestCase):
    PARAMS = dict(auction='copart', member_type='public', payment_type='card', title_type='clean',
                  auction_price_usd='1000', auction_location='TX', us_port='Houston', eu_port='Klaipeda',
                  fuel_type='petrol', engine_cc=3000)

    def test_excise_with_engine_cc_max_equal_to_engine_is_chosen(self):
        excise = _r(1, fuel_type='petrol', engine_cc_min=0, engine_cc_max=3000)
        sel = select_rates(RateCatalog(excise_rates=[excise]), self.PARAMS, ON)
        self.assertIs(sel.excise, excise)

    def test_routes_match_ports_exactly(self):
        # Ложные маршруты новее и с портами «до» и «после» по алфавиту: ловят `==` -> `<=`/`>=`.
        land = _r(1, auction_location='TX', us_port='Houston')
        ocean = _r(2, us_port='Houston', eu_port='Klaipeda')
        eu_ua = _r(3, eu_port='Klaipeda')
        catalog = RateCatalog(
            us_land_routes=[land, _r(11, NEW, auction_location='AL', us_port='Houston'),
                            _r(12, NEW, auction_location='ZZ', us_port='Houston'),
                            _r(13, NEW, auction_location='TX', us_port='Austin'),
                            _r(14, NEW, auction_location='TX', us_port='Savannah')],
            ocean_freight=[ocean, _r(21, NEW, us_port='Austin', eu_port='Klaipeda'),
                           _r(22, NEW, us_port='Savannah', eu_port='Klaipeda'),
                           _r(23, NEW, us_port='Houston', eu_port='Gdansk'),
                           _r(24, NEW, us_port='Houston', eu_port='Riga')],
            eu_to_ua=[eu_ua, _r(31, NEW, eu_port='Gdansk'), _r(32, NEW, eu_port='Riga')],
        )
        sel = select_rates(catalog, self.PARAMS, ON)
        self.assertIs(sel.us_land, land)
        self.assertIs(sel.ocean, ocean)
        self.assertIs(sel.eu_to_ua, eu_ua)
