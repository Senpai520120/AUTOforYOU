"""Заголовки безопасности и HTTPS-настройки (задача 7.1, 23-D103, 23-D104, 01-S18, 12-S2)."""
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import SimpleRateThrottle

from core.security_settings import build_security_settings, csrf_origins_from_site

CSRF_URL = '/api/v1/auth/csrf/'

SECURE_ON = dict(
    DEBUG=False, SECURE_HSTS_SECONDS=31_536_000, SECURE_CONTENT_TYPE_NOSNIFF=True,
    X_FRAME_OPTIONS='DENY', SECURE_SSL_REDIRECT=False,
)


class SecurityHeadersResponseTests(TestCase):
    @override_settings(**SECURE_ON)
    def test_https_response_has_security_headers(self):
        resp = self.client.get(CSRF_URL, secure=True)
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp['Strict-Transport-Security'], 'max-age=31536000')
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(resp['X-Frame-Options'], 'DENY')

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_forwarded_https_is_not_redirected(self):
        resp = self.client.get(CSRF_URL, HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(resp.status_code, 204)

    @override_settings(SECURE_SSL_REDIRECT=True, SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'))
    def test_plain_http_is_redirected_to_https(self):
        resp = self.client.get(CSRF_URL)
        self.assertEqual(resp.status_code, 301)
        self.assertTrue(resp['Location'].startswith('https://'))


class SsrRequestTests(TestCase):
    """SSR Next ходит в http://backend:8000 без X-Forwarded-Proto: 301 на https://backend быть не должно."""

    def test_letsencrypt_mode_ssr_request_is_not_redirected(self):
        prod = build_security_settings({'TLS_MODE': 'letsencrypt'})
        with override_settings(DEBUG=False, **prod):
            resp = self.client.get(CSRF_URL)  # http, без X-Forwarded-Proto
        self.assertEqual(resp.status_code, 204)

    def test_legacy_empty_mode_still_redirects(self):
        # TLS_MODE не задан в старом прод-.env: прежнее поведение (редирект и HSTS) сохраняется.
        prod = build_security_settings({})
        with override_settings(DEBUG=False, **prod):
            resp = self.client.get(CSRF_URL)
        self.assertEqual(resp.status_code, 301)


class BuildSecuritySettingsTests(SimpleTestCase):
    def test_dev_and_tests_return_nothing(self):
        self.assertEqual(build_security_settings({'TLS_MODE': 'letsencrypt'}, debug=True), {})
        self.assertEqual(build_security_settings({'TLS_MODE': 'letsencrypt'}, testing=True), {})

    def test_off_disables_redirect_and_hsts(self):
        cfg = build_security_settings({'TLS_MODE': 'off'})
        self.assertIs(cfg['SECURE_SSL_REDIRECT'], False)
        self.assertEqual(cfg['SECURE_HSTS_SECONDS'], 0)

    def test_letsencrypt_enables_hsts_but_not_django_redirect(self):
        # Редирект делает nginx; Django-редирект ломает SSR Next (http://backend:8000 без XFP).
        cfg = build_security_settings({'TLS_MODE': 'letsencrypt'})
        self.assertIs(cfg['SECURE_SSL_REDIRECT'], False)
        self.assertEqual(cfg['SECURE_HSTS_SECONDS'], 31_536_000)

    def test_selfsigned_and_external_do_not_redirect_in_django(self):
        for mode in ('selfsigned', 'external'):
            with self.subTest(mode=mode):
                self.assertIs(build_security_settings({'TLS_MODE': mode})['SECURE_SSL_REDIRECT'], False)

    def test_tls_mode_with_insecure_cookie_fails(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'AUTH_COOKIE_SECURE'):
            build_security_settings({'TLS_MODE': 'selfsigned'}, auth_cookie_secure=False)

    def test_off_mode_allows_insecure_cookie(self):
        cfg = build_security_settings({'TLS_MODE': 'off'}, auth_cookie_secure=False)
        self.assertIs(cfg['CSRF_COOKIE_SECURE'], False)

    def test_external_trusts_forwarded_proto_and_keeps_hsts(self):
        cfg = build_security_settings({'TLS_MODE': 'external', 'HSTS_MAX_AGE': '600'})
        self.assertEqual(cfg['SECURE_PROXY_SSL_HEADER'], ('HTTP_X_FORWARDED_PROTO', 'https'))
        self.assertEqual(cfg['SECURE_HSTS_SECONDS'], 600)

    def test_empty_mode_keeps_legacy_behaviour(self):
        cfg = build_security_settings({})
        self.assertIs(cfg['SECURE_SSL_REDIRECT'], True)
        self.assertEqual(cfg['SECURE_HSTS_SECONDS'], 31_536_000)

    def test_preload_and_subdomains_off_by_default(self):
        cfg = build_security_settings({'TLS_MODE': 'letsencrypt'})
        self.assertIs(cfg['SECURE_HSTS_PRELOAD'], False)
        self.assertIs(cfg['SECURE_HSTS_INCLUDE_SUBDOMAINS'], False)

    def test_preload_and_subdomains_by_flags(self):
        cfg = build_security_settings({'TLS_MODE': 'letsencrypt', 'HSTS_PRELOAD': 'true',
                                       'HSTS_INCLUDE_SUBDOMAINS': 'true'})
        self.assertIs(cfg['SECURE_HSTS_PRELOAD'], True)
        self.assertIs(cfg['SECURE_HSTS_INCLUDE_SUBDOMAINS'], True)

    def test_explicit_redirect_flag_overrides_mode(self):
        cfg = build_security_settings({'TLS_MODE': 'letsencrypt', 'SECURE_SSL_REDIRECT': 'true'})
        self.assertIs(cfg['SECURE_SSL_REDIRECT'], True)
        cfg = build_security_settings({'SECURE_SSL_REDIRECT': 'false'})
        self.assertIs(cfg['SECURE_SSL_REDIRECT'], False)
        self.assertEqual(cfg['SECURE_HSTS_SECONDS'], 0)

    def test_unknown_mode_fails(self):
        with self.assertRaisesMessage(ValueError, 'TLS_MODE'):
            build_security_settings({'TLS_MODE': 'https'})

    def test_bad_hsts_max_age_fails(self):
        with self.assertRaisesMessage(ValueError, 'HSTS_MAX_AGE'):
            build_security_settings({'TLS_MODE': 'letsencrypt', 'HSTS_MAX_AGE': 'год'})


class CsrfOriginsTests(SimpleTestCase):
    def test_from_domain_https(self):
        self.assertEqual(csrf_origins_from_site('example.com', '', 'letsencrypt'), ['https://example.com'])

    def test_from_domain_off_is_http(self):
        self.assertEqual(csrf_origins_from_site('example.com', '', 'off'), ['http://example.com'])

    def test_falls_back_to_site_url(self):
        self.assertEqual(csrf_origins_from_site('', 'https://shop.example.com', ''), ['https://shop.example.com'])

    def test_localhost_site_url_gives_nothing(self):
        self.assertEqual(csrf_origins_from_site('', 'http://localhost', ''), [])


class CheckDeployTests(SimpleTestCase):
    """manage.py check --deploy на прод-настройках не даёт предупреждений о HSTS/SSL/cookie."""

    def test_no_tls_warnings(self):
        prod = build_security_settings({'TLS_MODE': 'letsencrypt'})
        with override_settings(DEBUG=False, **prod):
            ids = {m.id for m in run_checks(tags=['security'], include_deployment_checks=True) if not m.is_silenced()}
        self.assertEqual(ids & {'security.W004', 'security.W008', 'security.W012', 'security.W016'}, set())

    def test_off_mode_reports_warnings(self):
        # Мутация-страховка: тест выше не пустой, проверка реально видит отсутствие HSTS/редиректа.
        with override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False, SECURE_HSTS_SECONDS=0):
            ids = {m.id for m in run_checks(tags=['security'], include_deployment_checks=True)}
        self.assertTrue({'security.W004', 'security.W008'} <= ids)


class _Throttle(SimpleRateThrottle):
    def get_rate(self):
        return '1/min'


class ClientIpRegressionTests(SimpleTestCase):
    """1.5: при NUM_PROXIES=1 два клиента за nginx - два разных счётчика (XFF = $remote_addr)."""

    def _ident(self, xff):
        rest = {'NUM_PROXIES': 1}
        request = Request(APIRequestFactory().get('/', HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR='172.18.0.5'))
        with override_settings(REST_FRAMEWORK={**rest}):
            from rest_framework.settings import api_settings
            api_settings.reload()
            try:
                return _Throttle().get_ident(request)
            finally:
                api_settings.reload()

    def test_two_clients_two_idents(self):
        self.assertNotEqual(self._ident('203.0.113.7'), self._ident('203.0.113.8'))

    def test_spoofed_prefix_is_ignored(self):
        self.assertEqual(self._ident('1.1.1.1, 203.0.113.7'), self._ident('9.9.9.9, 203.0.113.7'))
