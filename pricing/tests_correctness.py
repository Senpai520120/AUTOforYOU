"""Корректность расчёта (задача 2.5): чистый подбор тарифов, периоды, курс, EV/PHEV, правило растаможки.

23-D40, 23-D42...23-D46. Сид-тарифы - seed_rates + seed_auction_fees; ставки законодательства не проверяются (Q5).
"""
from datetime import date, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from pricing.cache import invalidate_all
from pricing.calculator import (
    PENSION_BASE_AUCTION_PRICE,
    PENSION_BASE_CUSTOMS_VALUE,
    PENSION_BASE_CUSTOMS_WITH_TAXES,
    PENSION_BASE_TOTAL,
    DefaultRule,
    RateCatalog,
    calc_age_coeff,
    pick_exchange_rate,
    pick_pension_bracket,
    select_rates,
)
from pricing.models import (
    AuctionFixedFee,
    Calculation,
    CustomsCalcRule,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UsLandRoute,
)
from tests.base import CleanCacheTestCase
from tests.factories import make_staff

CALC_URL = '/api/v1/pricing/calculate/'
TODAY = date.today()
PAYLOAD = {
    'auction': 'copart', 'auction_price_usd': '5000', 'engine_cc': 2000, 'fuel_type': 'petrol',
    'vehicle_year': 2018, 'member_type': 'broker', 'payment_type': 'secured', 'title_type': 'salvage',
    'auction_location': 'general', 'us_port': 'houston', 'eu_port': 'klaipeda',
}


def _ns(pk, valid_from, valid_to=None, **kw):
    return SimpleNamespace(pk=pk, valid_from=valid_from, valid_to=valid_to, **kw)


class SeededCase(CleanCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def calc(self, **extra):
        return APIClient().post(CALC_URL, {**PAYLOAD, **extra}, format='json')


# ─── Чистый подбор без БД ────────────────────────────────────────────────────

class SelectRatesPureTests(SimpleTestCase):
    def _catalog(self, **kw):
        base = dict(
            auction_fee_tiers=[_ns(1, date(2020, 1, 1), auction='copart', member_type='broker', payment_type='secured',
                                   title_type='any', bid_min=D('0'), bid_max=None, fee_flat=D('10'), fee_percent=None)],
            us_land_routes=[_ns(1, date(2020, 1, 1), auction_location='general', us_port='houston', cost_usd=D('1'))],
            ocean_freight=[_ns(1, date(2020, 1, 1), us_port='houston', eu_port='klaipeda', cost_usd=D('1'))],
            eu_to_ua=[_ns(1, date(2020, 1, 1), eu_port='klaipeda', cost_usd=D('1'))],
            exchange_rates=[SimpleNamespace(pk=1, from_currency='USD', to_currency='UAH', date=date(2026, 1, 10), rate=D('41')),
                            SimpleNamespace(pk=2, from_currency='USD', to_currency='EUR', date=date(2026, 1, 10), rate=D('0.9'))],
            excise_rates=[_ns(1, date(2020, 1, 1), fuel_type='petrol', engine_cc_min=0, engine_cc_max=None,
                              ev_excise_eur_per_kwh=None)],
            pension_brackets=[_ns(1, date(2020, 1, 1), min_value_uah=D('0'), max_value_uah=None, rate=D('0.03'))],
            customs_rules=[_ns(1, date(2000, 1, 1))],
        )
        base.update(kw)
        return RateCatalog(**base)

    def test_select_without_db(self):
        sel = select_rates(self._catalog(), PAYLOAD, date(2026, 1, 15))
        self.assertEqual(sel.missing, [])
        self.assertEqual((sel.tier.pk, sel.usd_to_uah.date), (1, date(2026, 1, 10)))

    def test_latest_valid_from_wins_then_pk(self):
        routes = [_ns(1, date(2020, 1, 1), auction_location='general', us_port='houston', cost_usd=D('1')),
                  _ns(2, date(2025, 1, 1), auction_location='general', us_port='houston', cost_usd=D('2')),
                  _ns(3, date(2023, 1, 1), auction_location='general', us_port='houston', cost_usd=D('3'))]
        sel = select_rates(self._catalog(us_land_routes=routes), PAYLOAD, date(2026, 1, 15))
        self.assertEqual(sel.us_land.pk, 2)
        same_day = [_ns(5, date(2025, 1, 1), eu_port='klaipeda', cost_usd=D('1')),
                    _ns(9, date(2025, 1, 1), eu_port='klaipeda', cost_usd=D('2'))]
        self.assertEqual(select_rates(self._catalog(eu_to_ua=same_day), PAYLOAD, date(2026, 1, 15)).eu_to_ua.pk, 9)

    def test_expired_and_future_not_applied(self):
        routes = [_ns(1, date(2020, 1, 1), date(2026, 1, 14), auction_location='general', us_port='houston', cost_usd=D('1')),
                  _ns(2, date(2026, 1, 16), auction_location='general', us_port='houston', cost_usd=D('2'))]
        sel = select_rates(self._catalog(us_land_routes=routes), PAYLOAD, date(2026, 1, 15))
        self.assertIsNone(sel.us_land)
        self.assertIn('UsLandRoute для general → houston', sel.missing)

    def test_exchange_rate_not_from_future(self):
        rates = [SimpleNamespace(pk=1, from_currency='USD', to_currency='UAH', date=date(2026, 1, 10), rate=D('41')),
                 SimpleNamespace(pk=2, from_currency='USD', to_currency='UAH', date=date(2026, 1, 20), rate=D('42'))]
        self.assertEqual(pick_exchange_rate(rates, 'USD', 'UAH', date(2026, 1, 15)).pk, 1)
        self.assertEqual(pick_exchange_rate(rates, 'USD', 'UAH', date(2026, 1, 20)).pk, 2)
        self.assertIsNone(pick_exchange_rate(rates, 'USD', 'UAH', date(2026, 1, 5)))

    def test_ev_without_kwh_rate_missing(self):
        excise = [_ns(1, date(2020, 1, 1), fuel_type='electric', engine_cc_min=0, engine_cc_max=None,
                      ev_excise_eur_per_kwh=None)]
        sel = select_rates(self._catalog(excise_rates=excise), {**PAYLOAD, 'fuel_type': 'electric'}, date(2026, 1, 15))
        self.assertTrue(any('ставки акцизу EV' in m for m in sel.missing))

    def test_no_rule_missing(self):
        sel = select_rates(self._catalog(customs_rules=[]), PAYLOAD, date(2026, 1, 15))
        self.assertIn('CustomsCalcRule', sel.missing)

    def test_rates_updated_on_is_max_valid_from(self):
        routes = [_ns(1, date(2025, 6, 1), auction_location='general', us_port='houston', cost_usd=D('1'))]
        sel = select_rates(self._catalog(us_land_routes=routes), PAYLOAD, date(2026, 1, 15))
        self.assertEqual(sel.rates_updated_on, date(2025, 6, 1))

    def test_pension_bracket_boundaries(self):
        b1, b2 = D('499620.00'), D('878120.00')
        brackets = [_ns(1, date(2020, 1, 1), min_value_uah=D('0'), max_value_uah=b1, rate=D('0.03')),
                    _ns(2, date(2020, 1, 1), min_value_uah=b1, max_value_uah=b2, rate=D('0.04')),
                    _ns(3, date(2020, 1, 1), min_value_uah=b2, max_value_uah=None, rate=D('0.05'))]
        on = date(2026, 1, 15)
        self.assertEqual(pick_pension_bracket(brackets, b1 - D('0.01'), on).pk, 1)
        self.assertEqual(pick_pension_bracket(brackets, b1, on).pk, 2)
        self.assertEqual(pick_pension_bracket(brackets, b1 + D('0.01'), on).pk, 2)
        self.assertEqual(pick_pension_bracket(brackets, b2 - D('0.01'), on).pk, 2)
        self.assertEqual(pick_pension_bracket(brackets, b2, on).pk, 3)
        self.assertEqual(pick_pension_bracket(brackets, b2 + D('0.01'), on).pk, 3)

    def test_age_coeff_params(self):
        self.assertEqual(calc_age_coeff(2018, 2026), D('8'))
        self.assertEqual(calc_age_coeff(2018, 2026, offset_years=1), D('7'))
        self.assertEqual(calc_age_coeff(2026, 2026, min_coeff=1), D('1'))
        self.assertEqual(calc_age_coeff(1990, 2026, max_coeff=15), D('15'))
        self.assertEqual(calc_age_coeff(1990, 2026, max_coeff=20), D('20'))


# ─── Периоды тарифов ─────────────────────────────────────────────────────────

class DateRangeValidationTests(CleanCacheTestCase):
    def _route(self, valid_from, valid_to=None, **kw):
        return UsLandRoute(auction_location='general', us_port='savannah', cost_usd=D('100'),
                           valid_from=valid_from, valid_to=valid_to, **kw)

    def test_to_before_from_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'раніше'):
            self._route(date(2026, 2, 1), date(2026, 1, 1)).full_clean()

    def test_overlap_rejected_adjacent_ok(self):
        self._route(date(2026, 1, 1), date(2026, 1, 31)).save()
        with self.assertRaisesMessage(ValidationError, 'перетинається'):
            self._route(date(2026, 1, 15)).full_clean()
        self._route(date(2026, 2, 1)).full_clean()  # не пересекается
        UsLandRoute(auction_location='other', us_port='savannah', cost_usd=D('1'),
                    valid_from=date(2026, 1, 15)).full_clean()  # другой ключ

    def test_open_ended_overlap_rejected(self):
        self._route(date(2026, 1, 1)).save()
        with self.assertRaisesMessage(ValidationError, 'перетинається'):
            self._route(date(2025, 1, 1), date(2026, 1, 1)).full_clean()

    def test_db_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            OceanFreightRate.objects.create(us_port='x', eu_port='gdansk', cost_usd=D('1'),
                                            valid_from=date(2026, 2, 1), valid_to=date(2026, 1, 1))

    def test_rule_single_per_date(self):
        with self.assertRaisesMessage(ValidationError, 'перетинається'):
            CustomsCalcRule(valid_from=date(2026, 1, 1)).full_clean()  # дефолтное правило с 2000 года открыто


class OverlapLatestAppliedTests(SeededCase):
    def test_two_active_routes_latest_applied(self):
        base = self.calc().json()['breakdown']
        # более старая запись того же маршрута не побеждает, более свежая (или та же дата, больший pk) - да
        UsLandRoute.objects.bulk_create([UsLandRoute(auction_location='general', us_port='houston',
                                                     cost_usd=D('1111'), valid_from=TODAY - timedelta(days=30))])
        invalidate_all()  # bulk_create не шлёт post_save
        self.assertEqual(self.calc().json()['breakdown']['us_land_usd'], base['us_land_usd'])
        UsLandRoute.objects.bulk_create([UsLandRoute(auction_location='general', us_port='houston',
                                                     cost_usd=D('9999'), valid_from=TODAY)])
        invalidate_all()
        self.assertEqual(self.calc().json()['breakdown']['us_land_usd'], '9999.00')
        self.assertNotEqual(base['us_land_usd'], '9999.00')

    def test_latest_ocean_eu_and_fixed_fee_applied(self):
        OceanFreightRate.objects.bulk_create([OceanFreightRate(us_port='houston', eu_port='klaipeda',
                                                               cost_usd=D('7777'), valid_from=TODAY)])
        EuToUaDeliveryRate.objects.bulk_create([EuToUaDeliveryRate(eu_port='klaipeda', cost_usd=D('6666'),
                                                                   valid_from=TODAY)])
        AuctionFixedFee.objects.bulk_create([AuctionFixedFee(auction='copart', fee_type='environmental',
                                                             title_type='any', amount=D('55.00'), valid_from=TODAY)])
        b = self.calc().json()['breakdown']
        self.assertEqual((b['ocean_freight_usd'], b['eu_to_ua_usd'], b['auction_fee_environmental_usd']),
                         ('7777.00', '6666.00', '55.00'))


# ─── Курс по дате ────────────────────────────────────────────────────────────

class ExchangeRateDateTests(SeededCase):
    def setUp(self):
        super().setUp()
        ExchangeRate.objects.all().delete()
        for day, uah in ((10, '40.00'), (20, '45.00')):
            ExchangeRate.objects.create(from_currency='USD', to_currency='UAH', rate=D(uah), date=date(2026, 1, day))
            ExchangeRate.objects.create(from_currency='USD', to_currency='EUR', rate=D('0.9'), date=date(2026, 1, day))
        # тарифы сида начинаются сегодня; для расчёта «в прошлом» продлеваем их назад
        for model in (UsLandRoute, OceanFreightRate, EuToUaDeliveryRate, CustomsExciseRate, PensionFundBracket):
            model.objects.update(valid_from=date(2025, 1, 1))
        from pricing.models import AuctionFeeTier
        AuctionFeeTier.objects.update(valid_from=date(2025, 1, 1))
        AuctionFixedFee.objects.update(valid_from=date(2025, 1, 1))

    def test_rate_on_or_before_date(self):
        resp = self.calc(calculation_date='2026-01-15')
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['exchange_rate_date'], '2026-01-10')
        calc = Calculation.objects.get(pk=body['calculation_id'])
        self.assertEqual(D(calc.rates_snapshot['usd_to_uah']), D('40'))
        self.assertEqual(calc.rates_snapshot['usd_to_uah_date'], '2026-01-10')
        self.assertEqual(calc.rates_snapshot['usd_to_eur_date'], '2026-01-10')
        self.assertEqual(calc.inputs_snapshot['calculation_date'], '2026-01-15')

    def test_exact_date(self):
        self.assertEqual(self.calc(calculation_date='2026-01-20').json()['exchange_rate_date'], '2026-01-20')

    def test_no_earlier_rate_is_422(self):
        resp = self.calc(calculation_date='2026-01-05')
        self.assertEqual(resp.status_code, 422)
        self.assertIn('ExchangeRate USD→UAH', resp.json()['missing'])


# ─── Правило растаможки ──────────────────────────────────────────────────────

class CustomsRuleTests(SeededCase):
    def _rule(self):
        return CustomsCalcRule.objects.get()

    def test_default_rule_keeps_previous_numbers_and_flags(self):
        resp = self.calc()
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIs(body['rules_confirmed'], False)
        self.assertIs(body['is_estimate'], True)
        self.assertEqual(body['breakdown']['customs_value_usd'], '6800.00')  # как в tests/test_e2e.py
        calc = Calculation.objects.get(pk=body['calculation_id'])
        rule = calc.rates_snapshot['rule']
        self.assertEqual((rule['id'], rule['confirmed_by_broker'], rule['confirmed_at']), (self._rule().pk, False, None))
        self.assertEqual(rule['pension_bracket_base'], PENSION_BASE_AUCTION_PRICE)

    def test_confirmed_rule(self):
        rule = self._rule()
        rule.confirmed_by_broker = True
        rule.confirmed_at = date(2026, 10, 1)
        rule.save()
        body = self.calc().json()
        self.assertIs(body['rules_confirmed'], True)
        self.assertIs(body['is_estimate'], True)
        snap = Calculation.objects.get(pk=body['calculation_id']).rates_snapshot['rule']
        self.assertEqual(snap['confirmed_at'], '2026-10-01')

    def test_customs_value_includes_eu_to_ua(self):
        base = self.calc().json()['breakdown']
        CustomsCalcRule.objects.filter(pk=self._rule().pk).update(customs_value_includes_eu_to_ua=True)
        from pricing.cache import invalidate
        invalidate('rules')
        new = self.calc().json()['breakdown']
        self.assertEqual(D(new['customs_value_usd']) - D(base['customs_value_usd']), D(base['eu_to_ua_usd']))
        self.assertGreater(D(new['duty_usd']), D(base['duty_usd']))
        self.assertGreater(D(new['vat_uah']), D(base['vat_uah']))

    def test_age_offset_from_rule(self):
        base = D(self.calc().json()['breakdown']['excise_eur'])
        rule = self._rule()
        rule.age_offset_years = 1
        rule.save()  # сигнал инвалидирует кэш
        new = D(self.calc().json()['breakdown']['excise_eur'])
        # возраст 8 -> 7: акциз пропорционален коэффициенту
        self.assertEqual((new / base).quantize(D('0.001')), (D(7) / D(8)).quantize(D('0.001')))

    def test_each_pension_base_pair(self):
        b = self.calc().json()['breakdown']
        rule = self._rule()
        expected_bases = {
            PENSION_BASE_CUSTOMS_VALUE: D(b['vat_base_uah']) - D(b['duty_uah']) - D(b['excise_uah']),
            PENSION_BASE_CUSTOMS_WITH_TAXES: D(b['vat_base_uah']) + D(b['vat_uah']),
        }
        for rate_base, base_uah in expected_bases.items():
            rule.pension_bracket_base = PENSION_BASE_AUCTION_PRICE
            rule.pension_rate_base = rate_base
            rule.save()
            got = D(self.calc().json()['breakdown']['pension_fund_uah'])
            self.assertEqual(got, (base_uah * D('0.03')).quantize(D('0.01')), rate_base)
        # выбор брекета по полной стоимости: цена ниже первого порога, а полная - выше
        rule.pension_bracket_base = PENSION_BASE_TOTAL
        rule.pension_rate_base = PENSION_BASE_TOTAL
        rule.save()
        big = self.calc(auction_price_usd='11000').json()['breakdown']
        total_before = D(big['total_uah']) - D(big['pension_fund_uah'])
        self.assertEqual(D(big['pension_fund_uah']), (total_before * D('0.04')).quantize(D('0.01')))

    def test_rules_by_date(self):
        CustomsCalcRule.objects.filter(pk=self._rule().pk).update(valid_to=TODAY - timedelta(days=1))
        CustomsCalcRule.objects.create(valid_from=TODAY, age_offset_years=1)
        from pricing.cache import invalidate
        invalidate('rules')
        ExchangeRate.objects.create(from_currency='USD', to_currency='UAH', rate=D('41.50'), date=TODAY - timedelta(days=3))
        ExchangeRate.objects.create(from_currency='USD', to_currency='EUR', rate=D('0.92'), date=TODAY - timedelta(days=3))
        for model in (UsLandRoute, OceanFreightRate, EuToUaDeliveryRate, CustomsExciseRate, PensionFundBracket,
                      AuctionFixedFee):
            model.objects.update(valid_from=TODAY - timedelta(days=10))
        from pricing.models import AuctionFeeTier
        AuctionFeeTier.objects.update(valid_from=TODAY - timedelta(days=10))
        invalidate('rules')
        old = self.calc(calculation_date=(TODAY - timedelta(days=2)).isoformat()).json()['breakdown']['excise_eur']
        new = self.calc().json()['breakdown']['excise_eur']
        self.assertNotEqual(old, new)

    def test_admin_change_invalidates_cache(self):
        self.calc()
        root = make_staff(superuser=True)
        client = self.client
        client.force_login(root)
        rule = self._rule()
        resp = client.post(f'/admin/pricing/customscalcrule/{rule.pk}/change/', {
            'valid_from': '2000-01-01', 'valid_to': '', 'pension_bracket_base': 'auction_price',
            'pension_rate_base': 'total_before_pension', 'age_coeff_min': 1, 'age_coeff_max': 15,
            'age_offset_years': 0, 'confirmed_by_broker': 'on', 'confirmed_at': '2026-10-01', 'note': 'x'})
        self.assertEqual(resp.status_code, 302)
        self.assertIs(self.calc().json()['rules_confirmed'], True)

    def test_plain_staff_cannot_confirm_rule(self):
        from django.contrib.auth.models import Permission
        staff = make_staff('rule.staff@test.com')
        staff.user_permissions.add(*Permission.objects.filter(codename__in=['view_customscalcrule',
                                                                            'change_customscalcrule']))
        self.client.force_login(staff)
        rule = self._rule()
        resp = self.client.post(f'/admin/pricing/customscalcrule/{rule.pk}/change/', {
            'valid_from': '2000-01-01', 'valid_to': '', 'pension_bracket_base': 'auction_price',
            'pension_rate_base': 'total_before_pension', 'age_coeff_min': 1, 'age_coeff_max': 15,
            'age_offset_years': 0, 'confirmed_by_broker': 'on', 'confirmed_at': '2026-10-01', 'note': 'x'})
        self.assertEqual(resp.status_code, 302)
        rule.refresh_from_db()
        self.assertIs(rule.confirmed_by_broker, False)

    def test_no_bracket_is_422(self):
        PensionFundBracket.objects.all().delete()
        resp = self.calc()
        self.assertEqual(resp.status_code, 422)
        self.assertIn('PensionFundBracket', resp.json()['missing'])

    def test_bracket_gap_for_base_is_422(self):
        PensionFundBracket.objects.filter(min_value_uah=D('0')).update(min_value_uah=D('1000000'), max_value_uah=None)
        PensionFundBracket.objects.exclude(min_value_uah=D('1000000')).delete()
        resp = self.calc()
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()['missing'], ['PensionFundBracket'])

    def test_pension_base_choices_match_calculator_constants(self):
        from pricing.models import PensionBase
        self.assertEqual(set(PensionBase.values), {PENSION_BASE_AUCTION_PRICE, PENSION_BASE_CUSTOMS_VALUE,
                                                   PENSION_BASE_CUSTOMS_WITH_TAXES, PENSION_BASE_TOTAL})

    def test_age_min_above_max_rejected(self):
        with self.assertRaisesMessage(ValidationError, 'меншим'):
            CustomsCalcRule(valid_from=date(1990, 1, 1), valid_to=date(1990, 12, 31), age_coeff_min=5,
                            age_coeff_max=3).full_clean()

    def test_unknown_base_gives_json_500(self):
        CustomsCalcRule.objects.filter(pk=self._rule().pk).update(pension_rate_base='bogus')
        from pricing.cache import invalidate
        invalidate('rules')
        resp = self.calc()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()['error'], 'Не вдалося виконати розрахунок. Спробуйте пізніше.')

    def test_default_rule_dataclass_matches_model_defaults(self):
        model_rule = CustomsCalcRule(valid_from=TODAY)
        for f in ('pension_bracket_base', 'pension_rate_base', 'customs_value_includes_eu_to_ua',
                  'age_coeff_min', 'age_coeff_max', 'age_offset_years', 'confirmed_by_broker'):
            self.assertEqual(getattr(model_rule, f), getattr(DefaultRule(), f), f)


# ─── EV / PHEV ───────────────────────────────────────────────────────────────

class EvTests(SeededCase):
    def test_electric_without_battery_400(self):
        resp = self.calc(fuel_type='electric')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('battery_capacity_kwh', resp.json())

    def test_phev_zero_battery_400(self):
        resp = self.calc(fuel_type='phev', battery_capacity_kwh='0')
        self.assertEqual(resp.status_code, 400)

    def test_electric_decimal_battery_excise_nonzero(self):
        resp = self.calc(fuel_type='electric', battery_capacity_kwh='75.5')
        self.assertEqual(resp.status_code, 201)
        rate = CustomsExciseRate.objects.get(fuel_type='electric').ev_excise_eur_per_kwh
        self.assertEqual(D(resp.json()['breakdown']['excise_eur']), (rate * D('75.5')).quantize(D('0.01')))
        self.assertNotEqual(D(resp.json()['breakdown']['excise_eur']), D('0'))

    def test_phev_calculates(self):
        self.assertEqual(self.calc(fuel_type='phev', battery_capacity_kwh='18').status_code, 201)

    def test_ev_rate_without_kwh_422(self):
        CustomsExciseRate.objects.filter(fuel_type='electric').update(ev_excise_eur_per_kwh=None)
        from pricing.cache import invalidate
        invalidate('excise')
        resp = self.calc(fuel_type='electric', battery_capacity_kwh='60')
        self.assertEqual(resp.status_code, 422)
        self.assertTrue(any('ставки акцизу EV' in m for m in resp.json()['missing']))

    def test_petrol_ignores_battery(self):
        resp = self.calc(battery_capacity_kwh='50')
        self.assertEqual(resp.status_code, 201)
        calc = Calculation.objects.get(pk=resp.json()['calculation_id'])
        self.assertIsNone(calc.inputs_snapshot['battery_capacity_kwh'])


# ─── Снимок, ответ, админка ──────────────────────────────────────────────────

class SnapshotAndAdminTests(SeededCase):
    def test_inputs_snapshot_types(self):
        body = self.calc().json()
        calc = Calculation.objects.get(pk=body['calculation_id'])
        self.assertIsNone(calc.inputs_snapshot['calculation_date'])
        self.assertEqual(calc.inputs_snapshot['auction_price_usd'], '5000.00')
        self.assertEqual(calc.inputs_snapshot['engine_cc'], 2000)
        self.assertEqual(body['rates_updated_on'], TODAY.isoformat())
        self.assertEqual(calc.rates_snapshot['rates_updated_on'], TODAY.isoformat())

    def test_empty_rates_422_without_500(self):
        for model in (UsLandRoute, OceanFreightRate, EuToUaDeliveryRate, CustomsExciseRate):
            model.objects.all().delete()
        resp = self.calc()
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(len(resp.json()['missing']), 4)

    def test_calculation_admin_read_only(self):
        calc = Calculation.objects.get(pk=self.calc().json()['calculation_id'])
        self.client.force_login(make_staff(superuser=True))
        self.assertEqual(self.client.get('/admin/pricing/calculation/add/').status_code, 403)
        resp = self.client.post(f'/admin/pricing/calculation/{calc.pk}/change/', {'total_usd': '1', 'is_estimate': ''})
        self.assertEqual(resp.status_code, 403)
        calc.refresh_from_db()
        self.assertIs(calc.is_estimate, True)
        self.assertEqual(self.client.get(f'/admin/pricing/calculation/{calc.pk}/change/').status_code, 200)
        staff = make_staff('calc.staff@test.com')
        from django.contrib.auth.models import Permission
        staff.user_permissions.add(*Permission.objects.filter(codename__in=['view_calculation', 'delete_calculation']))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(f'/admin/pricing/calculation/{calc.pk}/delete/').status_code, 403)
