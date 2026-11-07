"""GET /healthz (задача 7.3, 23-D105): живость для healthcheck контейнеров и uptime-монитора."""
from unittest import mock

from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings


class HealthzTests(TestCase):
    def test_anonymous_gets_ok_without_cache(self):
        with mock.patch.dict('os.environ', {'REDIS_URL': ''}):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'db': 'ok', 'cache': 'skipped'})
        self.assertIn('no-store', response['Cache-Control'])

    def test_db_failure_returns_503_without_exception_text(self):
        with mock.patch.dict('os.environ', {'REDIS_URL': ''}), \
                mock.patch('core.health.connection.cursor', side_effect=OperationalError('secret-host:5432 refused')):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'error', 'db': 'error', 'cache': 'skipped'})
        self.assertNotIn('secret-host', response.content.decode())
        self.assertIn('no-store', response['Cache-Control'])

    def test_cache_checked_when_redis_url_set(self):
        with mock.patch.dict('os.environ', {'REDIS_URL': 'redis://:x@redis:6379/0'}):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'db': 'ok', 'cache': 'ok'})

    def test_cache_failure_returns_503(self):
        with mock.patch.dict('os.environ', {'REDIS_URL': 'redis://:x@redis:6379/0'}), \
                mock.patch('core.health.cache.set', side_effect=ConnectionError('redis://:pw@redis down')):
            response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'error', 'db': 'ok', 'cache': 'error'})
        self.assertNotIn('pw', response.content.decode())

    def test_not_throttled(self):
        with mock.patch.dict('os.environ', {'REDIS_URL': ''}):
            codes = {self.client.get('/healthz').status_code for _ in range(100)}
        self.assertEqual(codes, {200})

    def test_head_returns_200_without_body(self):
        with mock.patch.dict('os.environ', {'REDIS_URL': ''}):
            response = self.client.head('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')

    def test_post_not_allowed(self):
        self.assertEqual(self.client.post('/healthz').status_code, 405)


class HealthzRouteTests(SimpleTestCase):
    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_route_has_no_api_prefix(self):
        from django.urls import reverse
        self.assertEqual(reverse('healthz'), '/healthz')
