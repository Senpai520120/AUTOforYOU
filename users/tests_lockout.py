"""Защита входа от перебора (задача 1.5): блокировка по аккаунту, scoped throttle, XFF."""
import hashlib
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from tests.base import CleanCacheTestCase
from tests.factories import TEST_PASSWORD, make_staff, make_user

TOKEN_URL = '/api/v1/auth/token/'
REGISTER_URL = '/api/v1/auth/register/'
REFRESH_URL = '/api/v1/auth/token/refresh/'


def _login(client, email, password, ip='10.0.0.1', **extra):
    return client.post(
        TOKEN_URL, {'email': email, 'password': password}, format='json',
        REMOTE_ADDR=ip, **extra,
    )


def _rates(**rates):
    # DRF читает THROTTLE_RATES при импорте класса, override_settings его не меняет.
    return mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, rates)


@override_settings(LOGIN_MAX_FAILURES=3)
class TestAccountLockout(CleanCacheTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user('lock@test.com')

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _fail(self, email='lock@test.com', n=3):
        # Разные IP: счётчик общий для всех адресов (иначе упрёмся в throttle по IP).
        return [_login(self.client, email, 'wrong', ip=f'10.0.0.{i + 1}') for i in range(n)]

    def test_lockout_after_n_failures(self):
        codes = [r.status_code for r in self._fail()]
        self.assertEqual(codes, [401, 401, 401])
        resp = _login(self.client, 'lock@test.com', TEST_PASSWORD, ip='10.0.0.9')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreater(int(resp['Retry-After']), 0)
        self.assertEqual(resp.json()['retry_after'], int(resp['Retry-After']))

    def test_lockout_email_is_normalized(self):
        self._fail()
        resp = _login(self.client, '  LOCK@test.com ', TEST_PASSWORD, ip='10.0.0.9')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_lockout_expires(self):
        self._fail()
        self.assertEqual(_login(self.client, 'lock@test.com', TEST_PASSWORD, ip='10.0.0.8').status_code, 429)
        with mock.patch('users.lockout.time.time', return_value=10 ** 10):
            resp = _login(self.client, 'lock@test.com', TEST_PASSWORD, ip='10.0.0.9')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_success_resets_counter(self):
        self._fail(n=2)
        self.assertEqual(_login(self.client, 'lock@test.com', TEST_PASSWORD).status_code, 200)
        codes = [r.status_code for r in self._fail(n=2)]
        self.assertEqual(codes, [401, 401])
        self.assertEqual(_login(self.client, 'lock@test.com', TEST_PASSWORD).status_code, 200)

    def test_lockout_same_for_unknown_email(self):
        known = self._fail('lock@test.com')
        unknown = self._fail('nobody@test.com')
        self.assertEqual([r.status_code for r in unknown], [401, 401, 401])
        self.assertEqual([r.json() for r in unknown], [r.json() for r in known])
        r_known = _login(self.client, 'lock@test.com', TEST_PASSWORD, ip='10.0.0.9')
        r_unknown = _login(self.client, 'nobody@test.com', TEST_PASSWORD, ip='10.0.0.9')
        self.assertEqual(r_unknown.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(r_unknown.json()['detail'], r_known.json()['detail'])

    def test_lockout_log_has_no_email(self):
        with self.assertLogs('users.lockout', level='WARNING') as logs:
            self._fail(n=4)
        output = '\n'.join(logs.output)
        self.assertNotIn('lock@test.com', output)
        self.assertIn('ip=10.0.0.4', output)

    def test_unicode_variant_shares_counter(self):
        self._fail(n=2)
        _login(self.client, 'ｌock@test.com', 'wrong', ip='10.0.0.7')  # полноширинная «l»
        resp = _login(self.client, 'lock@test.com', TEST_PASSWORD, ip='10.0.0.9')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_other_account_is_not_locked(self):
        make_user('other@test.com')
        self._fail()
        self.assertEqual(_login(self.client, 'other@test.com', TEST_PASSWORD).status_code, 200)

    @override_settings(CAPTCHA_LOGIN_AFTER_FAILURES=2)
    def test_captcha_required_flag_after_threshold(self):
        first, second = self._fail(n=2)
        self.assertFalse(first.json()['captcha_required'])
        self.assertTrue(second.json()['captcha_required'])
        unknown = self._fail('nobody@test.com', n=2)
        self.assertEqual([r.json()['captcha_required'] for r in unknown], [False, True])

    def test_missing_email_does_not_count(self):
        resp = self.client.post(TOKEN_URL, {'password': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNone(cache.get('login-fail:' + hashlib.sha256(b'').hexdigest()))


class TestScopedThrottle(CleanCacheTestCase):

    def test_login_scope_throttle(self):
        client = APIClient()
        with _rates(login='2/min'):
            codes = [_login(client, 'x@test.com', 'wrong').status_code for _ in range(3)]
        self.assertEqual(codes, [401, 401, 429])

    def test_register_scope_throttle(self):
        client = APIClient()
        with _rates(register='2/min'):
            codes = [
                client.post(REGISTER_URL, {'email': f'n{i}@test.com'}, format='json').status_code
                for i in range(3)
            ]
        self.assertEqual(codes, [400, 400, 429])

    def test_refresh_scope_throttle(self):
        client = APIClient()
        with _rates(refresh='2/min'):
            codes = [
                client.post(REFRESH_URL, {'refresh': 'bad'}, format='json').status_code
                for _ in range(3)
            ]
        self.assertEqual(codes, [401, 401, 429])

    def test_xff_spoofing_does_not_bypass_throttle(self):
        # NUM_PROXIES из настроек не None: XFF не берётся целиком (иначе строку можно
        # менять в каждом запросе). 0 — REMOTE_ADDR, 1 — последний элемент от nginx.
        self.assertIsNotNone(settings.REST_FRAMEWORK['NUM_PROXIES'])
        client = APIClient()
        with _rates(login='2/min'):
            codes = [
                _login(client, 'x@test.com', 'wrong', ip='9.9.9.9',
                       HTTP_X_FORWARDED_FOR=f'1.1.1.{n}, 10.0.0.1').status_code
                for n in range(3)
            ]
        self.assertEqual(codes, [401, 401, 429])

    def test_xff_last_element_used_with_one_proxy(self):
        client = APIClient()
        rest = {**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}
        with override_settings(REST_FRAMEWORK=rest), _rates(login='2/min'):
            same_last = [
                _login(client, 'x@test.com', 'wrong', ip='9.9.9.9',
                       HTTP_X_FORWARDED_FOR=f'1.1.1.{n}, 10.0.0.1').status_code
                for n in range(3)
            ]
            other_last = _login(client, 'x@test.com', 'wrong', ip='9.9.9.9',
                                HTTP_X_FORWARDED_FOR='1.1.1.1, 10.0.0.2').status_code
        self.assertEqual(same_last, [401, 401, 429])
        self.assertEqual(other_last, 401)


@override_settings(LOGIN_MAX_FAILURES=2)
class TestAdminLoginLockout(CleanCacheTestCase):

    def _post(self, password):
        return self.client.post(
            '/admin/login/', {'username': 'adm@test.com', 'password': password, 'next': '/admin/'},
        )

    def test_admin_login_lockout(self):
        make_staff('adm@test.com')
        for _ in range(2):
            self.assertEqual(self._post('bad').status_code, status.HTTP_200_OK)
        resp = self._post(TEST_PASSWORD)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, 'Забагато спроб входу')

    def test_admin_login_ok_without_failures(self):
        make_staff('adm@test.com')
        self.assertEqual(self._post(TEST_PASSWORD).status_code, status.HTTP_302_FOUND)


class TestLockoutCacheCheck(CleanCacheTestCase):

    @override_settings(DEBUG=False)
    def test_warns_on_locmem_cache_in_production(self):
        from users.apps import check_lockout_cache
        self.assertEqual([w.id for w in check_lockout_cache(None)], ['users.W001'])

    @override_settings(DEBUG=True)
    def test_no_warning_in_debug(self):
        from users.apps import check_lockout_cache
        self.assertEqual(check_lockout_cache(None), [])
