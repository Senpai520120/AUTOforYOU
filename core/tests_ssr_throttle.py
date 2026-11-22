"""12.4: SSR Next не должен делить один anon-лимит между всеми посетителями."""
from unittest import mock

from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from tests.base import CleanCacheTestCase

URL = '/api/v1/local/regions/'  # публичный GET с дефолтными троттлами (DEFAULT_THROTTLE_CLASSES)
FRONT_IP = '172.18.0.5'  # IP контейнера фронта: REMOTE_ADDR у всех SSR-запросов
NGINX_IP = '172.18.0.2'  # IP контейнера nginx: REMOTE_ADDR у запросов браузеров
LIMIT = 3


def _rest(**extra):
    from django.conf import settings
    return {**settings.REST_FRAMEWORK, 'NUM_PROXIES': 1, **extra}


class SsrSharedBucketProofTests(CleanCacheTestCase):
    """Шаг 1 (доказательство проблемы). После исправления остаётся регрессией для НЕДОВЕРЕННОГО пути:
    запрос без ключа и без XFF (как «голый» SSR) по-прежнему делит бакет `anon` по REMOTE_ADDR."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'anon': f'{LIMIT}/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)
        override = override_settings(REST_FRAMEWORK=_rest())
        override.enable()
        self.addCleanup(override.disable)

    def test_untrusted_no_xff_visitors_share_one_bucket(self):
        # Разные «посетители» неразличимы: один REMOTE_ADDR, XFF нет -> общий счётчик.
        for _ in range(LIMIT):
            self.assertEqual(APIClient().get(URL, REMOTE_ADDR=FRONT_IP).status_code, 200)
        self.assertEqual(APIClient().get(URL, REMOTE_ADDR=FRONT_IP).status_code, 429)

    def test_via_nginx_each_visitor_has_own_bucket(self):
        for n in range(LIMIT + 2):
            resp = APIClient().get(URL, REMOTE_ADDR=NGINX_IP, HTTP_X_FORWARDED_FOR=f'203.0.113.{n + 1}')
            self.assertEqual(resp.status_code, 200)


KEY = 'k' * 8 + 'ssr-internal-test-key-0123456789abcdef'  # 46 символов, >= 32


def _get(*, key=None, client_ip=None, xff=None, remote=FRONT_IP, url=URL):
    extra = {'REMOTE_ADDR': remote}
    if key is not None:
        extra['HTTP_X_SSR_KEY'] = key
    if client_ip is not None:
        extra['HTTP_X_SSR_CLIENT_IP'] = client_ip
    if xff is not None:
        extra['HTTP_X_FORWARDED_FOR'] = xff
    return APIClient().get(url, **extra)


class SsrTrustTests(CleanCacheTestCase):
    """Доверенный SSR: ключ + нет XFF. IP посетителя из X-SSR-Client-IP, лимит scope `ssr`."""

    def setUp(self):
        super().setUp()
        # anon намеренно строже ssr: по успешным запросам видно, какой scope применён.
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'anon': '1/hour', 'ssr': f'{LIMIT}/hour', 'ssr_shared': f'{LIMIT + 2}/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)
        for ctx in (override_settings(REST_FRAMEWORK=_rest()), override_settings(SSR_INTERNAL_KEY=KEY)):
            ctx.enable()
            self.addCleanup(ctx.disable)

    def test_trusted_visitors_have_own_buckets(self):
        for n in range(LIMIT + 2):
            self.assertEqual(_get(key=KEY, client_ip=f'198.51.100.{n + 1}').status_code, 200)

    def test_trusted_visitor_hits_own_limit_only(self):
        for _ in range(LIMIT):
            self.assertEqual(_get(key=KEY, client_ip='198.51.100.1').status_code, 200)
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.1').status_code, 429)
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.2').status_code, 200)

    def test_forged_with_xff_is_untrusted_and_counted_as_anon_by_xff(self):
        # Верный ключ, но запрос прошёл через nginx (есть XFF): клиентский IP не применяется, лимит anon (1/hour).
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.1', xff='203.0.113.1').status_code, 200)
        # другой X-SSR-Client-IP не даёт новый бакет: счёт идёт по XFF
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.2', xff='203.0.113.1').status_code, 429)
        # другой XFF - другой посетитель
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.2', xff='203.0.113.2').status_code, 200)

    def test_c2c_catalog_with_explicit_throttle_classes_counts_in_ssr_scope(self):
        # LocalListingListCreateView задаёт throttle_classes явно (не из DEFAULT): тоже должен учитывать scope `ssr`.
        catalog = '/api/v1/local/listings/'
        for n in range(LIMIT + 1):  # anon = 1/hour: 200 у всех посетителей значит, что считался scope ssr
            self.assertEqual(_get(key=KEY, client_ip=f'198.51.100.{n + 1}', url=catalog).status_code, 200)
        for _ in range(LIMIT - 1):
            self.assertEqual(_get(key=KEY, client_ip='198.51.100.1', url=catalog).status_code, 200)
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.1', url=catalog).status_code, 429)

    def test_trusted_without_client_ip_uses_shared_scope(self):
        # Кэшируемые запросы Next несут только ключ: общий бакет ssr_shared (LIMIT+2), не anon (1) и не ssr (LIMIT).
        for _ in range(LIMIT + 2):
            self.assertEqual(_get(key=KEY).status_code, 200)
        self.assertEqual(_get(key=KEY).status_code, 429)
        # посетители с IP не затронуты общим бакетом
        self.assertEqual(_get(key=KEY, client_ip='198.51.100.1').status_code, 200)

    def test_invalid_client_ip_falls_to_shared_scope(self):
        for _ in range(LIMIT + 2):
            self.assertEqual(_get(key=KEY, client_ip='not-an-ip').status_code, 200)
        self.assertEqual(_get(key=KEY, client_ip='not-an-ip').status_code, 429)

    def test_ipv6_visitors_in_same_64_share_bucket(self):
        for n in range(LIMIT):
            self.assertEqual(_get(key=KEY, client_ip=f'2001:db8:1:2::{n + 1}').status_code, 200)
        self.assertEqual(_get(key=KEY, client_ip='2001:db8:1:2:ffff::9').status_code, 429)
        self.assertEqual(_get(key=KEY, client_ip='2001:db8:1:3::1').status_code, 200)

    def test_normalize_visitor_ip(self):
        from core.ssr import normalize_visitor_ip

        self.assertEqual(normalize_visitor_ip('::ffff:203.0.113.7'), '203.0.113.7')
        self.assertEqual(normalize_visitor_ip('203.0.113.7'), '203.0.113.7')
        self.assertEqual(normalize_visitor_ip('2001:db8:1:2:aaaa:bbbb:cccc:dddd'), '2001:db8:1:2::')
        for bad in ('fe80::1%eth0', '2001:db8::1%1', 'x', ''):
            with self.assertRaises(ValueError, msg=bad):
                normalize_visitor_ip(bad)

    def _assert_untrusted(self, key):
        """Недоверенный: X-SSR-Client-IP игнорируется, все делят бакет anon (1/hour) по REMOTE_ADDR."""
        self.assertEqual(_get(key=key, client_ip='198.51.100.1').status_code, 200)
        self.assertEqual(_get(key=key, client_ip='198.51.100.2').status_code, 429)

    def test_wrong_key_is_untrusted(self):
        self._assert_untrusted('x' * 46)

    def test_missing_key_is_untrusted(self):
        self._assert_untrusted(None)

    def test_empty_setting_disables_feature(self):
        with override_settings(SSR_INTERNAL_KEY=''):
            self._assert_untrusted('')

    def test_short_key_disables_feature(self):
        short = 'a' * 31
        with override_settings(SSR_INTERNAL_KEY=short):
            self._assert_untrusted(short)

    def test_invalid_client_ip_keeps_remote_addr(self):
        from django.test import RequestFactory

        from core.ssr import SsrTrustMiddleware

        seen = {}

        def view(request):
            seen['addr'], seen['trusted'] = request.META['REMOTE_ADDR'], request.ssr_trusted
            return None

        for bad in ('not-an-ip', '', '1.2.3', '203.0.113.1, 10.0.0.1'):
            request = RequestFactory().get('/', REMOTE_ADDR=FRONT_IP, HTTP_X_SSR_KEY=KEY, HTTP_X_SSR_CLIENT_IP=bad)
            SsrTrustMiddleware(view)(request)
            self.assertEqual((seen['addr'], seen['trusted']), (FRONT_IP, True), bad)

    def test_valid_client_ip_replaces_remote_addr(self):
        from django.test import RequestFactory

        from core.ssr import SsrTrustMiddleware

        request = RequestFactory().get('/', REMOTE_ADDR=FRONT_IP, HTTP_X_SSR_KEY=KEY, HTTP_X_SSR_CLIENT_IP='2001:db8::1')
        SsrTrustMiddleware(lambda r: None)(request)
        self.assertEqual(request.META['REMOTE_ADDR'], '2001:db8::')  # IPv6 -> сеть /64
        self.assertTrue(request.ssr_visitor_ip)

    def test_ssr_headers_do_not_affect_untrusted_remote_addr(self):
        from django.test import RequestFactory

        from core.ssr import SsrTrustMiddleware

        request = RequestFactory().get('/', REMOTE_ADDR=NGINX_IP, HTTP_X_SSR_CLIENT_IP='198.51.100.1')
        SsrTrustMiddleware(lambda r: None)(request)
        self.assertEqual((request.META['REMOTE_ADDR'], request.ssr_trusted), (NGINX_IP, False))


class SsrKeyCheckTests(CleanCacheTestCase):
    """5: за прокси без валидного ключа - предупреждение core.W001."""

    def _ids(self, **conf):
        from core.ssr import check_ssr_key

        with override_settings(IS_TESTING=False, **conf):
            return [w.id for w in check_ssr_key(None)]

    def test_warns_behind_proxy_without_key(self):
        self.assertEqual(self._ids(NUM_PROXIES_COUNT=1, SSR_INTERNAL_KEY=''), ['core.W001'])
        self.assertEqual(self._ids(NUM_PROXIES_COUNT=1, SSR_INTERNAL_KEY='a' * 31), ['core.W001'])

    def test_silent_with_valid_key_without_proxies_or_in_tests(self):
        self.assertEqual(self._ids(NUM_PROXIES_COUNT=1, SSR_INTERNAL_KEY=KEY), [])
        self.assertEqual(self._ids(NUM_PROXIES_COUNT=0, SSR_INTERNAL_KEY=''), [])
        from core.ssr import check_ssr_key

        with override_settings(IS_TESTING=True, NUM_PROXIES_COUNT=1, SSR_INTERNAL_KEY=''):
            self.assertEqual(check_ssr_key(None), [])

    def test_check_is_registered(self):
        from django.core.checks import registry

        from core.ssr import check_ssr_key

        self.assertIn(check_ssr_key, registry.registry.registered_checks)
