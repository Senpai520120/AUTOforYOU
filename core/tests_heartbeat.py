"""Сигнал «Celery жив» внешнему сервису-сторожу (задача 9.55)."""
from unittest import mock

import httpx
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from core.tasks import send_celery_heartbeat

URL = 'https://hc.example/secret-uuid'


class CeleryHeartbeatTests(SimpleTestCase):
    @override_settings(CELERY_HEARTBEAT_URL='')
    def test_empty_url_makes_no_request(self):
        with mock.patch('core.tasks.httpx.get') as get:
            send_celery_heartbeat()
        get.assert_not_called()

    @override_settings(CELERY_HEARTBEAT_URL=URL)
    def test_pings_configured_url_with_timeout(self):
        with mock.patch('core.tasks.httpx.get') as get:
            send_celery_heartbeat()
        get.assert_called_once_with(URL, timeout=10)
        get.return_value.raise_for_status.assert_called_once_with()

    @override_settings(CELERY_HEARTBEAT_URL=URL)
    def test_network_error_is_logged_without_secret_url(self):
        error = httpx.ConnectError(f'cannot connect to {URL}')
        with mock.patch('core.tasks.httpx.get', side_effect=error), \
                self.assertLogs('core.tasks', level='WARNING') as logs:
            send_celery_heartbeat()
        self.assertIn('ConnectError', logs.output[0])
        self.assertNotIn('secret-uuid', logs.output[0])

    @override_settings(CELERY_HEARTBEAT_URL=URL)
    def test_error_status_is_logged_not_raised(self):
        response = httpx.Response(500, request=httpx.Request('GET', URL))
        with mock.patch('core.tasks.httpx.get', return_value=response), \
                self.assertLogs('core.tasks', level='WARNING') as logs:
            send_celery_heartbeat()
        self.assertIn('HTTPStatusError', logs.output[0])
        self.assertNotIn('secret-uuid', logs.output[0])

    @override_settings(CELERY_HEARTBEAT_URL='not a url\n')
    def test_invalid_url_is_logged_not_raised(self):
        with self.assertLogs('core.tasks', level='WARNING') as logs:
            send_celery_heartbeat()
        self.assertEqual(len(logs.output), 1)

    def test_scheduled_every_5_minutes_and_expires_before_next_run(self):
        entry = settings.CELERY_BEAT_SCHEDULE['celery-heartbeat']
        self.assertEqual(entry['task'], 'core.tasks.send_celery_heartbeat')
        self.assertEqual(entry['schedule'].minute, set(range(0, 60, 5)))
        self.assertLess(entry['options']['expires'], 300)
