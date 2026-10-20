"""Мониторинг ошибок (задача 7.6): адаптер, фильтр ПДн событий, эндпоинт client-errors.

sentry_sdk.init замокан, сети нет.
"""
import json
import logging
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from core import monitoring
from tests.base import CleanCacheTestCase

URL = '/api/v1/monitoring/client-errors/'
DSN = 'https://key@example.invalid/1'


class MonitoringStateMixin:
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(monitoring, '_enabled', False)
        patcher.start()
        self.addCleanup(patcher.stop)


class InitMonitoringTests(MonitoringStateMixin, CleanCacheTestCase):
    def test_empty_dsn_disabled_and_sdk_not_initialized(self):
        with mock.patch('sentry_sdk.init') as init:
            self.assertFalse(monitoring.init_monitoring('web', env={'SENTRY_DSN': ''}))
        init.assert_not_called()
        self.assertFalse(monitoring.is_enabled())

    def test_dsn_initializes_once_without_pii(self):
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration

        with mock.patch('sentry_sdk.init') as init, mock.patch('sentry_sdk.set_tag') as tag:
            self.assertTrue(monitoring.init_monitoring('celery', env={'SENTRY_DSN': DSN}))
            self.assertTrue(monitoring.init_monitoring('celery', env={'SENTRY_DSN': DSN}))
        init.assert_called_once()
        kw = init.call_args.kwargs
        self.assertIs(kw['send_default_pii'], False)
        self.assertEqual(kw['traces_sample_rate'], 0.0)
        self.assertEqual(kw['environment'], 'production')
        self.assertIs(kw['before_send'], monitoring.before_send)
        self.assertIs(kw['before_send_transaction'], monitoring.before_send)
        kinds = {type(i) for i in kw['integrations']}
        self.assertTrue({DjangoIntegration, CeleryIntegration} <= kinds)
        tag.assert_called_with('component', 'celery')

    def test_environment_and_release_from_env(self):
        with mock.patch('sentry_sdk.init') as init, mock.patch('sentry_sdk.set_tag'):
            monitoring.init_monitoring('web', env={'SENTRY_DSN': DSN, 'DEBUG': 'true', 'IMAGE_TAG': 'v1.2'})
        self.assertEqual(init.call_args.kwargs['environment'], 'development')
        self.assertEqual(init.call_args.kwargs['release'], 'v1.2')

    def test_bad_dsn_does_not_raise_and_does_not_log_dsn(self):
        with mock.patch('sentry_sdk.init', side_effect=Exception('BadDsn ' + DSN)), \
                self.assertLogs('core.monitoring', 'WARNING') as logs:
            self.assertFalse(monitoring.init_monitoring('web', env={'SENTRY_DSN': DSN}))
        self.assertNotIn('example.invalid', '\n'.join(logs.output))
        self.assertFalse(monitoring.is_enabled())

    def test_capture_message_noop_when_disabled(self):
        with mock.patch('sentry_sdk.capture_message') as cap:
            self.assertFalse(monitoring.capture_message('x'))
        cap.assert_not_called()


class BeforeSendTests(CleanCacheTestCase):
    def test_event_scrubbed(self):
        event = {
            'message': 'fail for ivan@test.com +380501234567',
            'request': {
                'url': 'https://site/api/x/?token=abc&email=a@b.cc', 'query_string': 'token=abc',
                'cookies': {'sessionid': 'S1'}, 'data': {'password': 'P1'},
                'headers': {'Authorization': 'Bearer T1', 'Cookie': 'access=C1', 'X-CSRFToken': 'X1',
                            'User-Agent': 'UA'},
            },
            'user': {'id': 7, 'email': 'ivan@test.com', 'ip_address': '1.2.3.4'},
            'exception': {'values': [{'value': 'bad phone 0671234567', 'stacktrace': {'frames': [
                {'function': 'f', 'vars': {'email': 'v@x.yz'}, 'context_line': "send('ctx@line.com')",
                 'pre_context': ['# pre@ctx.com'], 'post_context': ['# post@ctx.com']}]}}]},
            'threads': {'values': [{'stacktrace': {'frames': [{'vars': {'token': 'TH1'},
                                                              'context_line': 'thread@ctx.com'}]}}]},
            'extra': {'contact': 'z@z.zz'},
            'breadcrumbs': {'values': [{'message': 'GET /x?token=abc', 'data': {'url': '/x?token=abc'}}]},
        }
        out = json.dumps(monitoring.before_send(event, None), ensure_ascii=False)
        for leaked in ('ivan@test.com', '380501234567', 'token=abc', 'a@b.cc', 'S1', 'P1', 'T1', 'C1', 'X1',
                       '1.2.3.4', '0671234567', 'v@x.yz', 'z@z.zz', 'ctx@line.com', 'pre@ctx.com',
                       'post@ctx.com', 'TH1', 'thread@ctx.com'):
            self.assertNotIn(leaked, out)
        self.assertEqual(monitoring.before_send(event, None)['user'], {'id': 7})
        self.assertIn('UA', out)

    def test_django_request_repr_and_query_removed(self):
        event = {
            'extra': {'request': "<WSGIRequest: GET '/api/x/?q=Ivan+Petrenko'>", 'note': "see /api/y/?vin=WAUZZZ1"},
            'logentry': {'message': 'Internal Server Error: %s', 'params': ['/api/x/']},
            'request': {'url': '/x', 'headers': {'Referer': 'https://site/search?q=Ivan+Petrenko',
                                                 'X-Forwarded-For': '9.9.9.9'}},
            'breadcrumbs': {'values': [{'message': 'GET /api/z/?q=Olena', 'data': {'request': '<WSGIRequest ?q=Olena>'}}]},
        }
        result = monitoring.before_send(event, None)
        out = json.dumps(result, ensure_ascii=False)
        for leaked in ('Ivan', 'Petrenko', 'WAUZZZ1', 'Olena', '9.9.9.9'):
            self.assertNotIn(leaked, out)
        self.assertIn('/api/y/', out)
        self.assertNotIn('request', result['extra'])  # repr запроса не уходит вовсе
        self.assertEqual(set(result['request']['headers']), set())  # Referer и XFF выброшены

    def test_transaction_spans_scrubbed(self):
        event = {'type': 'transaction', 'transaction': '/api/x/?q=Ivan',
                 'request': {'url': '/api/x/?q=Ivan', 'query_string': 'q=Ivan'},
                 'spans': [{'description': 'GET http://backend/api/?email=a@b.cc&q=Ivan', 'data': {'url': '/p?q=Ivan'}}]}
        out = json.dumps(monitoring.before_send(event, None), ensure_ascii=False)
        self.assertNotIn('Ivan', out)
        self.assertNotIn('a@b.cc', out)

    def test_breadcrumb_scrubbed(self):
        crumb = monitoring.before_breadcrumb({'message': 'login a@b.cc', 'data': {'url': '/p?code=1'}}, None)
        self.assertEqual(crumb['data']['url'], '/p')
        self.assertNotIn('a@b.cc', crumb['message'])


class ClientErrorEndpointTests(MonitoringStateMixin, CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.payload = {'message': 'TypeError: x is undefined for a@b.cc', 'digest': '123',
                        'path': '/local/5?phone=0671234567'}

    def _post(self, payload, **kw):
        return self.client.post(URL, json.dumps(payload), content_type='application/json', **kw)

    def test_valid_report_sent_when_enabled(self):
        with mock.patch.object(monitoring, '_enabled', True), mock.patch('sentry_sdk.capture_message') as cap:
            resp = self._post(self.payload)
        self.assertEqual(resp.status_code, 204)
        cap.assert_called_once()
        self.assertNotIn('a@b.cc', cap.call_args.args[0])

    def test_extra_has_component_and_path_without_query(self):
        with mock.patch('core.monitoring_views.capture_message') as cap:
            self.assertEqual(self._post(self.payload).status_code, 204)
        extra = cap.call_args.kwargs['extra']
        self.assertEqual(extra['component'], 'frontend')
        self.assertEqual(extra['path'], '/local/5')

    def test_disabled_monitoring_still_204_without_event(self):
        with mock.patch('sentry_sdk.capture_message') as cap:
            self.assertEqual(self._post(self.payload).status_code, 204)
        cap.assert_not_called()

    def test_invalid_payloads_400(self):
        with mock.patch('core.monitoring_views.capture_message') as cap:
            for bad in ({}, {'message': ''}, {'message': 'x' * 501}, {'message': 'x', 'component': 'evil'}):
                self.assertEqual(self._post(bad).status_code, 400, bad)
            self.assertEqual(self.client.post(URL, 'not json', content_type='application/json').status_code, 400)
        cap.assert_not_called()

    def test_body_over_4kb_rejected(self):
        with mock.patch('core.monitoring_views.capture_message') as cap:
            resp = self._post({'message': 'x', 'junk': 'y' * 5000})  # лишнее поле сериализатор бы пропустил
        self.assertEqual(resp.status_code, 400)
        cap.assert_not_called()

    def test_external_cannot_pretend_to_be_ssr(self):
        with mock.patch('core.monitoring_views.capture_message') as cap:
            self._post({**self.payload, 'component': 'frontend-ssr'}, HTTP_X_FORWARDED_FOR='5.5.5.5')
            self.assertEqual(cap.call_args.kwargs['extra']['component'], 'frontend')
            self._post({**self.payload, 'component': 'frontend-ssr'})
            self.assertEqual(cap.call_args.kwargs['extra']['component'], 'frontend-ssr')

    def test_chunked_body_over_limit_rejected_and_bad_length_header(self):
        import io

        from rest_framework.exceptions import ParseError

        from core.monitoring_views import _SizeLimitedJSONParser
        request = mock.Mock(META={})  # без Content-Length (chunked)
        with self.assertRaisesMessage(ParseError, 'завелике'):
            _SizeLimitedJSONParser().parse(io.BytesIO(b'{"message": "' + b'y' * 5000 + b'"}'), None,
                                           {'request': request})
        request = mock.Mock(META={'CONTENT_LENGTH': 'abc'})
        data = _SizeLimitedJSONParser().parse(io.BytesIO(b'{"message": "x"}'), None, {'request': request})
        self.assertEqual(data, {'message': 'x'})

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_works_without_csrf_with_session_cookie(self):
        # Эндпоинт не читает сессию: живая cookie без X-CSRFToken не превращает отчёт в 403.
        from django.conf import settings
        from rest_framework_simplejwt.tokens import RefreshToken

        from tests.factories import make_user
        client = APIClient(enforce_csrf_checks=True)
        client.cookies[settings.AUTH_COOKIE_ACCESS_NAME] = str(RefreshToken.for_user(make_user()).access_token)
        with mock.patch('core.monitoring_views.capture_message'):
            resp = client.post(URL, json.dumps(self.payload), content_type='application/json')
        self.assertEqual(resp.status_code, 204)

    def test_throttle(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'client_errors': '2/min'}), \
                mock.patch('core.monitoring_views.capture_message'):
            for _ in range(2):
                self.assertEqual(self._post(self.payload).status_code, 204)
            self.assertEqual(self._post(self.payload).status_code, 429)


class MonitoringTestCommandTests(MonitoringStateMixin, CleanCacheTestCase):
    def test_disabled(self):
        out = StringIO()
        with mock.patch.dict('os.environ', {'SENTRY_DSN': ''}):
            call_command('monitoring_test', stdout=out)
        self.assertIn('выключен', out.getvalue())

    @override_settings(IS_TESTING=False)
    def test_enabled_sends_event(self):
        out = StringIO()
        with mock.patch.dict('os.environ', {'SENTRY_DSN': DSN}), mock.patch('sentry_sdk.init'), \
                mock.patch('sentry_sdk.set_tag'), mock.patch('sentry_sdk.capture_message') as cap, \
                mock.patch('sentry_sdk.flush'):
            call_command('monitoring_test', stdout=out)
        cap.assert_called_once()
        self.assertIn('отправлено', out.getvalue())


class TestingGuardTests(MonitoringStateMixin, CleanCacheTestCase):
    def test_env_dsn_ignored_in_tests(self):
        with mock.patch.dict('os.environ', {'SENTRY_DSN': DSN}), mock.patch('sentry_sdk.init') as init:
            self.assertFalse(monitoring.init_monitoring('bot'))
        init.assert_not_called()


class CeleryAndLoggingIntegrationTests(MonitoringStateMixin, CleanCacheTestCase):
    def test_celery_signals_connected(self):
        from celery.signals import beat_init, worker_process_init

        import core.celery as cc
        receivers = [r[1]() for r in worker_process_init.receivers]
        self.assertIn(cc._init_monitoring_worker, receivers)
        self.assertIn(cc._init_monitoring_beat, [r[1]() for r in beat_init.receivers])
        with mock.patch('core.monitoring.init_monitoring') as init:
            cc._init_monitoring_worker()
        init.assert_called_once_with('celery')

    def test_error_logs_are_events_warnings_breadcrumbs(self):
        from sentry_sdk.integrations.logging import LoggingIntegration

        with mock.patch('sentry_sdk.init') as init, mock.patch('sentry_sdk.set_tag'):
            monitoring.init_monitoring('web', env={'SENTRY_DSN': DSN})
        logging_int = next(i for i in init.call_args.kwargs['integrations'] if isinstance(i, LoggingIntegration))
        self.assertEqual(logging_int._handler.level, logging.ERROR)
        self.assertEqual(logging_int._breadcrumb_handler.level, logging.WARNING)


@override_settings(DEBUG=False)
class WsgiInitTests(CleanCacheTestCase):
    def test_wsgi_and_asgi_call_init(self):
        from pathlib import Path

        from django.conf import settings
        for name in ('wsgi.py', 'asgi.py'):
            src = (Path(settings.BASE_DIR) / 'core' / name).read_text(encoding='utf-8')
            self.assertIn("init_monitoring('web')", src, name)
        bot = (Path(settings.BASE_DIR) / 'telegram_bot' / 'management' / 'commands' / 'run_bot.py').read_text(
            encoding='utf-8')
        self.assertIn("init_monitoring('bot')", bot)
