"""Флаги раздела C2C и платежей (задача 6.7): middleware, смешанные API, фон, site-settings.

Подача (CanPostLocalListing) - в local_listings/tests_posting.py, callback LiqPay - в payments/tests_flags.py.
"""
from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from core.c2c import c2c_enabled, c2c_public_posting_enabled, c2c_seeding_mode, payments_enabled
from core.middleware import (
    C2C_OPEN_PATHS,
    C2C_PREFIXES,
    C2C_SEEDING_CLOSED_PATTERNS,
    C2C_SEEDING_CLOSED_PREFIXES,
    MIXED_API_PREFIXES,
    c2c_closed_reason,
)
from core.tests_module_flags import _routes
from local_listings.models import LocalListing
from local_listings.tasks import expire_listings, warn_expiring_listings
from notifications.models import Notification
from saved_searches.models import SavedSearch
from saved_searches.tasks import check_saved_searches
from tests.factories import auth_client, make_listing, make_local_listing, make_staff, make_user, make_vehicle

OFF = dict(C2C_ENABLED=False, C2C_PUBLIC_POSTING_ENABLED=True, PAYMENTS_ENABLED=True)
SEEDING = dict(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=False)
OPEN_ALL = dict(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=True)

# Третий явный список: всё остальное под /api/. Новый маршрут вне трёх списков валит test_every_route_is_classified.
OPEN_API = (
    '/api/v1/auth/', '/api/v1/b2b/', '/api/v1/broker/', '/api/v1/content/', '/api/v1/dealers/', '/api/v1/leads/', '/api/v1/listings/',
    '/api/v1/lots/', '/api/v1/metrics/', '/api/v1/monitoring/', '/api/v1/notifications/', '/api/v1/pricing/',
    '/api/v1/shipments/', '/api/v1/site-settings/', '/api/v1/telegram/', '/api/v1/vehicles/',
    '/api/docs/', '/api/redoc/', '/api/schema/',
)
METHODS = ('get', 'post', 'put', 'patch', 'delete')


def _api_paths():
    return sorted({'/' + r for r in _routes() if r.startswith('api/')})


def _c2c_paths():
    return [p for p in _api_paths() if any(p.startswith(pre) for pre in C2C_PREFIXES)]


def _seeding_closed_paths():
    return [p for p in _c2c_paths() if c2c_closed_reason_with(p, SEEDING) == 'seeding']


def c2c_closed_reason_with(path, flags):
    with override_settings(**flags):
        return c2c_closed_reason(path)


class TestFlagReaders(SimpleTestCase):
    @override_settings(C2C_ENABLED=False, C2C_PUBLIC_POSTING_ENABLED=True)
    def test_posting_flag_has_no_effect_when_section_off(self):
        self.assertFalse(c2c_public_posting_enabled())

    @override_settings(**SEEDING)
    def test_seeding_mode(self):
        self.assertTrue(c2c_enabled())
        self.assertTrue(c2c_seeding_mode())

    @override_settings(PAYMENTS_ENABLED=False, **OPEN_ALL)
    def test_payments_flag_is_independent_of_c2c(self):
        self.assertFalse(payments_enabled())

    def test_settings_defaults_are_false_and_parse_true_1_yes(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parent / 'settings.py').read_text(encoding='utf-8')
        for name in ('C2C_ENABLED', 'C2C_PUBLIC_POSTING_ENABLED', 'PAYMENTS_ENABLED'):
            with self.subTest(name=name):
                self.assertRegex(
                    src, rf"{name} = os\.environ\.get\('{name}', 'false'\)\.strip\(\)\.lower\(\) in \('true', '1', 'yes'\)")

    def test_no_direct_reads_of_flag_settings_outside_core_c2c(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        offenders = []
        skip_dirs = {'frontend', 'node_modules', 'docs', 'scripts', 'tests', 'staticfiles', 'media', 'cars'}
        for app in root.iterdir():
            if not app.is_dir() or app.name.startswith('.') or app.name in skip_dirs:
                continue
            for path in app.rglob('*.py'):
                rel = path.relative_to(root).as_posix()
                if 'test' in path.name or '/migrations/' in rel or rel in ('core/c2c.py', 'core/settings.py'):
                    continue
                text = path.read_text(encoding='utf-8')
                for name in ('C2C_ENABLED', 'C2C_PUBLIC_POSTING_ENABLED', 'PAYMENTS_ENABLED'):
                    if f'settings.{name}' in text or f"'{name}'" in text:
                        offenders.append(f'{rel}: {name}')
        self.assertEqual(offenders, [])


class TestRouteClassification(TestCase):
    def test_every_route_is_classified(self):
        # Каждый /api/ маршрут обязан быть в одном из трёх списков: C2C_PREFIXES, MIXED_API_PREFIXES, OPEN_API.
        unclassified = [
            p for p in _api_paths()
            if not any(p.startswith(pre) for pre in (*C2C_PREFIXES, *MIXED_API_PREFIXES, *OPEN_API))
        ]
        self.assertEqual(unclassified, [])

    def test_lists_do_not_overlap(self):
        for p in _api_paths():
            groups = [
                any(p.startswith(x) for x in C2C_PREFIXES),
                any(p.startswith(x) for x in MIXED_API_PREFIXES),
                any(p.startswith(x) for x in OPEN_API),
            ]
            with self.subTest(path=p):
                self.assertEqual(sum(groups), 1)

    def test_every_listed_prefix_matches_a_route(self):
        paths = _api_paths()
        for prefix in (*C2C_PREFIXES, *MIXED_API_PREFIXES, *OPEN_API):
            with self.subTest(prefix=prefix):
                self.assertTrue(any(p.startswith(prefix) for p in paths))

    def test_open_paths_and_seeding_lists_are_inside_c2c_prefixes(self):
        paths = _api_paths()
        for open_path in C2C_OPEN_PATHS:
            with self.subTest(open_path=open_path):
                self.assertIn(open_path, paths)
                self.assertTrue(any(open_path.startswith(pre) for pre in C2C_PREFIXES))
        for pre in C2C_SEEDING_CLOSED_PREFIXES:
            self.assertIn(pre, C2C_PREFIXES)
        for pattern in C2C_SEEDING_CLOSED_PATTERNS:
            self.assertTrue(any(pattern.match(p) for p in paths))

    def test_c2c_route_count_matches_the_task(self):
        # 11 local + 6 deals + 4 messages + 2 saved-searches + 2 payments.
        self.assertEqual(len(_c2c_paths()), 25)


class TestClosedReasonUnit(SimpleTestCase):
    """Обход резолвера: регистр, двойные слэши, путь без слэша не должны проскакивать мимо префикса."""

    @override_settings(**OFF)
    def test_bypass_variants_are_closed_when_section_off(self):
        for path in ('/api/v1/local/listings/', '/API/v1/Local/listings/', '/api/v1//local//listings/',
                     '/api/v1/local', '/api/v1/messages', '//api/v1/deals/1/', '/api/v1/payments/liqpay/checkout/'):
            with self.subTest(path=path):
                self.assertEqual(c2c_closed_reason(path), 'section')

    @override_settings(**OFF)
    def test_callback_and_other_apis_are_not_closed(self):
        for path in ('/api/v1/payments/liqpay/callback/', '/api/v1/pricing/rates/', '/api/v1/favorites/',
                     '/api/v1/reports/', '/admin/local_listings/locallisting/', '/api/v1/local-x/'):
            with self.subTest(path=path):
                self.assertIsNone(c2c_closed_reason(path))

    @override_settings(**SEEDING)
    def test_seeding_closes_exactly_the_listed_prefixes_and_promote(self):
        for path in ('/api/v1/messages/start/', '/api/v1/deals/', '/api/v1/saved-searches/',
                     '/api/v1/local/listings/5/promote/'):
            with self.subTest(path=path):
                self.assertEqual(c2c_closed_reason(path), 'seeding')
        for path in ('/api/v1/local/listings/', '/api/v1/local/listings/5/contact/', '/api/v1/payments/liqpay/checkout/',
                     '/api/v1/payments/liqpay/callback/'):
            with self.subTest(path=path):
                self.assertIsNone(c2c_closed_reason(path))

    @override_settings(**OPEN_ALL)
    def test_nothing_closed_when_everything_open(self):
        for path in _c2c_paths():
            with self.subTest(path=path):
                self.assertIsNone(c2c_closed_reason(path))


class _ClientsMixin:
    @classmethod
    def setUpTestData(cls):
        cls.users = {'anon': None, 'buyer': make_user(), 'staff': make_staff(superuser=True)}

    def client_for(self, who):
        user = self.users[who]
        return APIClient() if user is None else auth_client(user)


@override_settings(**OFF)
class TestSectionOff(_ClientsMixin, TestCase):
    def test_every_c2c_route_is_404_for_everyone_and_every_method(self):
        for path in _c2c_paths():
            if path in C2C_OPEN_PATHS:
                continue
            for who in self.users:
                client = self.client_for(who)
                for method in METHODS:
                    with self.subTest(path=path, who=who, method=method):
                        resp = getattr(client, method)(path)
                        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
                        self.assertEqual(resp.json(), {'detail': 'Not found.'})

    def test_callback_is_not_closed_by_the_section_flag(self):
        # Без ключа view отвечает 503 (а не 404 от middleware): callback принимается при любых флагах (Q17).
        resp = APIClient().post('/api/v1/payments/liqpay/callback/', {'data': 'x', 'signature': 'y'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_unaffected_apis_answer_as_before(self):
        self.assertEqual(APIClient().get('/api/v1/pricing/rates/').status_code, status.HTTP_200_OK)
        self.assertEqual(APIClient().get('/api/v1/listings/').status_code, status.HTTP_200_OK)
        self.assertEqual(APIClient().get('/api/v1/site-settings/').status_code, status.HTTP_200_OK)
        self.assertEqual(APIClient().get('/api/v1/shipments/').status_code, status.HTTP_401_UNAUTHORIZED)
        login = APIClient().post('/api/v1/auth/token/', {'email': 'nobody@test.com', 'password': 'x'}, format='json')
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_local_listings_available_to_staff(self):
        client = APIClient()
        client.force_login(self.users['staff'])
        self.assertEqual(client.get('/admin/local_listings/locallisting/').status_code, status.HTTP_200_OK)

    def test_messages_for_lot_dialogs_are_closed_too(self):
        lot = make_listing(make_vehicle(), make_user())
        resp = auth_client(self.users['buyer']).post(
            '/api/v1/messages/start/', {'listing_type': 'imported', 'listing_id': lot.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(**SEEDING)
class TestSeedingMode(_ClientsMixin, TestCase):
    def test_closed_features_are_404_for_everyone(self):
        paths = _seeding_closed_paths()
        self.assertEqual(len(paths), 13)  # 4 messages + 6 deals + 2 saved-searches + promote
        for path in paths:
            for who in self.users:
                client = self.client_for(who)
                for method in METHODS:
                    with self.subTest(path=path, who=who, method=method):
                        self.assertEqual(getattr(client, method)(path).status_code, status.HTTP_404_NOT_FOUND)

    def test_catalog_and_card_open_to_everyone(self):
        listing = make_local_listing(make_user())
        for who in self.users:
            client = self.client_for(who)
            for path in ('/api/v1/local/listings/', f'/api/v1/local/listings/{listing.pk}/', '/api/v1/local/regions/'):
                with self.subTest(who=who, path=path):
                    self.assertEqual(client.get(path).status_code, status.HTTP_200_OK)

    def test_phone_only_for_authenticated(self):
        listing = make_local_listing(make_user(), contact_phone='+380501112233')
        url = f'/api/v1/local/listings/{listing.pk}/contact/'
        self.assertEqual(APIClient().get(url).status_code, status.HTTP_401_UNAUTHORIZED)
        resp = auth_client(self.users['buyer']).get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json(), {'contact_phone': '+380501112233'})

    def test_favorite_and_report_on_local_are_404_lot_favorite_works(self):
        local = make_local_listing(make_user())
        lot = make_listing(make_vehicle(), make_user())
        for who in ('buyer', 'staff'):
            client = self.client_for(who)
            with self.subTest(who=who):
                body = {'listing_type': 'local', 'listing_id': local.pk}
                self.assertEqual(client.post('/api/v1/favorites/', body, format='json').status_code, 404)
                self.assertEqual(client.delete('/api/v1/favorites/', body, format='json').status_code, 404)
                status_url = f'/api/v1/favorites/status/?listing_type=local&listing_id={local.pk}'
                self.assertEqual(client.get(status_url).status_code, 404)
                report = {'listing': local.pk, 'reason': 'spam', 'comment': 'x'}
                self.assertEqual(client.post('/api/v1/reports/', report, format='json').status_code, 404)
        lot_body = {'listing_type': 'imported', 'listing_id': lot.pk}
        resp = self.client_for('buyer').post('/api/v1/favorites/', lot_body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_favorites_list_hides_local_records(self):
        from favorites.models import Favorite
        buyer = self.users['buyer']
        local = make_local_listing(make_user())
        lot = make_listing(make_vehicle(), make_user())
        Favorite.objects.create(user=buyer, local_listing=local)
        Favorite.objects.create(user=buyer, imported_listing=lot)
        resp = auth_client(buyer).get('/api/v1/favorites/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual([f['listing_type'] for f in resp.json()], ['imported'])

    def test_report_on_user_is_not_closed(self):
        resp = auth_client(self.users['buyer']).post(
            '/api/v1/reports/', {'reported_user': make_user().pk, 'reason': 'spam', 'comment': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


@override_settings(**OPEN_ALL)
class TestAllOpen(_ClientsMixin, TestCase):
    """Оба флага true: поведение как раньше (не 404 от middleware)."""

    def test_c2c_routes_answer_by_view_logic(self):
        for path, method, expected in (
            ('/api/v1/local/listings/', 'get', status.HTTP_200_OK),
            ('/api/v1/messages/conversations/', 'get', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/messages/unread-count/', 'get', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/deals/', 'get', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/saved-searches/', 'get', status.HTTP_401_UNAUTHORIZED),
            ('/api/v1/payments/liqpay/checkout/', 'post', status.HTTP_401_UNAUTHORIZED),
        ):
            with self.subTest(path=path):
                self.assertEqual(getattr(APIClient(), method)(path).status_code, expected)

    def test_favorite_and_report_on_local_work(self):
        local = make_local_listing(make_user())
        client = auth_client(self.users['buyer'])
        resp = client.post('/api/v1/favorites/', {'listing_type': 'local', 'listing_id': local.pk}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = client.post('/api/v1/reports/', {'listing': local.pk, 'reason': 'spam', 'comment': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class TestSiteSettingsFlags(TestCase):
    URL = '/api/v1/site-settings/'

    def test_all_three_flags_present_as_booleans(self):
        data = APIClient().get(self.URL).json()
        for name in ('c2c_enabled', 'c2c_public_posting_enabled', 'payments_enabled'):
            with self.subTest(name=name):
                self.assertIs(data[name], True)  # тестовый блок settings: всё включено

    def test_flags_follow_settings_not_cache(self):
        APIClient().get(self.URL)  # прогрев кэша
        with override_settings(**SEEDING, PAYMENTS_ENABLED=False):
            data = APIClient().get(self.URL).json()
        self.assertIs(data['c2c_enabled'], True)
        self.assertIs(data['c2c_public_posting_enabled'], False)
        self.assertIs(data['payments_enabled'], False)
        with override_settings(**OFF):
            data = APIClient().get(self.URL).json()
        self.assertIs(data['c2c_enabled'], False)
        self.assertIs(data['c2c_public_posting_enabled'], False)  # при выключенном разделе подача не имеет эффекта

    def test_flags_are_not_taken_from_model(self):
        from site_settings.models import SiteSettings
        self.assertFalse(any(f.name.startswith(('c2c_', 'payments_')) for f in SiteSettings._meta.get_fields()))


class TestBackgroundTasks(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.notify = mock.patch('integrations.tasks.send_notification.delay')
        self.send = self.notify.start()
        self.addCleanup(self.notify.stop)

    def test_expire_listings_skipped_when_section_off(self):
        listing = make_local_listing(self.owner, expires_at=timezone.now() - timedelta(days=1))
        with override_settings(**OFF):
            self.assertEqual(expire_listings(), {'skipped': 'c2c_disabled'})
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.ACTIVE)
        self.send.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)

    def test_expire_listings_works_in_seeding_mode(self):
        listing = make_local_listing(self.owner, expires_at=timezone.now() - timedelta(days=1))
        with override_settings(**SEEDING):
            self.assertEqual(expire_listings(), 'expired=1')
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.EXPIRED)

    def test_warn_expiring_skipped_when_section_off(self):
        listing = make_local_listing(self.owner, expires_at=timezone.now() + timedelta(days=2))
        with override_settings(**OFF):
            self.assertEqual(warn_expiring_listings(), {'skipped': 'c2c_disabled'})
        listing.refresh_from_db()
        self.assertFalse(listing.expiry_warned)
        self.send.assert_not_called()

    def test_warn_expiring_works_when_section_on(self):
        listing = make_local_listing(self.owner, expires_at=timezone.now() + timedelta(days=2))
        with override_settings(**SEEDING):
            self.assertEqual(warn_expiring_listings(), 'warned=1')
        listing.refresh_from_db()
        self.assertTrue(listing.expiry_warned)

    def _saved_search_with_match(self):
        ss = SavedSearch.objects.create(user=self.owner, name='Camry', filters={'make': 'Toyota'})
        make_local_listing(make_user())
        return ss

    def test_saved_searches_skipped_when_section_off_and_in_seeding(self):
        ss = self._saved_search_with_match()
        for flags in (OFF, SEEDING):
            with self.subTest(flags=flags), override_settings(**flags):
                self.assertEqual(check_saved_searches(), {'skipped': 'c2c_disabled'})
        ss.refresh_from_db()
        self.assertIsNone(ss.last_notified_at)
        self.assertEqual(Notification.objects.count(), 0)
        self.send.assert_not_called()

    def test_saved_searches_work_when_everything_open(self):
        ss = self._saved_search_with_match()
        with override_settings(**OPEN_ALL):
            self.assertEqual(check_saved_searches(), {'processed': 1})
        ss.refresh_from_db()
        self.assertIsNotNone(ss.last_notified_at)
        self.assertEqual(Notification.objects.count(), 1)

    def test_lot_channel_post_not_affected_by_c2c_flag(self):
        with override_settings(**OFF), mock.patch('telegram_bot.tasks.post_listing_to_channel.delay') as delay:
            listing = make_listing(make_vehicle(), make_user())
        delay.assert_called_once_with(listing.pk)
