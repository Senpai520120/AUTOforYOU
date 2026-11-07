"""Флаги заморозки модулей (задача 2.8): middleware, избранное, сигнал, CLI, site-settings, фронт."""
import re
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import status
from rest_framework.test import APIClient

from core.middleware import frozen_module_for
from core.modules import MODULE_FLAGS, module_enabled
from tests.factories import auth_client, make_listing, make_local_listing, make_staff, make_user, make_vehicle

ALL_OFF = dict(LOTS_ENABLED=False, B2B_ENABLED=False, DEALERS_ENABLED=False, SHIPMENTS_ENABLED=False)

# Маршруты /api/v1/vehicles/<vin>/..., не принадлежащие модулю лотов: NHTSA-декодер и отчёты по VIN.
VIN_ROUTE_MARKERS = ('/decode/', '/report/', '/registry/')

CONVERTER_SAMPLES = {'int': '1', 'str': 'X', 'slug': 'x', 'uuid': '00000000-0000-0000-0000-000000000001'}


def _routes(patterns=None, prefix=''):
    """Все маршруты urlconf как строки '/api/v1/...' с подставленными значениями конвертеров."""
    patterns = get_resolver().url_patterns if patterns is None else patterns
    for p in patterns:
        route = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _routes(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield re.sub(r'<(?:(\w+):)?\w+>', lambda m: CONVERTER_SAMPLES.get(m.group(1) or 'str', 'x'), route)


# Явный список из постановки 2.8: что должно замораживаться (значения конвертеров подставлены).
EXPECTED_FROZEN_PATHS = {
    '/api/v1/listings/', '/api/v1/listings/1/', '/api/v1/listings/create/',
    '/api/v1/lots/import/',
    '/api/v1/vehicles/', '/api/v1/vehicles/1/',
    '/api/v1/b2b/board/',
    '/api/v1/dealers/apply/', '/api/v1/dealers/application/',
    '/api/v1/shipments/', '/api/v1/shipments/1/', '/api/v1/shipments/1/events/1/photo/',
    '/api/v1/auth/me/shipments/',
}


def _frozen_paths():
    return sorted({'/' + r for r in _routes() if frozen_module_for('/' + r)})


class TestModuleHelper(TestCase):
    @override_settings(LOTS_ENABLED=False)
    def test_disabled_flag(self):
        self.assertFalse(module_enabled('lots'))

    @override_settings(LOTS_ENABLED=True)
    def test_enabled_flag(self):
        self.assertTrue(module_enabled('lots'))

    def test_unknown_module_raises(self):
        with self.assertRaises(KeyError):
            module_enabled('typo')

    def test_default_in_settings_is_false_without_env(self):
        # Тестовый блок включает модули, но боевой дефолт - false: читаем из исходника settings.
        src = (Path(__file__).resolve().parent / 'settings.py').read_text(encoding='utf-8')
        for name in (*MODULE_FLAGS.values(), 'LEGACY_CARS_API_ENABLED'):
            self.assertRegex(src, rf"{name} = os\.environ\.get\('{name}', 'false'\)")


@override_settings(**ALL_OFF)
class TestFrozenRoutes(TestCase):
    """Любой метод, любой пользователь (включая staff) - 404 от middleware."""

    @classmethod
    def setUpTestData(cls):
        cls.users = {'anon': None, 'buyer': make_user(), 'staff': make_staff(superuser=True)}

    def test_frozen_paths_match_expected_list(self):
        # Сверка с независимым списком: удалённая из FROZEN_ROUTES строка или новый маршрут без классификации краснят тест.
        self.assertEqual(set(_frozen_paths()), EXPECTED_FROZEN_PATHS)

    def test_every_frozen_route_is_404_for_everyone_and_every_method(self):
        for path in _frozen_paths():
            for who, user in self.users.items():
                client = APIClient() if user is None else auth_client(user)
                for method in ('get', 'post', 'put', 'patch', 'delete'):
                    with self.subTest(path=path, who=who, method=method):
                        self.assertEqual(getattr(client, method)(path).status_code, status.HTTP_404_NOT_FOUND)

    def test_no_unclassified_route_under_vehicles(self):
        # Новый маршрут под /api/v1/vehicles/ должен либо замораживаться, либо быть явно VIN-эндпоинтом.
        for r in _routes():
            path = '/' + r
            if path.startswith('/api/v1/vehicles/'):
                with self.subTest(path=path):
                    self.assertTrue(
                        frozen_module_for(path) == 'lots' or any(m in path for m in VIN_ROUTE_MARKERS),
                        f'{path}: не классифицирован',
                    )

    def test_vin_decode_not_frozen(self):
        # Короткий VIN: view отвечает 400 без сети, главное - не 404 от middleware.
        resp = APIClient().get('/api/v1/vehicles/SHORT/decode/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_and_other_apis_not_frozen(self):
        self.assertEqual(APIClient().get('/api/v1/pricing/rates/').status_code, status.HTTP_200_OK)
        self.assertEqual(APIClient().get('/admin/login/').status_code, status.HTTP_200_OK)

    def test_create_listing_404_even_for_admin(self):
        resp = auth_client(self.users['staff']).post('/api/v1/listings/create/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class TestEnabledRoutesPass(TestCase):
    """При включённых флагах (тестовый дефолт) маршруты отвечают логикой view, а не 404 middleware."""

    def test_flat_routes_are_not_404(self):
        for path, expected in (
            ('/api/v1/listings/', status.HTTP_200_OK),
            ('/api/v1/vehicles/', status.HTTP_200_OK),
            ('/api/v1/b2b/board/', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/dealers/application/', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/shipments/', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/auth/me/shipments/', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/lots/import/', status.HTTP_405_METHOD_NOT_ALLOWED),
        ):
            with self.subTest(path=path):
                method = APIClient().get
                if path.endswith('/import/'):
                    # POST без прав: 401; GET - 405 только после прав, поэтому проверяем POST.
                    expected = status.HTTP_401_UNAUTHORIZED
                    method = APIClient().post
                self.assertEqual(method(path).status_code, expected)

    @override_settings(LOTS_ENABLED=False)
    def test_one_flag_does_not_freeze_other_modules(self):
        self.assertEqual(APIClient().get('/api/v1/b2b/board/').status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(APIClient().get('/api/v1/shipments/').status_code, status.HTTP_401_UNAUTHORIZED)


class TestFavoritesByFlag(TestCase):
    URL = '/api/v1/favorites/'

    def setUp(self):
        self.user = make_user()
        self.client = auth_client(self.user)
        self.local = make_local_listing(make_user())
        self.lot = make_listing(make_vehicle(), make_user())

    @override_settings(LOTS_ENABLED=False)
    def test_add_lot_is_404_when_lots_disabled(self):
        resp = self.client.post(self.URL, {'listing_type': 'imported', 'listing_id': self.lot.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(LOTS_ENABLED=False)
    def test_delete_and_status_of_lot_are_404_when_lots_disabled(self):
        resp = self.client.delete(self.URL, {'listing_type': 'imported', 'listing_id': self.lot.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        resp = self.client.get(self.URL + 'status/', {'listing_type': 'imported', 'listing_id': self.lot.pk})
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(LOTS_ENABLED=False)
    def test_local_favorite_works_when_lots_disabled(self):
        resp = self.client.post(self.URL, {'listing_type': 'local', 'listing_id': self.local.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_add_lot_works_when_lots_enabled(self):
        resp = self.client.post(self.URL, {'listing_type': 'imported', 'listing_id': self.lot.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_existing_lot_favorites_hidden_from_list_when_lots_disabled(self):
        self.client.post(self.URL, {'listing_type': 'imported', 'listing_id': self.lot.pk}, format='json')
        self.client.post(self.URL, {'listing_type': 'local', 'listing_id': self.local.pk}, format='json')
        with override_settings(LOTS_ENABLED=False):
            resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([f['listing_type'] for f in resp.json()], ['local'])


class TestTelegramSignalByFlag(TestCase):
    TASK = 'telegram_bot.tasks.post_listing_to_channel.delay'

    def test_listing_not_queued_when_lots_disabled(self):
        with override_settings(LOTS_ENABLED=False), mock.patch(self.TASK) as delay:
            make_listing(make_vehicle(), make_user())
        delay.assert_not_called()

    def test_listing_queued_when_lots_enabled(self):
        with mock.patch(self.TASK) as delay:
            listing = make_listing(make_vehicle(), make_user())
        delay.assert_called_once_with(listing.pk)


class TestImportCommandsByFlag(TestCase):
    @override_settings(LOTS_ENABLED=False)
    def test_import_lot_refuses_when_lots_disabled(self):
        with self.assertRaisesMessage(CommandError, 'LOTS_ENABLED=false'):
            call_command('import_lot', json_str='{}', stdout=StringIO())

    @override_settings(LOTS_ENABLED=False)
    def test_upload_lot_photos_refuses_when_lots_disabled(self):
        with self.assertRaisesMessage(CommandError, 'LOTS_ENABLED=false'):
            call_command('upload_lot_photos', stdout=StringIO())


class TestSiteSettingsFlags(TestCase):
    URL = '/api/v1/site-settings/'

    def test_contains_four_flags_as_booleans(self):
        data = APIClient().get(self.URL).json()
        for name in ('lots_enabled', 'b2b_enabled', 'dealers_enabled', 'shipments_enabled'):
            with self.subTest(name=name):
                self.assertIs(data[name], True)

    def test_flags_follow_settings_not_cache(self):
        APIClient().get(self.URL)  # прогрев кэша при включённых флагах
        with override_settings(LOTS_ENABLED=False, B2B_ENABLED=False):
            data = APIClient().get(self.URL).json()
        self.assertIs(data['lots_enabled'], False)
        self.assertIs(data['b2b_enabled'], False)
        self.assertIs(data['dealers_enabled'], True)


FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'
LINK_FILES = (
    'components/layout/Header.tsx', 'app/page.tsx', 'app/error.tsx', 'app/not-found.tsx',
    'components/listings/ListingDetail.tsx', 'app/b2b/page.tsx', 'app/me/page.tsx', 'app/me/MeDashboard.tsx', 'app/dealers/apply/page.tsx',
)
FROZEN_HREFS = ('/listings', '/b2b', '/dealers/apply', '/me/shipments')


class TestFrontendHasNoFrozenLinks(TestCase):
    def test_no_legacy_cars_api_in_frontend(self):
        needles = (r'api/calculate', r'api/list', r'/cars')
        hits = []
        for ext in ('ts', 'tsx'):
            for path in FRONTEND.rglob(f'*.{ext}'):
                parts = path.relative_to(FRONTEND).parts
                if parts[0] in ('node_modules', '.next', 'e2e'):
                    continue
                text = path.read_text(encoding='utf-8')
                hits += [f'{path.name}: {n}' for n in needles if re.search(n, text)]
        self.assertEqual(hits, [])

    def test_no_href_to_frozen_modules_in_ui_files(self):
        pattern = re.compile(r"""href=(?:["']|\{\s*[`"'])(%s)""" % '|'.join(re.escape(h) for h in FROZEN_HREFS))
        for rel in LINK_FILES:
            with self.subTest(file=rel):
                text = (FRONTEND / rel).read_text(encoding='utf-8')
                self.assertEqual(pattern.findall(text), [])
