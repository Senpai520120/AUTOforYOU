"""Антибот-адаптер и точки капчи (задача 1.6, Q2). Сеть мокается через patch('httpx.post')."""
import time
import uuid
from unittest import mock

import httpx
from django.core import signing
from django.test import RequestFactory, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from integrations.captcha import (
    FORM_TOKEN_SALT,
    CaptchaFailed,
    DisabledVerifier,
    HoneypotVerifier,
    TurnstileVerifier,
    get_captcha_verifier,
    issue_form_token,
    require_captcha,
)
from tests.base import CleanCacheTestCase
from tests.factories import TEST_PASSWORD, auth_client, make_user
from users.tests_email_verify import REG

REGISTER_URL = '/api/v1/auth/register/'
TOKEN_URL = '/api/v1/auth/token/'
APPLY_URL = '/api/v1/dealers/apply/'
SECRET = 'TOP-SECRET-turnstile'
TURNSTILE = dict(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SITE_KEY='pub', TURNSTILE_SECRET_KEY=SECRET)
APPLY_DATA = {
    'company_name': 'ТОВ Авто', 'full_name': 'Іван Іванов', 'contact_phone': '+380991234567',
    'documents': 'https://drive.google.com/doc', 'agreed_to_processing': True, 'confirmed_age_18': True,
}


def _siteverify(success):
    response = mock.Mock()
    response.json.return_value = {'success': success}
    return mock.patch('httpx.post', return_value=response)


def _old_form_token(ip='203.0.113.5', age=60, nonce=None):
    payload = {'t': int(time.time()) - age, 'n': nonce or uuid.uuid4().hex, 'ip': ip}
    return signing.dumps(payload, salt=FORM_TOKEN_SALT)


def _assert_captcha_failed(test, resp):
    test.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
    test.assertEqual(resp.json()['code'], 'captcha_failed')
    test.assertIn('captcha_token', resp.json())


class TestRequireCaptcha(CleanCacheTestCase):

    def _request(self):
        return RequestFactory().post('/x/', REMOTE_ADDR='203.0.113.5')

    def _fresh(self):
        return issue_form_token('203.0.113.5')

    @override_settings(**TURNSTILE)
    def test_success_passes_and_sends_secret_token_ip(self):
        with _siteverify(True) as post:
            require_captcha(self._request(), {'captcha_token': 'tok'}, point='register')
        self.assertEqual(post.call_args.kwargs['data'], {
            'secret': SECRET, 'response': 'tok', 'remoteip': '203.0.113.5',
        })
        self.assertEqual(post.call_args.kwargs['timeout'], 5)

    @override_settings(**TURNSTILE)
    def test_rejected_token_fails_and_logs_point_without_token_or_secret(self):
        with _siteverify(False), self.assertLogs('integrations.captcha', level='WARNING') as logs:
            with self.assertRaises(CaptchaFailed) as ctx:
                require_captcha(self._request(), {'captcha_token': 'secret-token-value'}, point='dealer_apply')
        self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')
        text = '\n'.join(logs.output)
        self.assertIn('dealer_apply', text)
        self.assertIn('invalid', text)
        self.assertNotIn('secret-token-value', text)
        self.assertNotIn(SECRET, text)

    @override_settings(**TURNSTILE)
    def test_network_error_fails_and_logs_without_secret(self):
        with mock.patch('httpx.post', side_effect=httpx.ConnectError(f'boom {SECRET}')):
            with self.assertLogs('integrations.captcha', level='WARNING') as logs:
                with self.assertRaises(CaptchaFailed) as ctx:
                    require_captcha(self._request(), {'captcha_token': 'tok'}, point='register')
        self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')
        text = '\n'.join(logs.output)
        self.assertIn('network', text)
        self.assertNotIn(SECRET, text)

    @override_settings(**TURNSTILE)
    def test_empty_token_with_turnstile_key_fails_without_network_call(self):
        with mock.patch('httpx.post') as post, self.assertLogs('integrations.captcha', level='WARNING') as logs:
            with self.assertRaises(CaptchaFailed) as ctx:
                require_captcha(self._request(), {}, point='register')
        self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')
        post.assert_not_called()
        self.assertIn('missing', '\n'.join(logs.output))

    @override_settings(**TURNSTILE)
    def test_extra_keys_are_in_failure_body(self):
        with self.assertRaises(CaptchaFailed) as ctx:
            require_captcha(self._request(), {}, point='login', extra={'captcha_required': True})
        self.assertIs(ctx.exception.detail['captcha_required'], True)

    @override_settings(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='')
    def test_captcha_fallback_to_honeypot(self):
        self.assertIsInstance(get_captcha_verifier(), HoneypotVerifier)
        with self.assertLogs('integrations.captcha', level='WARNING'):
            get_captcha_verifier()
        with self.assertRaises(CaptchaFailed) as ctx:
            require_captcha(self._request(), {'captcha_token': self._fresh(), 'website': 'spam'}, point='register')
        self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')

    @override_settings(CAPTCHA_PROVIDER='honeypot', CAPTCHA_MIN_FILL_SECONDS=3)
    def test_honeypot_requires_slow_enough_fill(self):
        with self.assertRaises(CaptchaFailed) as ctx:
            require_captcha(self._request(), {'captcha_token': self._fresh()}, point='register')
        self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')
        require_captcha(self._request(), {'captcha_token': _old_form_token()}, point='register')

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_honeypot_token_is_one_time(self):
        token = _old_form_token()
        require_captcha(self._request(), {'captcha_token': token}, point='register')
        with self.assertLogs('integrations.captcha', level='WARNING') as logs:
            with self.assertRaises(CaptchaFailed) as ctx:
                require_captcha(self._request(), {'captcha_token': token}, point='register')
        self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')
        self.assertIn('reuse', '\n'.join(logs.output))

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_honeypot_failure_not_caused_by_token_does_not_consume_it(self):
        token = _old_form_token()
        with self.assertRaises(CaptchaFailed):
            require_captcha(self._request(), {'captcha_token': token, 'website': 'spam'}, point='register')
        require_captcha(self._request(), {'captcha_token': token}, point='register')

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_honeypot_token_bound_to_ip(self):
        with self.assertRaises(CaptchaFailed):
            require_captcha(self._request(), {'captcha_token': _old_form_token(ip='198.51.100.9')}, point='register')

    @override_settings(CAPTCHA_PROVIDER='honeypot', CAPTCHA_FORM_TOKEN_MAX_AGE=3600)
    def test_honeypot_token_expires_after_max_age(self):
        with self.assertRaises(CaptchaFailed):
            require_captcha(self._request(), {'captcha_token': _old_form_token(age=3700)}, point='register')

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_config_issues_new_token_each_time_bound_to_requester(self):
        client = APIClient()
        first = client.get('/api/v1/auth/config/', REMOTE_ADDR='203.0.113.5').json()['captcha']['form_token']
        second = client.get('/api/v1/auth/config/', REMOTE_ADDR='203.0.113.5').json()['captcha']['form_token']
        self.assertNotEqual(first, second)
        self.assertEqual(signing.loads(first, salt=FORM_TOKEN_SALT)['ip'], '203.0.113.5')

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_honeypot_rejects_missing_and_forged_token(self):
        for data in ({}, {'captcha_token': 'forged'}):
            with self.assertRaises(CaptchaFailed) as ctx:
                require_captcha(self._request(), data, point='register')
            self.assertEqual(ctx.exception.detail['code'], 'captcha_failed')

    @override_settings(CAPTCHA_PROVIDER='off')
    def test_off_passes_everything(self):
        self.assertIsInstance(get_captcha_verifier(), DisabledVerifier)
        require_captcha(self._request(), {'website': 'spam'}, point='register')

    @override_settings(**TURNSTILE)
    def test_verify_returns_bool(self):
        verifier = TurnstileVerifier(SECRET)
        with _siteverify(True):
            self.assertIs(verifier.verify('t', '1.1.1.1'), True)
        with _siteverify(False):
            self.assertIs(verifier.verify('t', '1.1.1.1'), False)


class TestRegisterCaptcha(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    @override_settings(**TURNSTILE)
    def test_turnstile_success_registers(self):
        with _siteverify(True):
            resp = self.client.post(REGISTER_URL, {**REG, 'captcha_token': 'tok'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    @override_settings(**TURNSTILE)
    def test_turnstile_failure_returns_captcha_failed(self):
        with _siteverify(False):
            resp = self.client.post(REGISTER_URL, {**REG, 'captcha_token': 'tok'}, format='json')
        _assert_captcha_failed(self, resp)

    @override_settings(**TURNSTILE)
    def test_without_token_returns_captcha_failed(self):
        _assert_captcha_failed(self, self.client.post(REGISTER_URL, REG, format='json'))

    @override_settings(**TURNSTILE)
    def test_network_error_returns_captcha_failed(self):
        with mock.patch('httpx.post', side_effect=httpx.ConnectTimeout('t')):
            resp = self.client.post(REGISTER_URL, {**REG, 'captcha_token': 'tok'}, format='json')
        _assert_captcha_failed(self, resp)

    @override_settings(**TURNSTILE)
    def test_honeypot_always_on(self):
        with _siteverify(True):
            resp = self.client.post(
                REGISTER_URL, {**REG, 'captcha_token': 'tok', 'website': 'http://spam'}, format='json',
            )
        _assert_captcha_failed(self, resp)

    def test_captcha_off_registers_without_token(self):
        self.assertEqual(self.client.post(REGISTER_URL, REG, format='json').status_code, status.HTTP_201_CREATED)

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_honeypot_provider_with_form_token_registers(self):
        resp = self.client.post(REGISTER_URL, {**REG, 'captcha_token': _old_form_token(ip='127.0.0.1')}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_captcha_checked_before_user_creation(self):
        resp = self.client.post(REGISTER_URL, REG, format='json')
        _assert_captcha_failed(self, resp)
        from django.contrib.auth import get_user_model
        self.assertFalse(get_user_model().objects.filter(email=REG['email']).exists())


class TestDealerApplyCaptcha(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        self.client = auth_client(make_user('dealer-cap@test.com'))

    @override_settings(**TURNSTILE)
    def test_turnstile_success_creates_application(self):
        with _siteverify(True):
            resp = self.client.post(APPLY_URL, {**APPLY_DATA, 'captcha_token': 'tok'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    @override_settings(**TURNSTILE)
    def test_turnstile_failure_returns_captcha_failed(self):
        with _siteverify(False):
            resp = self.client.post(APPLY_URL, {**APPLY_DATA, 'captcha_token': 'tok'}, format='json')
        _assert_captcha_failed(self, resp)

    @override_settings(**TURNSTILE)
    def test_without_token_returns_captcha_failed(self):
        _assert_captcha_failed(self, self.client.post(APPLY_URL, APPLY_DATA, format='json'))

    @override_settings(**TURNSTILE)
    def test_network_error_returns_captcha_failed(self):
        with mock.patch('httpx.post', side_effect=httpx.ConnectError('x')):
            resp = self.client.post(APPLY_URL, {**APPLY_DATA, 'captcha_token': 'tok'}, format='json')
        _assert_captcha_failed(self, resp)


class TestLoginCaptcha(CleanCacheTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user('login-cap@test.com')

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _login(self, password, ip='10.1.1.1', **extra):
        return self.client.post(
            TOKEN_URL, {'email': self.user.email, 'password': password, **extra}, format='json', REMOTE_ADDR=ip,
        )

    @override_settings(**TURNSTILE, CAPTCHA_ON_LOGIN=True)
    def test_on_login_requires_captcha_always(self):
        resp = self._login(TEST_PASSWORD)
        _assert_captcha_failed(self, resp)
        self.assertIs(resp.json()['captcha_required'], True)
        with _siteverify(True):
            self.assertEqual(self._login(TEST_PASSWORD, captcha_token='tok').status_code, status.HTTP_200_OK)

    @override_settings(**TURNSTILE, CAPTCHA_ON_LOGIN=True)
    def test_on_login_rejected_by_siteverify(self):
        with _siteverify(False):
            _assert_captcha_failed(self, self._login(TEST_PASSWORD, captcha_token='tok'))

    @override_settings(**TURNSTILE)
    def test_login_captcha_after_3_failures(self):
        with mock.patch('httpx.post') as post:
            codes = [self._login('wrong', ip=f'10.1.1.{i}').status_code for i in range(3)]
            post.assert_not_called()
        self.assertEqual(codes, [401, 401, 401])
        resp = self._login(TEST_PASSWORD)
        _assert_captcha_failed(self, resp)
        self.assertIs(resp.json()['captcha_required'], True)
        with _siteverify(True):
            ok = self._login(TEST_PASSWORD, captcha_token='tok')
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    @override_settings(**TURNSTILE)
    def test_third_failure_response_announces_captcha_required(self):
        flags = [self._login('wrong', ip=f'10.1.1.{i}').json()['captcha_required'] for i in range(3)]
        self.assertEqual(flags, [False, False, True])

    @override_settings(**TURNSTILE)
    def test_failed_captcha_does_not_consume_attempt(self):
        for i in range(3):
            self._login('wrong', ip=f'10.1.1.{i}')
        for _ in range(3):
            _assert_captcha_failed(self, self._login('wrong'))
        with _siteverify(True):
            self.assertEqual(self._login('wrong', captcha_token='tok').status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(**TURNSTILE)
    def test_threshold_is_configurable(self):
        with override_settings(CAPTCHA_LOGIN_AFTER_FAILURES=1):
            self._login('wrong')
            _assert_captcha_failed(self, self._login(TEST_PASSWORD))

    def test_captcha_off_never_requires(self):
        for i in range(3):
            self._login('wrong', ip=f'10.1.1.{i}')
        self.assertEqual(self._login(TEST_PASSWORD).status_code, status.HTTP_200_OK)

    @override_settings(**TURNSTILE, LOGIN_MAX_FAILURES=3)
    def test_lockout_still_works_independently(self):
        for i in range(3):
            self._login('wrong', ip=f'10.1.1.{i}')
        with _siteverify(True):
            self._login('wrong', captcha_token='tok')
            resp = self._login(TEST_PASSWORD, captcha_token='tok')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


@override_settings(DEBUG=False, IS_TESTING=False)
class TestCaptchaSystemCheck(CleanCacheTestCase):

    def _ids(self, **settings_):
        from users.apps import check_captcha_provider
        with override_settings(**settings_):
            return [m.id for m in check_captcha_provider(None)]

    def test_turnstile_without_secret_warns(self):
        self.assertEqual(self._ids(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY=''), ['users.W002'])

    def test_cloudflare_test_secrets_are_error(self):
        for secret in ('1x0000000000000000000000000000000AA', '2x0000000000000000000000000000000AA',
                       '3x0000000000000000000000000000000AA'):
            self.assertEqual(self._ids(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY=secret), ['users.E002'])

    def test_real_secret_is_ok(self):
        self.assertEqual(self._ids(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='0x4AAAreal'), [])

    def test_off_is_error(self):
        self.assertEqual(self._ids(CAPTCHA_PROVIDER='off', TURNSTILE_SECRET_KEY=''), ['users.E001'])

    def test_debug_skips_checks(self):
        self.assertEqual(self._ids(DEBUG=True, CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='1x0000000000000000000000000000000AA'), [])
