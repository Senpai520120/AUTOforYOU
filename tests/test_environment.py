"""Страховочные тесты изоляции (задача 0.2): 23-D1, 23-D2 и сетевой предохранитель."""
import socket

from django.conf import settings
from django.core.cache import caches
from django.test import SimpleTestCase

from core.test_runner import ExternalNetworkBlocked


class TestTestEnvironmentIsolation(SimpleTestCase):

    def test_provider_keys_empty_under_runner(self):
        """23-D1: ключи внешних провайдеров обнулены независимо от .env."""
        for name in (
            'OPENDATABOT_API_KEY', 'APIFY_TOKEN', 'LIQPAY_PUBLIC_KEY',
            'LIQPAY_PRIVATE_KEY', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD',
            'TELEGRAM_BOT_TOKEN', 'TURNSTILE_SITE_KEY', 'TURNSTILE_SECRET_KEY',
        ):
            with self.subTest(setting=name):
                self.assertEqual(getattr(settings, name), '')
        self.assertEqual(settings.CAPTCHA_PROVIDER, 'off')
        self.assertEqual(
            settings.EMAIL_BACKEND, 'django.core.mail.backends.locmem.EmailBackend'
        )

    def test_cache_is_locmem_and_celery_eager(self):
        """23-D2: кэш — LocMem, Celery — eager, даже при заданном REDIS_URL."""
        from django.core.cache.backends.locmem import LocMemCache
        self.assertIsInstance(caches['default'], LocMemCache)
        self.assertIs(settings.CELERY_TASK_ALWAYS_EAGER, True)
        self.assertEqual(settings.CELERY_BROKER_URL, 'memory://')

    def test_runner_is_isolated(self):
        self.assertEqual(settings.TEST_RUNNER, 'core.test_runner.IsolatedDiscoverRunner')

    def test_outbound_connection_blocked(self):
        """Предохранитель: внешний хост -> понятное исключение, соединения нет."""
        with self.assertRaises(ExternalNetworkBlocked) as ctx:
            socket.create_connection(('example.com', 80), timeout=1)
        self.assertIn('Внешний сетевой запрос в тесте: example.com:80', str(ctx.exception))
        self.assertIn('Замокайте провайдер', str(ctx.exception))

    def test_outbound_socket_connect_blocked(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        with self.assertRaises(ExternalNetworkBlocked):
            s.connect(('93.184.216.34', 80))

    def test_localhost_allowed(self):
        """localhost не блокируется: закрытый порт -> ConnectionRefusedError."""
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()  # порт освобождён, слушателя нет
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(('127.0.0.1', port), timeout=10)  # Windows отказывает не мгновенно
