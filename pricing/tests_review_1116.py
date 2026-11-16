"""Правки ревью 2026-11-16: on_commit-инвалидация кэша, курс > 0, engine_cc для ДВС."""
from decimal import Decimal as D

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from pricing import cache as pricing_cache
from pricing.models import ExchangeRate
from pricing.tests_config import SeededCase


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
