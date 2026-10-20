"""Задача 2.6: справочники формы из API (Q11), демо по данным, честные ошибки, лимит и очистка расчётов."""
import json
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from pricing import cache as pricing_cache
from pricing.admin import UsLandRouteAdmin
from pricing.models import (
    AuctionFeeTier,
    AuctionFixedFee,
    Calculation,
    CalculatorSettings,
    CustomsCalcRule,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UsLandRoute,
)
from pricing.tasks import purge_anonymous_calculations
from pricing.views import CalculateView
from tests.base import CleanCacheTestCase
from tests.factories import make_admin_role, make_broker, make_moderator, make_staff, make_user

RATES_URL = '/api/v1/pricing/rates/'
CALC_URL = '/api/v1/pricing/calculate/'
TODAY = timezone.localdate()
PAYLOAD = {
    'auction': 'copart', 'auction_price_usd': '5000', 'engine_cc': 2000, 'fuel_type': 'petrol',
    'vehicle_year': 2018, 'auction_location': 'general', 'us_port': 'houston', 'eu_port': 'klaipeda',
}
TARIFFS = (AuctionFeeTier, AuctionFixedFee, UsLandRoute, OceanFreightRate, EuToUaDeliveryRate,
           CustomsExciseRate, PensionFundBracket, CustomsCalcRule)
GRID_KEYS = ('auction_fee_tiers', 'auction_fixed_fees', 'us_land_routes', 'ocean_freight', 'eu_to_ua',
             'exchange_rates', 'excise_rates', 'pension_brackets')


def throttled():
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(ScopedRateThrottle, 'allow_request', return_value=False))
    stack.enter_context(patch.object(ScopedRateThrottle, 'wait', return_value=None))
    return stack


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


class SeededCase(CleanCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def calc(self, user=None, **extra):
        return client_for(user).post(CALC_URL, {**PAYLOAD, **extra}, format='json')

    def verify_all(self):
        for model in TARIFFS:
            model.objects.update(is_verified=True)
        ExchangeRate.objects.update(source='nbu')
        pricing_cache.invalidate_all()


# ─── /rates/ по Q11 (23-D47) ─────────────────────────────────────────────────

class RatesAccessTests(SeededCase):
    def test_anonymous_gets_options_without_sums(self):
        resp = client_for().get(RATES_URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(set(body), {'options', 'is_demo', 'demo_banner'})
        raw = json.dumps(body)
        for word in ('cost_usd', 'fee_flat', 'fee_percent', '"rate"', 'amount', 'duty_rate'):
            self.assertNotIn(word, raw)

    def test_buyer_gets_same_as_anonymous(self):
        resp = client_for(make_user()).get(RATES_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(set(GRID_KEYS) & set(resp.json()))

    def test_broker_gets_full_grid(self):
        resp = client_for(make_broker()).get(RATES_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(set(GRID_KEYS) <= set(resp.json()))

    def test_moderator_without_grid(self):
        resp = client_for(make_moderator()).get(RATES_URL)  # is_staff=True, но pricing.* модератору не положено
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(set(GRID_KEYS) & set(resp.json()))

    def test_admin_role_gets_full_grid(self):
        resp = client_for(make_admin_role()).get(RATES_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(set(GRID_KEYS) <= set(resp.json()))

    def test_options_built_from_seed(self):
        opts = client_for().get(RATES_URL).json()['options']
        self.assertTrue(opts['is_configured'])
        self.assertEqual({o['value'] for o in opts['eu_ports']}, {'klaipeda', 'gdansk'})
        fuels = {o['value']: o['requires_battery'] for o in opts['fuel_types']}
        self.assertTrue(fuels['electric'])
        self.assertFalse(fuels['petrol'])
        self.assertEqual(opts['defaults']['member_type'], 'broker')

    def test_empty_tariffs_not_configured(self):
        for model in TARIFFS:
            model.objects.all().delete()
        pricing_cache.invalidate_all()
        opts = client_for().get(RATES_URL).json()['options']
        self.assertFalse(opts['is_configured'])
        self.assertEqual(opts['auctions'], [])


# ─── Порт ЕС - данные (02-C4) ────────────────────────────────────────────────

class EuPortFromDataTests(SeededCase):
    def add_rotterdam(self):
        OceanFreightRate.objects.create(us_port='houston', eu_port='rotterdam', cost_usd=D('1500'), valid_from=TODAY)
        EuToUaDeliveryRate.objects.create(eu_port='rotterdam', cost_usd=D('1100'), valid_from=TODAY)

    def test_new_port_in_options(self):
        self.add_rotterdam()
        opts = client_for().get(RATES_URL).json()['options']
        self.assertIn('rotterdam', [o['value'] for o in opts['eu_ports']])
        houston = next(p for p in opts['us_ports'] if p['value'] == 'houston')
        self.assertIn('rotterdam', houston['eu_ports'])

    def test_port_without_delivery_not_offered(self):
        OceanFreightRate.objects.create(us_port='houston', eu_port='rotterdam', cost_usd=D('1500'), valid_from=TODAY)
        opts = client_for().get(RATES_URL).json()['options']
        self.assertNotIn('rotterdam', [o['value'] for o in opts['eu_ports']])

    def test_new_port_calculates(self):
        self.add_rotterdam()
        self.assertEqual(self.calc(eu_port='rotterdam').status_code, 201)

    def test_unknown_port_422(self):
        self.assertEqual(self.calc(eu_port='atlantis').status_code, 422)


# ─── is_demo / applied_rates / тексты ────────────────────────────────────────

class DemoFlagTests(SeededCase):
    def test_seed_is_demo(self):
        body = self.calc().json()
        self.assertTrue(body['is_demo'])
        self.assertTrue(client_for().get(RATES_URL).json()['is_demo'])

    def test_all_verified_not_demo(self):
        self.verify_all()
        body = self.calc().json()
        self.assertFalse(body['is_demo'])
        self.assertTrue(body['is_estimate'])
        self.assertFalse(client_for().get(RATES_URL).json()['is_demo'])

    def test_one_unverified_tariff_is_demo(self):
        self.verify_all()
        OceanFreightRate.objects.filter(us_port='houston', eu_port='klaipeda').update(is_verified=False)
        pricing_cache.invalidate_all()
        self.assertTrue(self.calc().json()['is_demo'])

    def test_demo_exchange_rate_is_demo(self):
        self.verify_all()
        ExchangeRate.objects.filter(from_currency='USD', to_currency='UAH').update(source='demo')
        pricing_cache.invalidate_all()
        self.assertTrue(self.calc().json()['is_demo'])

    def test_is_demo_in_snapshot(self):
        calc_id = self.calc().json()['calculation_id']
        self.assertIs(Calculation.objects.get(pk=calc_id).rates_snapshot['is_demo'], True)

    def test_applied_rates_petrol(self):
        rates = self.calc().json()['applied_rates']
        self.assertEqual(rates['duty_rate'], '0.1000')
        self.assertIn('excise_eur_per_100cc', rates)

    def test_applied_rates_ev(self):
        ev = CustomsExciseRate.objects.filter(fuel_type='electric').first()
        rates = self.calc(fuel_type='electric', battery_capacity_kwh='60').json()['applied_rates']
        self.assertEqual(rates['duty_rate'], str(ev.duty_rate))
        self.assertIn('ev_excise_eur_per_kwh', rates)

    def test_warning_from_settings(self):
        settings_obj = CalculatorSettings.load()
        settings_obj.result_warning = 'Новий текст попередження'
        settings_obj.save()
        self.assertEqual(self.calc().json()['warning'], 'Новий текст попередження')

    def test_seed_marks_demo(self):
        self.assertFalse(AuctionFeeTier.objects.filter(is_verified=True).exists())
        self.assertFalse(UsLandRoute.objects.filter(is_verified=True).exists())
        self.assertEqual(set(ExchangeRate.objects.values_list('source', flat=True)), {'demo'})


# ─── Ошибки (02-S1, 422 по Q11) ──────────────────────────────────────────────

class ErrorTests(SeededCase):
    def test_500_hides_exception(self):
        with patch('pricing.views.select_rates', side_effect=RuntimeError('secret ORM detail')), \
                self.assertLogs('pricing.views', level='ERROR') as logs:
            resp = self.calc()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json(), {'error': 'internal_error'})
        self.assertIn('secret ORM detail', '\n'.join(logs.output))

    def test_422_anonymous_without_model_names(self):
        resp = self.calc(eu_port='atlantis')
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(set(resp.json()), {'error', 'missing_count'})
        self.assertNotIn('Rate', json.dumps(resp.json()))

    def test_422_buyer_without_missing(self):
        resp = self.calc(user=make_user(), eu_port='atlantis')
        self.assertNotIn('missing', resp.json())

    def test_422_staff_has_missing(self):
        resp = self.calc(user=make_admin_role(), eu_port='atlantis')
        self.assertEqual(resp.status_code, 422)
        self.assertTrue(resp.json()['missing'])

    def test_throttle_scope(self):
        self.assertEqual(CalculateView.throttle_scope, 'calculator')
        with throttled():
            self.assertEqual(self.calc().status_code, 429)


# ─── Очистка анонимных расчётов (02-S2) ──────────────────────────────────────

class PurgeTests(SeededCase):
    def make_calc(self, days_old, user=None):
        calc = Calculation.objects.create(user=user, inputs_snapshot={}, rates_snapshot={}, breakdown={},
                                          total_usd=D('1'), total_uah=D('1'))
        Calculation.objects.filter(pk=calc.pk).update(created_at=timezone.now() - timedelta(days=days_old))
        return calc

    def test_old_anonymous_deleted(self):
        calc = self.make_calc(40)
        purge_anonymous_calculations()
        self.assertFalse(Calculation.objects.filter(pk=calc.pk).exists())

    def test_fresh_anonymous_kept(self):
        calc = self.make_calc(5)
        purge_anonymous_calculations()
        self.assertTrue(Calculation.objects.filter(pk=calc.pk).exists())

    def test_user_calculation_kept(self):
        calc = self.make_calc(40, user=make_user())
        purge_anonymous_calculations()
        self.assertTrue(Calculation.objects.filter(pk=calc.pk).exists())

    def test_linked_to_lead_kept(self):
        from tests.factories import make_lead
        calc = self.make_calc(40)
        make_lead(calculation=calc)
        purge_anonymous_calculations()
        self.assertTrue(Calculation.objects.filter(pk=calc.pk).exists())

    def test_linked_to_listing_kept(self):
        from tests.factories import make_listing, make_vehicle
        calc = self.make_calc(40)
        make_listing(make_vehicle(), make_user(), calculation=calc)
        purge_anonymous_calculations()
        self.assertTrue(Calculation.objects.filter(pk=calc.pk).exists())

    def test_purge_does_not_call_hook(self):
        self.make_calc(40)
        with patch('pricing.hooks.on_calculation_saved') as hook:
            purge_anonymous_calculations()
        hook.assert_not_called()


# ─── Хук счётчика (шаг 13) ───────────────────────────────────────────────────

class HookTests(SeededCase):
    def test_hook_once_on_success_anonymous(self):
        with patch('pricing.views.on_calculation_saved') as hook, self.captureOnCommitCallbacks(execute=True):
            resp = self.calc()
        self.assertEqual(resp.status_code, 201)
        hook.assert_called_once()
        self.assertEqual(hook.call_args.args[0].pk, resp.json()['calculation_id'])

    def test_hook_once_on_success_user(self):
        with patch('pricing.views.on_calculation_saved') as hook, self.captureOnCommitCallbacks(execute=True):
            self.calc(user=make_user())
        hook.assert_called_once()

    def test_hook_not_called_on_errors(self):
        with patch('pricing.views.on_calculation_saved') as hook, self.captureOnCommitCallbacks(execute=True):
            self.calc(engine_cc=-1)                       # 400
            self.calc(eu_port='atlantis')                 # 422
            with throttled():
                self.calc()                               # 429
            with patch('pricing.views.select_rates', side_effect=RuntimeError('x')), \
                    self.assertLogs('pricing.views', level='ERROR'):
                self.calc()                               # 500
        hook.assert_not_called()

    def test_hook_not_called_without_commit(self):
        with patch('pricing.views.on_calculation_saved') as hook, self.captureOnCommitCallbacks(execute=False):
            self.calc()
        hook.assert_not_called()

    def test_stub_without_metrics_module(self):
        from pricing.hooks import on_calculation_saved
        with patch.dict('sys.modules', {'reports.metrics': None}):
            on_calculation_saved(object())  # ImportError внутри - без падения
        with patch.dict('sys.modules', {'reports.metrics': None}), self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.calc().status_code, 201)


# ─── Админка (шаг 6) ─────────────────────────────────────────────────────────

class AdminVerifyTests(SeededCase):
    def test_mark_verified_action_and_cache(self):
        self.assertTrue(client_for().get(RATES_URL).json()['is_demo'])  # прогрели кэш
        request = RequestFactory().post('/')
        request.user = make_staff(superuser=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        UsLandRouteAdmin(UsLandRoute, AdminSite()).mark_verified(request, UsLandRoute.objects.all())
        self.assertFalse(UsLandRoute.objects.filter(is_verified=False).exists())
        self.assertTrue(all(r.is_verified for r in pricing_cache.get_us_land_routes()))

    def test_changelist_shows_unverified_count(self):
        client = APIClient()
        client.force_login(make_staff(superuser=True))
        resp = client.get('/admin/pricing/uslandroute/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Неперевірених діючих тарифів')
