"""Устойчивость API (задача 10.16, E3): NUL-байт в query -> 400, throttle переживает падение кэша."""
import os
import tempfile
import time
from unittest import mock

import redis
from django.test import SimpleTestCase, TestCase
from django_redis.exceptions import ConnectionInterrupted
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from core import throttles


class NulByteQueryTests(TestCase):
    def get(self, url):
        return APIClient().get(url)

    def test_city_search_nul_is_400(self):
        resp = self.get('/api/v1/local/cities/?q=%00')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('detail', resp.json())

    def test_local_catalog_filter_nul_is_400(self):
        self.assertEqual(self.get('/api/v1/local/listings/?q=ab%00cd').status_code, 400)

    def test_lots_catalog_filter_nul_is_400(self):
        self.assertEqual(self.get('/api/v1/listings/?make=%00').status_code, 400)

    def test_vehicles_filter_nul_is_400(self):
        self.assertEqual(self.get('/api/v1/vehicles/?search=%00').status_code, 400)

    def test_site_settings_nul_in_any_param_is_400(self):
        self.assertEqual(self.get('/api/v1/site-settings/?x=%00').status_code, 400)

    def test_uppercase_percent_and_raw_nul_is_400(self):
        self.assertEqual(self.get('/api/v1/site-settings/?x=a%2500%00').status_code, 400)
        resp = APIClient().generic('GET', '/api/v1/site-settings/', QUERY_STRING='x=\x00')
        self.assertEqual(resp.status_code, 400)

    def test_clean_query_passes(self):
        self.assertEqual(self.get('/api/v1/site-settings/?x=abc').status_code, 200)

    def test_literal_percent_zero_zero_text_is_not_nul(self):
        # %2500 - это литерал «%00» после декодирования, не NUL; но подстрока '%00' в сыром виде не встречается.
        self.assertEqual(self.get('/api/v1/site-settings/?x=%2500').status_code, 200)


class FailOpenThrottleUnitTests(SimpleTestCase):
    def setUp(self):
        marker = tempfile.mkdtemp()
        patcher = mock.patch('core.throttles.tempfile.gettempdir', return_value=marker)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_alert_sent_once_per_interval(self):
        with mock.patch('core.throttles.threading.Thread') as thread:
            throttles._alert_once()
            throttles._alert_once()
        self.assertEqual(thread.call_count, 1)

    def test_alert_repeats_after_interval(self):
        with mock.patch('core.throttles.threading.Thread') as thread:
            throttles._alert_once()
            old = time.time() - throttles.ALERT_INTERVAL - 5
            os.utime(throttles._marker_path(), (old, old))
            throttles._alert_once()
        self.assertEqual(thread.call_count, 2)

    def test_cache_errors_include_django_redis_interrupted(self):
        self.assertIn(ConnectionInterrupted, throttles.cache_errors())


def broken_cache(exc):
    cache = mock.Mock()
    for name in ('get', 'set', 'add', 'incr', 'decr'):
        getattr(cache, name).side_effect = exc
    return cache


REDIS_DOWN = (redis.exceptions.ConnectionError('down'), ConnectionError('down'), ConnectionInterrupted(connection=None))


class ThrottleBrokenCacheMixin:
    """Подменяет кэш throttle (не весь cache проекта: капча и идемпотентность живут отдельно)."""

    def break_throttle_cache(self, exc):
        patcher = mock.patch.object(SimpleRateThrottle, 'cache', broken_cache(exc))
        patcher.start()
        self.addCleanup(patcher.stop)
        alert = mock.patch('core.throttles._alert_once')
        self.alert = alert.start()
        self.addCleanup(alert.stop)
