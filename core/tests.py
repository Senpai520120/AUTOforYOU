"""Тесты модели прав (задача 1.2): аудит views, дефолт IsAuthenticated, публичные эндпоинты."""
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, path
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from tests.base import CleanCacheTestCase

# Views, которым явные права не нужны: служебные OpenAPI-views задают
# SERVE_PERMISSIONS в самих классах drf_spectacular. Новые записи - только
# с обоснованием.
AUDIT_WHITELIST_MODULES = ('drf_spectacular.',)


def _iter_callbacks(patterns):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _iter_callbacks(p.url_patterns)
        elif isinstance(p, URLPattern):
            yield p.callback


def _declares_permissions(callback):
    cls = getattr(callback, 'cls', None)
    initkwargs = getattr(callback, 'initkwargs', {}) or {}
    if 'permission_classes' in initkwargs:
        return True
    for klass in cls.__mro__:
        if klass.__module__.startswith('rest_framework.'):
            break  # дошли до базовых классов DRF: дефолт из settings
        if 'permission_classes' in klass.__dict__ or 'get_permissions' in klass.__dict__:
            return True
    return False


class TestPermissionAudit(TestCase):
    def test_every_api_view_declares_permissions(self):
        missing = []
        for callback in _iter_callbacks(get_resolver().url_patterns):
            cls = getattr(callback, 'cls', None)
            if cls is None or not issubclass(cls, APIView):
                continue
            if cls.__module__.startswith(AUDIT_WHITELIST_MODULES):
                continue
            if not _declares_permissions(callback):
                missing.append(f'{cls.__module__}.{cls.__qualname__}')
        self.assertEqual(
            sorted(set(missing)), [],
            'У view нет явных permission_classes (иначе действует дефолт IsAuthenticated, '
            'а намерение не задокументировано). Укажите AllowAny/IsAuthenticated явно.',
        )


class _NoPermsView(APIView):
    def get(self, request):
        return Response({'ok': True})


urlpatterns = [path('no-perms/', _NoPermsView.as_view())]


@override_settings(ROOT_URLCONF='core.tests')
class TestDefaultPermission(TestCase):
    def test_default_permission_is_authenticated(self):
        resp = APIClient().get('/no-perms/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestPublicEndpointsStayPublic(CleanCacheTestCase):
    """Регрессия: после дефолта IsAuthenticated публичные эндпоинты по-прежнему доступны анониму."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_pricing_calculate(self):
        resp = self.client.post('/api/v1/pricing/calculate/', {
            'auction': 'copart', 'auction_price_usd': '5000', 'engine_cc': 2000,
            'fuel_type': 'petrol', 'vehicle_year': 2018, 'member_type': 'broker',
            'payment_type': 'secured', 'title_type': 'salvage',
            'us_port': 'houston', 'eu_port': 'klaipeda',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, getattr(resp, 'data', None))

    def test_pricing_rates(self):
        self.assertEqual(self.client.get('/api/v1/pricing/rates/').status_code, status.HTTP_200_OK)

    def test_listings(self):
        self.assertEqual(self.client.get('/api/v1/listings/').status_code, status.HTTP_200_OK)

    def test_local(self):
        self.assertEqual(self.client.get('/api/v1/local/listings/').status_code, status.HTTP_200_OK)

    def test_vehicles(self):
        self.assertEqual(self.client.get('/api/v1/vehicles/').status_code, status.HTTP_200_OK)



def _reload_urlconf():
    import importlib

    from django.urls import clear_url_caches

    import core.urls
    clear_url_caches()
    importlib.reload(core.urls)


class LegacyCarsFlagTests(TestCase):
    """Q7, 2.8 (23-D56): legacy cars/ API подключается только при LEGACY_CARS_API_ENABLED. Код cars/ не меняется."""

    def setUp(self):
        self.addCleanup(_reload_urlconf)  # вернуть urlconf с настройками по умолчанию

    def get(self, url, enabled):
        with override_settings(LEGACY_CARS_API_ENABLED=enabled):
            _reload_urlconf()
            return APIClient().get(url).status_code

    def test_calculate_off_404(self):
        self.assertEqual(self.get('/api/calculate/', False), status.HTTP_404_NOT_FOUND)

    def test_list_off_404(self):
        self.assertEqual(self.get('/api/list/', False), status.HTTP_404_NOT_FOUND)

    def test_calculate_on_200(self):
        self.assertEqual(self.get('/api/calculate/', True), status.HTTP_200_OK)

    def test_list_on_200(self):
        self.assertEqual(self.get('/api/list/', True), status.HTTP_200_OK)

    def test_not_in_openapi_when_off(self):
        with override_settings(LEGACY_CARS_API_ENABLED=False):
            _reload_urlconf()
            from drf_spectacular.generators import SchemaGenerator
            paths = SchemaGenerator().get_schema(request=None, public=True)['paths']
        self.assertNotIn('/api/calculate/', paths)
        self.assertNotIn('/api/list/', paths)
