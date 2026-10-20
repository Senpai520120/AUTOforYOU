"""Задача 2.8: заморозка модулей флагами (404 по флагу), сигнал канала, CLI, избранное, site-settings, фронт."""
import re
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from core.middleware import FROZEN_API_PATHS, frozen_module_for
from tests.factories import make_admin_role, make_listing, make_local_listing, make_staff, make_user, make_vehicle

ALL_OFF = dict(LOTS_ENABLED=False, B2B_ENABLED=False, DEALERS_ENABLED=False, SHIPMENTS_ENABLED=False)

# Пример конкретного пути на каждый маршрут под замороженными префиксами (url_name -> (метод, путь)).
FROZEN_ROUTES = {
    'listing-list': ('get', '/api/v1/listings/'),
    'listing-detail': ('get', '/api/v1/listings/1/'),
    'listing-create': ('post', '/api/v1/listings/create/'),
    'lot-import': ('post', '/api/v1/lots/import/'),
    'vehicle-list': ('get', '/api/v1/vehicles/'),
    'vehicle-detail': ('get', '/api/v1/vehicles/1/'),
    'b2b-board': ('get', '/api/v1/b2b/board/'),
    'dealer-apply': ('post', '/api/v1/dealers/apply/'),
    'dealer-application': ('get', '/api/v1/dealers/application/'),
    'me-shipments': ('get', '/api/v1/auth/me/shipments/'),
}
SHIPMENTS_PREFIX = '/api/v1/shipments/'


def _routes(patterns, prefix=''):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _routes(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern), p.name


def _sample_path(route: str) -> str:
    return '/' + re.sub(r'<(?:\w+:)?\w+>', '1', route)


class FrozenRoutesClassifiedTests(TestCase):
    def test_every_route_under_frozen_prefix_is_classified(self):
        """Новый маршрут под замороженным префиксом валит тест, пока его не внесли в FROZEN_ROUTES."""
        unclassified = []
        for route, name in _routes(get_resolver().url_patterns):
            path = _sample_path(route)
            if frozen_module_for(path) and not path.startswith(SHIPMENTS_PREFIX) and name not in FROZEN_ROUTES:
                unclassified.append((name, route))
        self.assertEqual(unclassified, [])

    def test_vin_services_not_frozen(self):
        for path in ('/api/v1/vehicles/1HGCM82633A004352/decode/', '/api/v1/vehicles/1HGCM82633A004352/report/',
                     '/api/v1/vehicles/1HGCM82633A004352/registry/'):
            with self.subTest(path=path):
                self.assertIsNone(frozen_module_for(path))

    def test_every_pattern_used(self):
        modules = {m for m, _ in FROZEN_API_PATHS}
        self.assertEqual(modules, {'lots', 'b2b', 'dealers', 'shipments'})


@override_settings(**ALL_OFF)
class FlagsOffTests(TestCase):
    def call(self, user, method, path):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return getattr(client, method)(path, {}, format='json')

    def test_frozen_routes_404_for_everyone(self):
        from shipments.models import Shipment
        users = {'anon': None, 'buyer': make_user(), 'staff': make_staff(), 'admin': make_admin_role()}
        # Существующие объекты: 404 должен давать middleware, а не view «объект не найден».
        vehicle = make_vehicle()
        listing = make_listing(vehicle, make_user())
        shipment = Shipment.objects.create(container_no='MSCU7654321')
        routes = {**FROZEN_ROUTES, 'listing-detail': ('get', f'/api/v1/listings/{listing.pk}/'),
                  'vehicle-detail': ('get', f'/api/v1/vehicles/{vehicle.pk}/')}
        routes = [*routes.values(), ('get', SHIPMENTS_PREFIX), ('get', f'{SHIPMENTS_PREFIX}{shipment.pk}/')]
        for role, user in users.items():
            for method, path in routes:
                with self.subTest(role=role, path=path, method=method):
                    self.assertEqual(self.call(user, method, path).status_code, 404)

    def test_vin_decode_not_frozen(self):
        with patch('integrations.views.NHTSAVinDecodeProvider.decode', return_value={'make': 'HONDA'}) as decode:
            resp = self.call(None, 'get', '/api/v1/vehicles/1HGCM82633A004352/decode/')
        self.assertEqual(resp.status_code, 200)
        decode.assert_called_once()

    def test_messages_start_imported_rejected(self):
        client = APIClient()
        client.force_authenticate(make_user())
        lot = make_listing(make_vehicle(), make_user())
        resp = client.post('/api/v1/messages/start/', {'listing_type': 'imported', 'listing_id': lot.pk, 'text': 'Привіт'},
                           format='json')
        self.assertEqual(resp.status_code, 400)
        from messaging.models import Conversation
        self.assertFalse(Conversation.objects.exists())

    def test_lead_with_listing_rejected(self):
        from leads.tests_api import body, set_partner
        set_partner()
        lot = make_listing(make_vehicle(), make_user())
        resp = APIClient().post('/api/v1/leads/', body(source='listing', listing_id=lot.pk), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('listing_id', resp.json())

    def test_payment_with_listing_rejected(self):
        client = APIClient()
        client.force_authenticate(make_user())
        lot = make_listing(make_vehicle(), make_user())
        resp = client.post('/api/v1/payments/liqpay/checkout/', {'order_id': 'frozen-1', 'amount': '10.00',
                           'currency': 'USD', 'listing_id': lot.pk}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('listing_id', resp.json())

    def test_bot_latest_answers_unavailable(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from telegram_bot.handlers import cmd_latest
        make_listing(make_vehicle(), make_user())
        message = MagicMock()
        message.answer = AsyncMock()
        message.answer_photo = AsyncMock()
        asyncio.run(cmd_latest(message))
        message.answer.assert_called_once()
        self.assertIn('недоступний', message.answer.call_args.args[0])
        message.answer_photo.assert_not_called()

    def test_favorites_delete_lot_404(self):
        client = APIClient()
        client.force_authenticate(make_user())
        resp = client.delete('/api/v1/favorites/', {'listing_type': 'imported', 'listing_id': 1}, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_admin_site_not_affected(self):
        client = APIClient()
        client.force_login(make_staff(superuser=True))
        self.assertEqual(client.get('/admin/listings/listing/').status_code, 200)

    def test_site_settings_flags_false(self):
        body = APIClient().get('/api/v1/site-settings/').json()
        self.assertEqual({k: body[k] for k in ('lots_enabled', 'b2b_enabled', 'dealers_enabled', 'shipments_enabled')},
                         {'lots_enabled': False, 'b2b_enabled': False, 'dealers_enabled': False,
                          'shipments_enabled': False})

    def test_signal_does_not_post_to_channel(self):
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as delay:
            make_listing(make_vehicle(), make_user(), channel='retail')
        delay.assert_not_called()

    def test_import_lot_cli_refuses(self):
        with self.assertRaisesMessage(CommandError, 'LOTS_ENABLED=false'):
            call_command('import_lot', '--source', 'manual')

    def test_upload_lot_photos_cli_refuses(self):
        with self.assertRaisesMessage(CommandError, 'LOTS_ENABLED=false'):
            call_command('upload_lot_photos')

    def test_favorites_lot_404_local_ok(self):
        user = make_user()
        client = APIClient()
        client.force_authenticate(user)
        lot = make_listing(make_vehicle(), make_user())
        self.assertEqual(client.post('/api/v1/favorites/', {'listing_type': 'imported', 'listing_id': lot.pk},
                                     format='json').status_code, 404)
        self.assertEqual(client.get(f'/api/v1/favorites/status/?listing_type=imported&listing_id={lot.pk}').status_code,
                         404)
        local = make_local_listing(make_user())
        self.assertEqual(client.post('/api/v1/favorites/', {'listing_type': 'local', 'listing_id': local.pk},
                                     format='json').status_code, 201)

    def test_favorites_list_hides_lots(self):
        from favorites.models import Favorite
        user = make_user()
        Favorite.objects.create(user=user, imported_listing=make_listing(make_vehicle(), make_user()))
        Favorite.objects.create(user=user, local_listing=make_local_listing(make_user()))
        client = APIClient()
        client.force_authenticate(user)
        items = client.get('/api/v1/favorites/').json()
        self.assertEqual(len(items), 1)


@override_settings(B2B_ENABLED=False)
class B2BOffTests(TestCase):
    """LOTS включён, B2B выключен: wholesale не виден даже дилеру и не уходит в канал."""

    def setUp(self):
        from tests.factories import make_dealer
        self.dealer = make_dealer()
        self.wholesale = make_listing(make_vehicle(), make_user(), channel='wholesale')

    def dealer_client(self):
        client = APIClient()
        client.force_authenticate(self.dealer)
        return client

    def test_dealer_list_without_wholesale(self):
        ids = [item['id'] for item in self.dealer_client().get('/api/v1/listings/').json()['results']]
        self.assertNotIn(self.wholesale.pk, ids)

    def test_dealer_detail_wholesale_404(self):
        self.assertEqual(self.dealer_client().get(f'/api/v1/listings/{self.wholesale.pk}/').status_code, 404)

    def test_create_wholesale_400(self):
        client = APIClient()
        client.force_authenticate(make_admin_role())
        resp = client.post('/api/v1/listings/create/', {'vehicle': make_vehicle().pk, 'price': '1', 'currency': 'USD',
                                                        'channel': 'wholesale'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('channel', resp.json())

    def test_express_wholesale_not_posted(self):
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as delay, \
                self.captureOnCommitCallbacks(execute=True):
            make_listing(make_vehicle(), make_user(), channel='wholesale', is_express_buyout=True)
        delay.assert_not_called()


class FlagsOnTests(TestCase):
    """Флаги включены (тестовый блок настроек): маршруты отвечают логикой view, а не 404 middleware."""

    def test_listing_list_200(self):
        self.assertEqual(APIClient().get('/api/v1/listings/').status_code, 200)

    def test_vehicles_200(self):
        self.assertEqual(APIClient().get('/api/v1/vehicles/').status_code, 200)

    def test_b2b_anonymous_401(self):
        self.assertEqual(APIClient().get('/api/v1/b2b/board/').status_code, 401)

    def test_me_shipments_anonymous_401(self):
        self.assertEqual(APIClient().get('/api/v1/auth/me/shipments/').status_code, 401)

    def test_signal_posts_when_on(self):
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as delay, \
                self.captureOnCommitCallbacks(execute=True):
            make_listing(make_vehicle(), make_user(), channel='retail')
        delay.assert_called_once()


class FrontendLinksTests(TestCase):
    """В навигации нет замороженных модулей и legacy cars (grep по исходникам фронта)."""
    FRONT = Path(settings.BASE_DIR) / 'frontend'
    FILES = ('components/layout/Header.tsx', 'app/page.tsx', 'app/error.tsx', 'app/not-found.tsx',
             'components/listings/ListingDetail.tsx', 'app/b2b/page.tsx', 'app/me/page.tsx')

    def sources(self):
        for base in ('app', 'components', 'lib', 'api'):
            for path in (self.FRONT / base).rglob('*.ts*'):
                yield path, path.read_text(encoding='utf-8')

    def test_no_legacy_cars_api(self):
        hits = [str(p) for p, text in self.sources() if re.search(r"api/calculate|api/list\b|['\"/]cars\b", text)]
        self.assertEqual(hits, [])

    def test_no_links_to_frozen_pages(self):
        pattern = re.compile(r'href=\{?[`\'"](/listings|/b2b|/dealers/apply|/me/shipments)')
        hits = [f for f in self.FILES if pattern.search((self.FRONT / f).read_text(encoding='utf-8'))]
        self.assertEqual(hits, [])
