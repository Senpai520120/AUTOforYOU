"""Правки ревью 2026-11-16: on_commit-инвалидация кэша, курс > 0, engine_cc для ДВС."""
from decimal import Decimal as D

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from pricing import cache as pricing_cache
from pricing.management.commands.seed_rates import fill_uk_names
from pricing.models import ExchangeRate, OceanFreightRate, UsLandRoute
from pricing.tests_config import CALC_URL, PAYLOAD, RATES_URL, SeededCase

PAYLOAD_NO_CC = {**PAYLOAD}


class CacheInvalidateOnCommitTests(SeededCase):
    def _warm(self):
        pricing_cache.get_exchange_rates()
        self.assertIsNotNone(cache.get(pricing_cache.KEYS['exchange']))

    def test_invalidate_waits_for_commit(self):
        self._warm()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            pricing_cache.invalidate('exchange')
            self.assertIsNotNone(cache.get(pricing_cache.KEYS['exchange']))  # до коммита ключ жив
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertIsNone(cache.get(pricing_cache.KEYS['exchange']))

    def test_invalidate_all_waits_for_commit(self):
        self._warm()
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            pricing_cache.invalidate_all()
            self.assertIsNotNone(cache.get(pricing_cache.KEYS['exchange']))
        callbacks[0]()
        self.assertIsNone(cache.get(pricing_cache.KEYS['exchange']))

    def test_invalidate_with_execute_clears_cache(self):
        self._warm()
        with self.captureOnCommitCallbacks(execute=True):
            pricing_cache.invalidate('exchange')
        self.assertIsNone(cache.get(pricing_cache.KEYS['exchange']))


class ExchangeRatePositiveTests(SeededCase):
    def test_zero_rate_fails_validation(self):
        row = ExchangeRate(from_currency='USD', to_currency='PLN', rate=D('0'), date='2020-01-01')
        with self.assertRaises(ValidationError) as ctx:
            row.full_clean()
        self.assertIn('rate', ctx.exception.message_dict)

    def test_zero_rate_rejected_by_db(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExchangeRate.objects.create(from_currency='USD', to_currency='PLN', rate=D('0'), date='2020-01-01')

    def test_positive_rate_ok(self):
        ExchangeRate.objects.create(from_currency='USD', to_currency='PLN', rate=D('0.000001'), date='2020-01-01')


class EngineCcByFuelTests(SeededCase):
    def test_petrol_zero_cc_is_400(self):
        resp = self.calc(engine_cc=0)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('engine_cc', resp.json())

    def test_hybrid_zero_cc_is_400(self):
        resp = self.calc(engine_cc=0, fuel_type='hybrid')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('engine_cc', resp.json())

    def test_electric_zero_cc_ok(self):
        resp = self.calc(engine_cc=0, fuel_type='electric', battery_capacity_kwh='75.0')
        self.assertEqual(resp.status_code, 201)

    def test_phev_zero_cc_ok(self):
        # Акциз PHEV считается по батарее (EV_FUEL_TYPES), объём двигателя не нужен.
        resp = self.calc(engine_cc=0, fuel_type='phev', battery_capacity_kwh='14.0')
        self.assertEqual(resp.status_code, 201)

    def test_phev_zero_cc_without_battery_is_400(self):
        resp = self.calc(engine_cc=0, fuel_type='phev')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('battery_capacity_kwh', resp.json())


class CalculatorUxValidationTests(SeededCase):
    """10.17: пустые обязательные поля - 400 с украинским сообщением; ЭВ без объёма допустим."""

    def _calc_without(self, key, **extra):
        payload = {**PAYLOAD_NO_CC, **extra}
        payload.pop(key, None)
        return self.client.post(CALC_URL, payload, format='json')

    def test_petrol_without_engine_cc_is_400_with_message(self):
        resp = self._calc_without('engine_cc')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['engine_cc'], ["Вкажіть об'єм двигуна (см³)."])

    def test_petrol_null_engine_cc_is_400(self):
        resp = self.calc(engine_cc=None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['engine_cc'], ["Вкажіть об'єм двигуна (см³)."])

    def test_electric_without_engine_cc_ok(self):
        resp = self._calc_without('engine_cc', fuel_type='electric', battery_capacity_kwh='75.0')
        self.assertEqual(resp.status_code, 201)

    def test_missing_price_is_400_with_message(self):
        resp = self._calc_without('auction_price_usd')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['auction_price_usd'], ['Вкажіть ціну аукціону ($).'])

    def test_missing_year_is_400_with_message(self):
        resp = self._calc_without('vehicle_year')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['vehicle_year'], ['Вкажіть рік випуску.'])


class PlaceNamesUkTests(SeededCase):
    """10.17: українські назви портів і локацій в /rates/ з фолбеком на назву з коду."""

    def _options(self):
        return self.client.get(RATES_URL).json()['options']

    def test_seed_fills_unambiguous_names(self):
        labels = {p['value']: p['label'] for p in self._options()['us_ports']}
        self.assertEqual(labels['new_jersey'], 'Нью-Джерсі')
        self.assertEqual(labels['houston'], "Х'юстон")
        eu = {p['value']: p['label'] for p in self._options()['eu_ports']}
        self.assertEqual(eu['klaipeda'], 'Клайпеда')
        locs = {p['value']: p['label'] for p in self._options()['auction_locations']}
        self.assertEqual(locs['california'], 'Каліфорнія')

    def test_untranslated_location_falls_back_to_code_name(self):
        locs = {p['value']: p['label'] for p in self._options()['auction_locations']}
        self.assertEqual(locs['general'], 'General')

    def test_admin_name_is_not_overwritten_by_seed(self):
        UsLandRoute.objects.filter(us_port='houston').update(us_port_uk='Хьюстон (власна)')
        OceanFreightRate.objects.filter(us_port='houston').update(us_port_uk='Хьюстон (власна)')
        call_command('seed_rates', verbosity=0)
        pricing_cache.invalidate_all()
        labels = {p['value']: p['label'] for p in self._options()['us_ports']}
        self.assertEqual(labels['houston'], 'Хьюстон (власна)')

    def test_seed_uk_names_idempotent(self):
        self.assertEqual(fill_uk_names(), 0)
