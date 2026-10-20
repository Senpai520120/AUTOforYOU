"""Прод-настройки Django: SECRET_KEY, DEBUG, STORAGES, логи без ПДн (задача 7.2, 23-D106...D108).

Настройки читаются при импорте, поэтому старт Django проверяется в subprocess с нужным env,
а хранилища и ключ - через чистые функции core/storage_settings.py и core/secret_key.py.
"""
import io
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import path

from core.logging_filters import PiiScrubFilter, RequestPathFilter, scrub
from core.secret_key import check_debug_hosts, resolve_secret_key
from core.storage_settings import build_storage_settings

ROOT = Path(settings.BASE_DIR)
LONG_KEY = 'k' * 20 + 'Zx9!q' * 8  # 60 символов, без маркеров-заглушек
OLD_FALLBACK = 'django-insecure-ea+&)bt%jlzm6=lms#20m8khy&^!fg*41^a+l(&3n7e!5hoal+'


def _django_start(**env):
    """Старт Django в отдельном процессе. Все значимые переменные задаются явно: .env не подмешивается."""
    base = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'SYSTEMROOT', 'VIRTUAL_ENV')}
    base.update({
        'DJANGO_SETTINGS_MODULE': 'core.settings', 'DATABASE_URL': '', 'REDIS_URL': '',
        'SECRET_KEY': '', 'DEBUG': 'false', 'ALLOWED_HOSTS': '', 'ALLOW_DEBUG_ON_PUBLIC_HOST': '',
        'SITE_URL': 'https://example.com',
    })
    base.update(env)
    code = 'import django; django.setup(); from django.conf import settings; print("KEY=" + settings.SECRET_KEY)'
    return subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=base, capture_output=True, text=True, timeout=120)


class DjangoStartupTests(SimpleTestCase):
    def test_empty_key_in_prod_fails(self):
        r = _django_start(ALLOWED_HOSTS='example.com')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('ImproperlyConfigured', r.stderr)
        self.assertIn('SECRET_KEY', r.stderr)

    def test_placeholder_key_in_prod_fails(self):
        r = _django_start(ALLOWED_HOSTS='example.com',
                          SECRET_KEY='local-docker-dev-secret-key-REPLACE-BEFORE-PRODUCTION-aUTOforYOU2026')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('заглушку', r.stderr)

    def test_long_real_key_in_prod_starts(self):
        r = _django_start(ALLOWED_HOSTS='example.com', SECRET_KEY=LONG_KEY)
        self.assertEqual(r.returncode, 0, r.stderr[-500:])

    def test_prod_without_allowed_hosts_fails(self):
        r = _django_start(SECRET_KEY=LONG_KEY)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('ALLOWED_HOSTS', r.stderr)

    def test_debug_with_public_host_fails_unless_explicitly_allowed(self):
        r = _django_start(DEBUG='true', ALLOWED_HOSTS='example.com', SECRET_KEY=LONG_KEY)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('DEBUG=false', r.stderr)
        r = _django_start(DEBUG='true', ALLOWED_HOSTS='example.com', SECRET_KEY=LONG_KEY,
                          ALLOW_DEBUG_ON_PUBLIC_HOST='true')
        self.assertEqual(r.returncode, 0, r.stderr[-500:])

    def test_debug_with_empty_allowed_hosts_but_public_site_url_fails(self):
        # Пустой ALLOWED_HOSTS при DEBUG даёт localhost-хосты; сервер с Host: localhost иначе проходил бы.
        r = _django_start(DEBUG='true', SECRET_KEY=LONG_KEY, SITE_URL='https://example.com')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('example.com', r.stderr)

    def test_entrypoint_refuses_debug_for_gunicorn(self):
        env = {'PATH': os.environ.get('PATH', ''), 'DEBUG': 'true'}
        r = subprocess.run(['bash', str(ROOT / 'docker' / 'entrypoint.sh')], env=env, capture_output=True,
                           text=True, timeout=30, cwd='/')
        self.assertEqual(r.returncode, 1)
        self.assertIn('DEBUG=true недопустим', r.stderr)

    def test_debug_without_key_generates_persistent_dev_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            key_file = os.path.join(tmp, 'dev_key')
            first = _django_start(DEBUG='true', ALLOWED_HOSTS='localhost', SITE_URL='', DEV_SECRET_KEY_FILE=key_file)
            self.assertEqual(first.returncode, 0, first.stderr[-500:])
            second = _django_start(DEBUG='true', ALLOWED_HOSTS='localhost', SITE_URL='', DEV_SECRET_KEY_FILE=key_file)
            key1 = first.stdout.strip().split('KEY=')[-1]
            self.assertEqual(second.stdout.strip().split('KEY=')[-1], key1)
            self.assertGreaterEqual(len(key1), 50)
            self.assertNotEqual(key1, OLD_FALLBACK)

    def test_no_insecure_fallback_in_settings(self):
        self.assertNotIn('django-insecure-', (ROOT / 'core' / 'settings.py').read_text(encoding='utf-8'))
        self.assertNotIn('autoforyou.ua', (ROOT / 'core' / 'settings.py').read_text(encoding='utf-8'))

    def test_dev_key_file_ignored_by_git_and_docker(self):
        for name in ('.gitignore', '.dockerignore'):
            self.assertIn('.dev_secret_key', (ROOT / name).read_text(encoding='utf-8'), name)


class SecretKeyFunctionTests(SimpleTestCase):
    def test_testing_gets_random_key_per_run(self):
        a = resolve_secret_key({}, debug=False, testing=True, base_dir='/nonexistent')
        b = resolve_secret_key({}, debug=False, testing=True, base_dir='/nonexistent')
        self.assertNotEqual(a, b)

    def test_short_prod_key_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'короче 50'):
            resolve_secret_key({'SECRET_KEY': 'x' * 49}, debug=False, testing=False, base_dir='.')

    def test_unwritable_dir_falls_back_to_memory_key(self):
        env = {'DEV_SECRET_KEY_FILE': '/nonexistent-dir/key'}
        with self.assertLogs('core.secret_key', 'WARNING'):
            key = resolve_secret_key(env, debug=True, testing=False, base_dir='.')
        self.assertGreaterEqual(len(key), 50)

    def test_example_placeholders_rejected(self):
        for key in ('e2e-only-secret-key-not-for-production-0123456789abcdef', 'your-django-secret-key-here' * 3):
            with self.assertRaisesMessage(ImproperlyConfigured, 'заглушку'):
                resolve_secret_key({'SECRET_KEY': key}, debug=False, testing=False, base_dir='.')

    def test_cors_origin_counts_as_public_host(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'shop.example.com'):
            check_debug_hosts({'CORS_ALLOWED_ORIGINS': 'http://localhost,https://shop.example.com'},
                              debug=True, allowed_hosts=['localhost'])

    def test_safe_hosts_allowed_with_debug(self):
        check_debug_hosts({}, debug=True, allowed_hosts=['localhost', '127.0.0.1', '0.0.0.0', 'backend'])


class StorageSettingsTests(SimpleTestCase):
    S3 = {'S3_BUCKET_NAME': 'media', 'AWS_ACCESS_KEY_ID': 'AK', 'AWS_SECRET_ACCESS_KEY': 'SK'}

    def test_local_by_default(self):
        cfg = build_storage_settings({}, '/app')
        self.assertEqual(cfg['STORAGES']['default']['BACKEND'], 'django.core.files.storage.FileSystemStorage')
        self.assertEqual(cfg['MEDIA_ROOT'], os.path.join('/app', 'media'))
        self.assertEqual(cfg['MEDIA_URL'], '/media/')
        self.assertFalse(cfg['USE_S3'])

    def test_s3_media_static_stays_local(self):
        cfg = build_storage_settings(self.S3, '/app')
        self.assertEqual(cfg['STORAGES']['default']['BACKEND'], 'storages.backends.s3boto3.S3Boto3Storage')
        self.assertEqual(cfg['STORAGES']['staticfiles']['BACKEND'],
                         'django.contrib.staticfiles.storage.StaticFilesStorage')
        self.assertTrue(cfg['MEDIA_ROOT'])
        self.assertNotIn('DEFAULT_FILE_STORAGE', cfg)
        self.assertNotIn('STATICFILES_STORAGE', cfg)
        self.assertEqual((cfg['AWS_DEFAULT_ACL'], cfg['AWS_QUERYSTRING_AUTH']), ('private', True))
        self.assertIn('amazonaws.com', cfg['MEDIA_URL'])  # AWS без endpoint - шаблон остаётся

    def test_r2_endpoint_without_custom_domain_has_no_amazonaws_url(self):
        cfg = build_storage_settings({**self.S3, 'S3_ENDPOINT_URL': 'https://acc.r2.cloudflarestorage.com',
                                      'S3_REGION': 'auto'}, '/app')
        self.assertNotIn('amazonaws.com', cfg['MEDIA_URL'])
        self.assertEqual(cfg['AWS_S3_ENDPOINT_URL'], 'https://acc.r2.cloudflarestorage.com')
        self.assertTrue(cfg['AWS_QUERYSTRING_AUTH'])

    def test_custom_domain(self):
        cfg = build_storage_settings({**self.S3, 'S3_CUSTOM_DOMAIN': 'cdn.example.com'}, '/app')
        self.assertEqual(cfg['MEDIA_URL'], 'https://cdn.example.com/')
        self.assertEqual(cfg['AWS_S3_CUSTOM_DOMAIN'], 'cdn.example.com')

    def test_incomplete_s3_vars_stay_local(self):
        cfg = build_storage_settings({'S3_BUCKET_NAME': 'media'}, '/app')
        self.assertEqual(cfg['STORAGES']['default']['BACKEND'], 'django.core.files.storage.FileSystemStorage')

    def test_default_storage_is_s3_without_network(self):
        from django.core.files.storage import default_storage
        from storages.backends.s3boto3 import S3Boto3Storage

        cfg = build_storage_settings({**self.S3, 'S3_ENDPOINT_URL': 'https://acc.r2.cloudflarestorage.com'}, '/app')
        aws = {k: v for k, v in cfg.items() if k.startswith('AWS_')}
        # override_settings(STORAGES=...) сбрасывает storages и default_storage (сигнал setting_changed).
        with override_settings(STORAGES=cfg['STORAGES'], **aws):
            url = default_storage.url('local_listings/a.jpg')  # подпись считается локально, без сети
            self.assertIsInstance(default_storage._wrapped, S3Boto3Storage)
        self.assertNotIn('amazonaws.com', url)
        self.assertIn('acc.r2.cloudflarestorage.com', url)

    def test_private_storage_uses_separate_bucket_when_set(self):
        from core.uploads import private_media_storage

        with override_settings(USE_S3=True, AWS_STORAGE_BUCKET_NAME='media', PRIVATE_S3_BUCKET_NAME='private-media',
                               AWS_ACCESS_KEY_ID='AK', AWS_SECRET_ACCESS_KEY='SK', AWS_S3_REGION_NAME='auto',
                               AWS_S3_ENDPOINT_URL='https://acc.r2.cloudflarestorage.com'):
            self.assertEqual(private_media_storage().bucket_name, 'private-media')

    def test_private_storage_ignores_public_custom_domain(self):
        from core.uploads import private_media_storage

        with override_settings(USE_S3=True, AWS_STORAGE_BUCKET_NAME='media', AWS_ACCESS_KEY_ID='AK',
                               AWS_SECRET_ACCESS_KEY='SK', AWS_S3_CUSTOM_DOMAIN='cdn.example.com',
                               AWS_S3_ENDPOINT_URL='https://acc.r2.cloudflarestorage.com',
                               AWS_S3_REGION_NAME='auto', AWS_S3_SIGNATURE_VERSION='s3v4'):
            url = private_media_storage().url('tracking_photos/x.jpg')
        self.assertNotIn('cdn.example.com', url)
        self.assertIn('X-Amz-Signature', url)


class PiiScrubTests(SimpleTestCase):
    def _format(self, msg, *args, name='app', filters=(PiiScrubFilter(),)):
        record = logging.LogRecord(name, logging.INFO, __file__, 1, msg, args, None)
        for f in filters:
            f.filter(record)
        return logging.Formatter('%(message)s').format(record)

    def test_email_phone_token_masked(self):
        out = self._format('user test@example.com phone +380501234567 /reset?token=abc')
        for leaked in ('test@example.com', '+380501234567', 'abc'):
            self.assertNotIn(leaked, out)

    def test_args_are_formatted_and_masked(self):
        out = self._format('login %s from %s', 'a@b.cc', '0671234567')
        self.assertEqual(out, 'login *** from ***')

    def test_ua_and_international_phone_formats(self):
        for phone in ('050 123 45 67', '(067)123-45-67', '380671234567', '+1 (415) 555-2671', '+44 20 7946 0958'):
            self.assertNotIn(phone, scrub(f'тел {phone}.'), phone)

    def test_secrets_in_query_json_and_headers(self):
        text = scrub('?uid=MQ&key=K1&signature=S1 {"password": "P1", "refresh": "R1"} '
                     'Authorization: Bearer T1 Cookie: access=C1')
        for leaked in ('MQ', 'K1', 'S1', 'P1', 'R1', 'T1', 'C1'):
            self.assertNotIn(leaked, text)

    def test_session_cookie_jwt_encoded_phone_and_names(self):
        # Каждый случай отдельной строкой: правило Cookie маскирует строку до конца и скрыло бы остальные.
        cases = {
            'HTTP_COOKIE: sessionid=abc123': 'abc123',
            'admin sessionid=abc124 seen': 'abc124',
            'csrftoken=zz9 sent': 'zz9',
            '/x?t=eyJhbGci.eyJzdWIi.sig-1 ok': 'eyJhbGci',
            'phone=%2B380501234567&x=1': '380501234567',
            '{"first_name": "Іван", "id": 1}': 'Іван',
        }
        for text, leaked in cases.items():
            self.assertNotIn(leaked, scrub(text), text)

    def test_request_path_filter_drops_request_and_query(self):
        record = logging.LogRecord('django.server', logging.INFO, __file__, 1, '"%s" %s %s',
                                   ('GET /api/x/?token=T9 HTTP/1.1', '200', '5'), None)
        record.request = object()
        RequestPathFilter().filter(record)
        self.assertIsNone(record.request)
        self.assertNotIn('T9', record.getMessage())

    def test_dates_and_ids_not_mangled(self):
        text = 'дата 2026-10-20 08:56:00, lead_id=17, order 12345, AFY-2026-0001'
        self.assertEqual(scrub(text), text)

    def test_exception_text_masked(self):
        try:
            raise ValueError('bad email x@y.zz')
        except ValueError:
            record = logging.LogRecord('app', logging.ERROR, __file__, 1, 'boom', (), sys.exc_info())
        PiiScrubFilter().filter(record)
        self.assertNotIn('x@y.zz', logging.Formatter().format(record))

    def test_handlers_have_pii_filter(self):
        for name in ('', 'django', 'django.request', 'users.services'):
            logger = logging.getLogger(name)
            while logger and not logger.handlers:
                logger = logger.parent
            kinds = {type(f) for h in logger.handlers for f in h.filters}
            self.assertIn(PiiScrubFilter, kinds, name or 'root')
            self.assertIn(RequestPathFilter, kinds, name or 'root')


def _boom(request):
    raise RuntimeError('boom for a@b.cc')


urlpatterns = [path('api/boom/', _boom)]


@override_settings(ROOT_URLCONF='tests.test_prod_settings')
class RequestLogTests(TestCase):
    def test_500_log_has_no_query_or_email(self):
        logger = logging.getLogger('django.request')
        handler = logger.handlers[0]
        stream = io.StringIO()
        capture = logging.StreamHandler(stream)
        for f in handler.filters:
            capture.addFilter(f)
        logger.addHandler(capture)
        self.addCleanup(logger.removeHandler, capture)
        self.client.raise_request_exception = False
        resp = self.client.get('/api/boom/?email=a@b.cc&phone=+380501234567')
        self.assertEqual(resp.status_code, 500)
        out = stream.getvalue()
        self.assertIn('/api/boom/', out)
        for leaked in ('a@b.cc', '380501234567', '?email'):
            self.assertNotIn(leaked, out)


class NotificationLogTests(TestCase):
    def test_send_notification_log_has_no_telegram_id(self):
        from integrations.tasks import send_notification
        from tests.factories import make_user

        user = make_user(telegram_id=987654321)

        bot = mock.MagicMock()
        bot.send_message = mock.AsyncMock()
        bot.session.close = mock.AsyncMock()
        with override_settings(TELEGRAM_BOT_TOKEN='1:test'), mock.patch('aiogram.Bot', return_value=bot), \
                self.assertLogs('integrations.tasks', 'INFO') as logs:
            send_notification(user.pk, 'Привіт')
        text = '\n'.join(logs.output)
        self.assertIn(f'user pk={user.pk}', text)
        self.assertNotIn('987654321', text)
        self.assertNotIn('telegram_id', text)


class CeleryLoggingTests(SimpleTestCase):
    def test_worker_does_not_hijack_root_logger(self):
        # Иначе обработчик Celery без фильтра ПДн заменил бы LOGGING в celery_worker.
        from core.celery import app
        self.assertFalse(settings.CELERY_WORKER_HIJACK_ROOT_LOGGER)
        self.assertFalse(app.conf.worker_hijack_root_logger)


class BeatScheduleTests(SimpleTestCase):
    def test_flush_expired_tokens_scheduled_and_calls_command(self):
        tasks = {entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn('users.tasks.flush_expired_tokens', tasks)
        from users.tasks import flush_expired_tokens
        with mock.patch('users.tasks.call_command') as cmd:
            flush_expired_tokens()
        cmd.assert_any_call('flushexpiredtokens')


class DeployCheckTests(SimpleTestCase):
    @unittest.skip('ждёт задачу 7.1: build_security_settings (HSTS, SSL-редирект) ещё нет - 23-D106')
    def test_check_deploy_clean(self):
        pass
