"""Задача 2.7: доставка по Украине и услуги брокера после растаможки (Q6, Q11, решение шага 14)."""
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from types import SimpleNamespace

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.utils import timezone

from pricing import cache as pricing_cache
from pricing.calculator import LandedCostInputs, broker_services_for, calculate_landed_cost
from pricing.models import BrokerServiceFee, Calculation, FeeMode, UaDeliveryRate
from pricing.tests import _make_rates
from pricing.tests_config import RATES_URL, SeededCase, client_for
from tests.factories import make_broker, make_user

TODAY = timezone.localdate()
INPUTS = LandedCostInputs(auction_price_usd=D('10000'), engine_cc=2000, fuel_type='petrol',
                          vehicle_year=2018, calculation_year=2026)


def fee(mode, value, pk=1, title='Послуги брокера'):
    if mode == 'percent':
        return SimpleNamespace(pk=pk, title=title, fee_mode='percent', percent=D(value), amount_usd=None)
    return SimpleNamespace(pk=pk, title=title, fee_mode='fixed', amount_usd=D(value), percent=None)


class PureCalculatorTests(SimpleTestCase):
    def test_extras_added_after_customs(self):
        base = calculate_landed_cost(INPUTS, _make_rates())
        rates = replace(_make_rates(), ua_delivery_cost_usd=D('300'),
                        broker_services=[{'title': 'A', 'amount_usd': D('150')}, {'title': 'B', 'amount_usd': D('50')}])
        res = calculate_landed_cost(INPUTS, rates)
        self.assertEqual(res.total_usd - base.total_usd, D('500'))
        self.assertEqual(res.total_uah - base.total_uah, D('500') * D('41.00'))
        self.assertEqual((res.customs_value_usd, res.duty_usd), (base.customs_value_usd, base.duty_usd))
        self.assertEqual(res.broker_services_total_usd, D('200'))
        self.assertFalse(res.ua_delivery_pending)
        self.assertFalse(res.broker_services_pending)

    def test_nothing_configured_is_pending(self):
        base = calculate_landed_cost(INPUTS, _make_rates())
        self.assertTrue(base.ua_delivery_pending)
        self.assertTrue(base.broker_services_pending)
        self.assertIsNone(base.ua_delivery_usd)

    def test_percent_from_auction_price(self):
        self.assertEqual(broker_services_for([fee('percent', '2')], D('10000'))[0]['amount_usd'], D('200.00'))

    def test_percent_independent_of_other_rates(self):
        services = broker_services_for([fee('percent', '2')], INPUTS.auction_price_usd)
        rates = replace(_make_rates(duty_rate=D('0.5')), usd_to_uah=D('50'), eu_to_ua_cost_usd=D('999'),
                        broker_services=services)
        self.assertEqual(calculate_landed_cost(INPUTS, rates).broker_services[0]['amount_usd'], D('200.00'))

    def test_percent_rounds_up_to_cent(self):
        self.assertEqual(broker_services_for([fee('percent', '1.5')], D('333.33'))[0]['amount_usd'], D('5.00'))
        self.assertEqual(broker_services_for([fee('percent', '1')], D('100.01'))[0]['amount_usd'], D('1.01'))

    def test_switch_fixed_percent(self):
        self.assertEqual(broker_services_for([fee('fixed', '300')], D('10000'))[0]['amount_usd'], D('300'))
        self.assertEqual(broker_services_for([fee('percent', '3')], D('10000'))[0]['amount_usd'], D('300.00'))


class ModelTests(SeededCase):
    def test_default_mode_fixed(self):
        self.assertEqual(BrokerServiceFee(title='X', valid_from=TODAY).fee_mode, FeeMode.FIXED)

    def test_fixed_without_amount_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrokerServiceFee.objects.create(title='X', fee_mode='fixed', valid_from=TODAY)

    def test_percent_over_100_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrokerServiceFee.objects.create(title='X', fee_mode='percent', percent=D('150'), valid_from=TODAY)

    def test_negative_delivery_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UaDeliveryRate.objects.create(destination='Київ', cost_usd=D('-1'), valid_from=TODAY)

    def test_delivery_without_cost_or_quote_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UaDeliveryRate.objects.create(destination='Київ', valid_from=TODAY)


class ApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.kyiv = UaDeliveryRate.objects.create(destination='Київ', cost_usd=D('300'), valid_from=TODAY)

    def test_valid_city_201(self):
        resp = self.calc(ua_delivery_rate=self.kyiv.pk)
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body['breakdown']['ua_delivery_usd'], '300.00')
        snap = Calculation.objects.get(pk=body['calculation_id']).rates_snapshot
        self.assertEqual(snap['meta']['ua_delivery_rate_id'], self.kyiv.pk)

    def test_city_included_in_total(self):
        without = self.calc().json()['breakdown']['total_usd']
        with_city = self.calc(ua_delivery_rate=self.kyiv.pk).json()['breakdown']['total_usd']
        self.assertEqual(D(with_city) - D(without), D('300'))

    def test_unknown_id_400(self):
        resp = self.calc(ua_delivery_rate=999999)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('ua_delivery_rate', resp.json())

    def test_expired_rate_400(self):
        UaDeliveryRate.objects.filter(pk=self.kyiv.pk).update(valid_from=TODAY - timedelta(days=10),
                                                               valid_to=TODAY - timedelta(days=1))
        pricing_cache.invalidate_all()
        self.assertEqual(self.calc(ua_delivery_rate=self.kyiv.pk).status_code, 400)

    def test_other_eu_port_400(self):
        UaDeliveryRate.objects.filter(pk=self.kyiv.pk).update(eu_port='gdansk')
        pricing_cache.invalidate_all()
        self.assertEqual(self.calc(ua_delivery_rate=self.kyiv.pk, eu_port='klaipeda').status_code, 400)

    def test_quote_on_request_pending(self):
        lviv = UaDeliveryRate.objects.create(destination='Львів', quote_on_request=True, valid_from=TODAY)
        b = self.calc(ua_delivery_rate=lviv.pk).json()['breakdown']
        self.assertTrue(b['ua_delivery_pending'])
        self.assertIsNone(b['ua_delivery_usd'])

    def test_quote_on_request_wins_over_cost(self):
        odesa = UaDeliveryRate.objects.create(destination='Одеса', cost_usd=D('999'), quote_on_request=True,
                                              valid_from=TODAY)
        self.assertTrue(self.calc(ua_delivery_rate=odesa.pk).json()['breakdown']['ua_delivery_pending'])

    def test_nothing_selected_201_pending(self):
        resp = self.calc()
        self.assertEqual(resp.status_code, 201)
        b = resp.json()['breakdown']
        self.assertTrue(b['ua_delivery_pending'])
        self.assertTrue(b['broker_services_pending'])
        self.assertEqual(b['broker_services'], [])

    def test_percent_service_in_snapshot(self):
        BrokerServiceFee.objects.create(title='Послуги брокера', fee_mode='percent', percent=D('2'), valid_from=TODAY)
        body = self.calc(auction_price_usd='10000').json()
        self.assertEqual(body['breakdown']['broker_services'], [{'title': 'Послуги брокера', 'amount_usd': '200.00'}])
        snap = Calculation.objects.get(pk=body['calculation_id']).rates_snapshot['broker_services'][0]
        self.assertEqual((snap['fee_mode'], snap['percent'], snap['base_usd'], snap['amount_usd']),
                         ('percent', '2.00', '10000.00', '200.00'))

    def test_future_fee_not_applied(self):
        BrokerServiceFee.objects.create(title='Реєстрація', amount_usd=D('50'), valid_from=TODAY + timedelta(days=5))
        self.assertTrue(self.calc().json()['breakdown']['broker_services_pending'])

    def test_unverified_city_makes_demo(self):
        self.verify_all()
        self.assertFalse(self.calc(ua_delivery_rate=self.kyiv.pk).json()['is_demo'])
        UaDeliveryRate.objects.filter(pk=self.kyiv.pk).update(is_verified=False)
        pricing_cache.invalidate_all()
        self.assertTrue(self.calc(ua_delivery_rate=self.kyiv.pk).json()['is_demo'])


class RatesTests(SeededCase):
    def setUp(self):
        super().setUp()
        UaDeliveryRate.objects.create(destination='Київ', cost_usd=D('321'), valid_from=TODAY)
        UaDeliveryRate.objects.create(destination='Старе', cost_usd=D('1'), valid_from=TODAY - timedelta(days=9),
                                      valid_to=TODAY - timedelta(days=1))
        BrokerServiceFee.objects.create(title='Сертифікація', amount_usd=D('77'), valid_from=TODAY)

    def test_anonymous_without_sums(self):
        body = client_for().get(RATES_URL).json()
        self.assertEqual([r['destination'] for r in body['ua_delivery_rates']], ['Київ'])
        self.assertEqual([f['title'] for f in body['broker_service_fees']], ['Сертифікація'])
        raw = json.dumps({k: body[k] for k in ('ua_delivery_rates', 'broker_service_fees')})
        for word in ('cost_usd', 'amount_usd', 'percent', '321', '77'):
            self.assertNotIn(word, raw)

    def test_buyer_without_sums(self):
        raw = json.dumps(client_for(make_user()).get(RATES_URL).json()['ua_delivery_rates'])
        self.assertNotIn('cost_usd', raw)

    def test_broker_with_sums(self):
        body = client_for(make_broker()).get(RATES_URL).json()
        self.assertEqual(D(str(body['ua_delivery_rates'][0]['cost_usd'])), D('321'))
        self.assertEqual(D(str(body['broker_service_fees'][0]['amount_usd'])), D('77'))

    def test_admin_change_invalidates_cache(self):
        client_for().get(RATES_URL)  # прогрели кэш
        UaDeliveryRate.objects.create(destination='Одеса', cost_usd=D('400'), valid_from=TODAY)
        names = [r['destination'] for r in client_for().get(RATES_URL).json()['ua_delivery_rates']]
        self.assertIn('Одеса', names)
