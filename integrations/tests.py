"""
Тесты интеграции: Opendatabot (провайдер, кэш, эндпоинт) + импорт лотов аукционов.
"""
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import httpx
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image as PILImage
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from integrations.importer import import_lot
from integrations.models import RegistryReport
from integrations.providers import ApifyLotProvider, ManualLotProvider, RealOpendatabotProvider
from listings.models import Listing
from tests.factories import auth_client, make_admin_role, make_broker, make_moderator, make_staff, make_user
from tests.test_uploads import image_bytes, use_temp_media
from vehicles.models import Vehicle, VehicleImage

# ── Провайдер: без ключа → demo ───────────────────────────────────────────────

class TestOpendatabotProviderNoKey(SimpleTestCase):

    def test_no_key_returns_demo_true(self):
        provider = RealOpendatabotProvider(api_key='')
        result = provider.get_vehicle_info(vin='1HGBH41JXMN109186')
        self.assertTrue(result['demo'])
        self.assertEqual(result['provider'], 'opendatabot')

    def test_no_key_does_not_raise(self):
        provider = RealOpendatabotProvider(api_key='')
        try:
            provider.get_vehicle_info(vin='1HGBH41JXMN109186')
        except Exception as exc:
            self.fail(f'Provider без ключа бросил исключение: {exc}')

    def test_no_key_plate_also_returns_demo(self):
        provider = RealOpendatabotProvider(api_key='')
        result = provider.get_vehicle_info(plate='AA1234BB')
        self.assertTrue(result['demo'])


# ── Провайдер: с ключом → реальный запрос (замоканный) ───────────────────────

_MOCK_ODB_RESPONSE = {
    'code': 200,
    'data': {
        'vin': '1HGBH41JXMN109186',
        'number': 'AA1234BB',
        'brand': 'Honda',
        'model': 'Civic',
        'year': 2019,
        'color': 'Білий',
        'fuelName': 'Бензин',
        'engineVolume': 1500,
        'stolen': False,
        'restrictions': [],
        'owners': [{'name': 'Іванов І.І.', 'from': '2020-01-10'}],
        'odometer': {'value': 45000, 'unit': 'km'},
    },
}


class TestOpendatabotProviderWithKey(SimpleTestCase):

    def _mock_response(self, json_data, status_code=200):
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_data
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    @patch('httpx.get')
    def test_successful_vin_lookup_parses_fields(self, mock_get):
        mock_get.return_value = self._mock_response(_MOCK_ODB_RESPONSE)

        provider = RealOpendatabotProvider(api_key='test_key')
        result = provider.get_vehicle_info(vin='1HGBH41JXMN109186')

        self.assertFalse(result['demo'])
        self.assertEqual(result['provider'], 'opendatabot')
        self.assertEqual(result['vin'], '1HGBH41JXMN109186')
        self.assertEqual(result['brand'], 'Honda')
        self.assertEqual(result['year'], 2019)
        self.assertFalse(result['stolen'])
        self.assertEqual(len(result['owners']), 1)

    @patch('httpx.get')
    def test_successful_plate_lookup(self, mock_get):
        mock_get.return_value = self._mock_response(_MOCK_ODB_RESPONSE)

        provider = RealOpendatabotProvider(api_key='test_key')
        result = provider.get_vehicle_info(plate='AA1234BB')

        self.assertFalse(result['demo'])
        self.assertEqual(result['plate'], 'AA1234BB')

    @patch('httpx.get')
    def test_http_error_returns_error_dict_not_exception(self, mock_get):
        mock_get.side_effect = Exception('Connection timeout')

        provider = RealOpendatabotProvider(api_key='test_key')
        result = provider.get_vehicle_info(vin='1HGBH41JXMN109186')

        self.assertIn('error', result)

    @patch('httpx.get')
    def test_vin_uppercased_in_request(self, mock_get):
        mock_get.return_value = self._mock_response(_MOCK_ODB_RESPONSE)

        provider = RealOpendatabotProvider(api_key='test_key')
        provider.get_vehicle_info(vin='1hgbh41jxmn109186')

        called_url = mock_get.call_args[0][0]
        self.assertIn('1HGBH41JXMN109186', called_url)


# ── Эндпоинт: кэш ────────────────────────────────────────────────────────────

class TestRegistryReportEndpoint(APITestCase):

    VIN = '1HGBH41JXMN109186'
    URL = '/api/v1/vehicles/1HGBH41JXMN109186/registry/'

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        RegistryReport.objects.all().delete()
        self.client = auth_client(make_user('endpoint_test@test.com'))

    @patch('integrations.views.get_opendatabot_provider')
    def test_successful_response_has_required_fields(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.get_vehicle_info.return_value = {
            'demo': False,
            'provider': 'opendatabot',
            'vin': self.VIN,
            'brand': 'Honda',
            'stolen': False,
        }
        mock_factory.return_value = mock_provider

        resp = self.client.get(self.URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('provider', resp.data)
        self.assertFalse(resp.data['cached'])

    @patch('integrations.views.get_opendatabot_provider')
    def test_repeat_request_uses_cache_no_second_http_call(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.get_vehicle_info.return_value = {
            'demo': False, 'provider': 'opendatabot', 'vin': self.VIN, 'brand': 'Honda',
        }
        mock_factory.return_value = mock_provider

        self.client.get(self.URL)
        self.client.get(self.URL)

        # Провайдер вызван ровно один раз — второй запрос обслужен из кэша
        mock_provider.get_vehicle_info.assert_called_once()

    @patch('integrations.views.get_opendatabot_provider')
    def test_second_request_is_marked_cached(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.get_vehicle_info.return_value = {
            'demo': True, 'provider': 'opendatabot', 'vin': self.VIN,
        }
        mock_factory.return_value = mock_provider

        self.client.get(self.URL)
        resp2 = self.client.get(self.URL)

        self.assertTrue(resp2.data['cached'])

    @patch('integrations.views.get_opendatabot_provider')
    def test_no_key_demo_response_does_not_500(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.get_vehicle_info.return_value = {
            'demo': True, 'provider': 'opendatabot', 'vin': self.VIN,
            'note': '⚠ OPENDATABOT_API_KEY не задан — демо-режим.',
        }
        mock_factory.return_value = mock_provider

        resp = self.client.get(self.URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['demo'])

    def test_invalid_vin_length_returns_400(self):
        resp = self.client.get('/api/v1/vehicles/SHORT/registry/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_underscore_without_plate_returns_400(self):
        resp = self.client.get('/api/v1/vehicles/_/registry/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('integrations.views.get_opendatabot_provider')
    def test_plate_lookup_via_query_param(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.get_vehicle_info.return_value = {
            'demo': False, 'provider': 'opendatabot', 'plate': 'AA1234BB',
        }
        mock_factory.return_value = mock_provider

        resp = self.client.get('/api/v1/vehicles/_/registry/?plate=AA1234BB')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        _, kwargs = mock_provider.get_vehicle_info.call_args
        self.assertEqual(kwargs.get('plate'), 'AA1234BB')
        self.assertIsNone(kwargs.get('vin'))


# ── RegistryReport: сохранение в кэш ─────────────────────────────────────────

class TestRegistryReportCacheSave(TestCase):

    @patch('integrations.views.get_opendatabot_provider')
    def test_report_saved_to_db_on_first_request(self, mock_factory):
        mock_provider = MagicMock()
        mock_provider.get_vehicle_info.return_value = {
            'demo': True, 'provider': 'opendatabot', 'vin': '1HGBH41JXMN109186',
        }
        mock_factory.return_value = mock_provider

        client = auth_client(make_user())
        client.get('/api/v1/vehicles/1HGBH41JXMN109186/registry/')

        self.assertEqual(
            RegistryReport.objects.filter(vin='1HGBH41JXMN109186', provider='opendatabot').count(),
            1,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Импорт лотов аукционов
# ═══════════════════════════════════════════════════════════════════════════════

_VALID_LOT = {
    'vin': '1HGBH41JXMN109186',
    'auction': 'copart',
    'lot_number': '12345678',
    'make': 'Honda',
    'model': 'Civic',
    'year': 2019,
    'engine_cc': 1500,
    'fuel_type': 'petrol',
    'damage_type': 'Front End',
    'mileage_km': 65000,
    'final_bid': '8500.00',
    'photos': [
        'https://cs.copart.com/v1/photos/001.jpg',
        'https://cs.copart.com/v1/photos/002.jpg',
    ],
    'location': 'Dallas, TX',
}


# ── ManualLotProvider ─────────────────────────────────────────────────────────

class TestManualLotProvider(SimpleTestCase):

    def test_valid_lot_returns_normalized_dict(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot(_VALID_LOT)
        self.assertFalse(result.get('error'))
        self.assertEqual(result['vin'], '1HGBH41JXMN109186')
        self.assertEqual(result['auction'], 'copart')
        self.assertEqual(result['provider'], 'manual')
        self.assertIsInstance(result['final_bid'], Decimal)

    def test_missing_vin_returns_error(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot({'make': 'Honda'})
        self.assertIn('error', result)

    def test_short_vin_returns_error(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot({**_VALID_LOT, 'vin': 'SHORT'})
        self.assertIn('error', result)

    def test_non_dict_returns_error(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot('https://copart.com/lot/123')
        self.assertIn('error', result)

    def test_vin_uppercased(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot({**_VALID_LOT, 'vin': '1hgbh41jxmn109186'})
        self.assertEqual(result['vin'], '1HGBH41JXMN109186')

    def test_unknown_auction_defaults_to_other(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot({**_VALID_LOT, 'auction': 'carmax'})
        self.assertEqual(result['auction'], 'other')

    def test_photos_preserved(self):
        provider = ManualLotProvider()
        result = provider.fetch_lot(_VALID_LOT)
        self.assertEqual(len(result['photos']), 2)


# ── ApifyLotProvider ──────────────────────────────────────────────────────────

class TestApifyLotProvider(SimpleTestCase):

    def test_no_token_returns_demo_true(self):
        provider = ApifyLotProvider(token='')
        result = provider.fetch_lot('https://www.copart.com/lot/12345678')
        self.assertTrue(result['demo'])
        self.assertEqual(result['provider'], 'apify')

    def test_no_token_does_not_raise(self):
        provider = ApifyLotProvider(token='')
        try:
            provider.fetch_lot('https://www.copart.com/lot/12345678')
        except Exception as exc:
            self.fail(f'ApifyLotProvider без токена бросил исключение: {exc}')


# ── import_lot сервис ─────────────────────────────────────────────────────────

class TestImportLotService(TestCase):

    def setUp(self):
        self.seller = make_staff('admin@test.com', superuser=True)
        Vehicle.objects.filter(vin='1HGBH41JXMN109186').delete()

    def _lot_data(self):
        return ManualLotProvider().fetch_lot(_VALID_LOT)

    def test_import_creates_vehicle(self):
        lot = self._lot_data()
        vehicle, listing, created = import_lot(lot, self.seller)
        self.assertEqual(vehicle.vin, '1HGBH41JXMN109186')
        self.assertEqual(vehicle.make, 'Honda')
        self.assertEqual(vehicle.source_auction, 'copart')
        self.assertTrue(created)

    def test_import_creates_in_transit_listing(self):
        lot = self._lot_data()
        _, listing, created = import_lot(lot, self.seller)
        self.assertEqual(listing.status, Listing.ListingStatus.IN_TRANSIT)
        self.assertEqual(listing.channel, Listing.Channel.RETAIL)
        self.assertTrue(created)

    def test_import_saves_photo_urls(self):
        lot = self._lot_data()
        vehicle, _, _ = import_lot(lot, self.seller)
        urls = list(VehicleImage.objects.filter(vehicle=vehicle).values_list('source_url', flat=True))
        self.assertIn('https://cs.copart.com/v1/photos/001.jpg', urls)
        self.assertIn('https://cs.copart.com/v1/photos/002.jpg', urls)

    def test_first_photo_is_primary(self):
        lot = self._lot_data()
        vehicle, _, _ = import_lot(lot, self.seller)
        primary = VehicleImage.objects.filter(vehicle=vehicle, is_primary=True).first()
        self.assertIsNotNone(primary)
        self.assertEqual(primary.source_url, 'https://cs.copart.com/v1/photos/001.jpg')

    def test_repeat_import_same_vin_no_duplicate_vehicle(self):
        lot = self._lot_data()
        import_lot(lot, self.seller)
        import_lot(lot, self.seller)
        self.assertEqual(Vehicle.objects.filter(vin='1HGBH41JXMN109186').count(), 1)

    def test_repeat_import_same_vin_no_duplicate_listing(self):
        lot = self._lot_data()
        import_lot(lot, self.seller)
        _, _, created2 = import_lot(lot, self.seller)
        self.assertFalse(created2)
        self.assertEqual(
            Listing.objects.filter(vehicle__vin='1HGBH41JXMN109186', status='in_transit').count(),
            1,
        )

    def test_error_in_lot_data_raises_value_error(self):
        with self.assertRaises(ValueError):
            import_lot({'error': 'VIN обязателен', 'demo': False}, self.seller)


# ── POST /api/v1/lots/import/ ─────────────────────────────────────────────────

class TestLotImportEndpoint(TestCase):

    URL = '/api/v1/lots/import/'

    def setUp(self):
        self.admin = make_staff('adm@lots.com', superuser=True)
        self.user = make_user('buyer@lots.com')
        self.client = APIClient()
        Vehicle.objects.filter(vin='1HGBH41JXMN109186').delete()

    def test_admin_can_import_lot(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.URL, {
            'source': 'manual',
            'lot_data': _VALID_LOT,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['vin'], '1HGBH41JXMN109186')
        self.assertTrue(resp.data['created'])

    def test_non_admin_gets_403(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post(self.URL, {
            'source': 'manual',
            'lot_data': _VALID_LOT,
        }, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_gets_401(self):
        resp = self.client.post(self.URL, {
            'source': 'manual',
            'lot_data': _VALID_LOT,
        }, format='json')
        self.assertEqual(resp.status_code, 401)

    def _post_as(self, user):
        self.client.force_authenticate(user)
        return self.client.post(self.URL, {'source': 'manual', 'lot_data': _VALID_LOT}, format='json')

    def test_broker_with_is_staff_gets_403(self):
        self.assertEqual(self._post_as(make_broker()).status_code, 403)

    def test_moderator_with_is_staff_gets_403(self):
        self.assertEqual(self._post_as(make_moderator()).status_code, 403)

    def test_admin_role_can_import(self):
        self.assertEqual(self._post_as(make_admin_role()).status_code, 201)

    def test_invalid_vin_returns_400(self):
        self.client.force_authenticate(self.admin)
        bad_lot = {**_VALID_LOT, 'vin': 'BADVIN'}
        resp = self.client.post(self.URL, {
            'source': 'manual',
            'lot_data': bad_lot,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_repeat_import_returns_200(self):
        self.client.force_authenticate(self.admin)
        self.client.post(self.URL, {'source': 'manual', 'lot_data': _VALID_LOT}, format='json')
        resp = self.client.post(self.URL, {'source': 'manual', 'lot_data': _VALID_LOT}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['created'])

    def test_apify_no_token_returns_demo_true(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post(self.URL, {
            'source': 'apify',
            'lot_url': 'https://www.copart.com/lot/12345678',
        }, format='json')
        # Под тест-раннером APIFY_TOKEN обнулён (core/settings.py) → ApifyLotProvider
        # в demo-режиме (demo=True, vin=None), сетевого запроса нет. Вью отвечает 400:
        # import_lot бросает ValueError('VIN обязателен для импорта лота'). Код выяснен прогоном.
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data, {'error': 'Не вдалося імпортувати лот. Перевірте дані.'})  # без текста исключения (1.11)


# ── Безопасность: auth + throttling ──────────────────────────────────────────

REGISTRY_URL = '/api/v1/vehicles/1HGBH41JXMN109186/registry/'
DECODE_URL = '/api/v1/vehicles/1HGBH41JXMN109186/decode/'


class TestRegistryRequiresAuth(TestCase):
    """Реестр (платный Opendatabot) доступен только авторизованным."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_anonymous_gets_401(self):
        from rest_framework.test import APIClient
        client = APIClient()
        resp = client.get(REGISTRY_URL)
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_user_can_access(self):
        client = auth_client(make_user('registry_access_unique@test.com'))
        with patch('integrations.views.get_opendatabot_provider') as mock_prov:
            mock_prov.return_value.get_vehicle_info.return_value = {
                'vin': '1HGBH41JXMN109186', 'demo': True, 'provider': 'opendatabot',
            }
            resp = client.get(REGISTRY_URL)
        self.assertEqual(resp.status_code, 200)
        mock_prov.return_value.get_vehicle_info.assert_called_once()


class TestExpensiveEndpointThrottle(TestCase):
    """ScopedRateThrottle применён — при deny возвращает 429."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_registry_throttle_deny_returns_429(self):
        from rest_framework.throttling import ScopedRateThrottle
        client = auth_client(make_user('thr1@test.com'))
        with patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
             patch.object(ScopedRateThrottle, 'wait', return_value=60.0):
            resp = client.get(REGISTRY_URL)
        self.assertEqual(resp.status_code, 429)

    def test_decode_throttle_deny_returns_429(self):
        from rest_framework.test import APIClient
        from rest_framework.throttling import ScopedRateThrottle
        client = APIClient()
        with patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
             patch.object(ScopedRateThrottle, 'wait', return_value=60.0):
            resp = client.get(DECODE_URL)
        self.assertEqual(resp.status_code, 429)


# ── Celery-задача: import_lot_task — идемпотентность ─────────────────────────

class TestImportLotTaskIdempotency(TestCase):
    """
    import_lot_task с одним VIN дважды:
    - первый вызов создаёт Vehicle + Listing;
    - второй вызов обновляет Vehicle, не создаёт дубль Listing.
    """

    def setUp(self):
        self.seller = make_user('seller_celery@test.com')

    _LOT = {
        'vin': 'CELERYTEST00001',
        'make': 'Toyota',
        'model': 'Camry',
        'year': 2020,
        'engine_cc': 2500,
        'fuel_type': 'petrol',
        'mileage_km': 30000,
        'damage_type': 'front',
        'auction': 'copart',
        'lot_number': 'LOT001',
        'photos': [],
        'final_bid': Decimal('8000'),
    }

    def test_two_calls_one_listing(self):
        from integrations.tasks import import_lot_task
        from listings.models import Listing
        from vehicles.models import Vehicle

        result1 = import_lot_task(self._LOT, self.seller.pk)
        result2 = import_lot_task(self._LOT, self.seller.pk)

        self.assertTrue(result1['created'])
        self.assertFalse(result2['created'])

        self.assertEqual(Vehicle.objects.filter(vin='CELERYTEST00001').count(), 1)
        self.assertEqual(Listing.objects.filter(vehicle__vin='CELERYTEST00001').count(), 1)

    def test_missing_seller_returns_error(self):
        from integrations.tasks import import_lot_task

        result = import_lot_task(self._LOT, seller_id=999999)
        self.assertIn('error', result)


# ─── VIN-отчёт: платный API под защитой ───────────────────────────────────────

class VinReportAccessTest(APITestCase):
    """
    Внутри дергается Opendatabot — платный внешний API. Раньше вью была без
    permission_classes (AllowAny из настроек) и без «дорогого» throttle:
    аноним мог жечь квоту и плодить строки в VinReport.
    """

    URL = '/api/v1/vehicles/1HGBH41JXMN109186/report/'

    def test_anonymous_rejected(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)

    def test_authenticated_allowed(self):
        user = make_user('vin@test.com')
        self.client.force_authenticate(user=user)
        # Платный Opendatabot замокан — реального запроса нет (13-S9).
        with patch('integrations.views.get_opendatabot_provider') as mock_prov:
            mock_prov.return_value.get_vehicle_info.return_value = {
                'vin': '1HGBH41JXMN109186', 'demo': True, 'provider': 'opendatabot',
                'stolen': False, 'restrictions': [], 'ua_registrations': [],
            }
            resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        mock_prov.return_value.get_vehicle_info.assert_called_once_with('1HGBH41JXMN109186')
        self.assertTrue(resp.data['demo'])
        self.assertFalse(resp.data['cached'])
        self.assertIn('ua_registry', resp.data)
        self.assertEqual(resp.data['ua_registry']['stolen'], False)

    def test_uses_expensive_throttle_scope(self):
        from integrations.views import VinReportView
        # Тот же лимит, что и у RegistryReportView с тем же внешним API.
        self.assertEqual(VinReportView.throttle_scope, 'expensive')


# ── 1.1: утечки секретов (03-S1, 03-S6) ──────────────────────────────────────

_LEAKY_URL = 'https://api.opendatabot.ua/v3/x?apikey=SECRET123'


def _http_error():
    import httpx
    request = httpx.Request('GET', _LEAKY_URL)
    return httpx.HTTPStatusError(
        f"Client error '403 Forbidden' for url '{_LEAKY_URL}'",
        request=request,
        response=httpx.Response(403, request=request),
    )


class TestProviderErrorsDoNotLeak(SimpleTestCase):

    @patch('httpx.get')
    def test_opendatabot_http_error_does_not_leak_key(self, mock_get):
        mock_get.side_effect = _http_error()
        result = RealOpendatabotProvider(api_key='SECRET123').get_vehicle_info(vin='1HGBH41JXMN109186')
        self.assertEqual(result['error'], 'service_unavailable')
        dumped = str(result)
        self.assertNotIn('SECRET123', dumped)
        self.assertNotIn('apikey', dumped)

    @patch('httpx.get')
    def test_opendatabot_error_logged_masked(self, mock_get):
        mock_get.side_effect = _http_error()
        with self.assertLogs('integrations.providers', level='WARNING') as cm:
            RealOpendatabotProvider(api_key='SECRET123').get_vehicle_info(vin='1HGBH41JXMN109186')
        out = ' '.join(cm.output)
        self.assertIn('apikey=***', out)
        self.assertNotIn('SECRET123', out)

    @patch('httpx.get')
    def test_nhtsa_error_is_generic(self, mock_get):
        from integrations.providers import NHTSAVinDecodeProvider
        mock_get.side_effect = Exception('boom internal host 10.0.0.5')
        result = NHTSAVinDecodeProvider().decode('1HGBH41JXMN109186')
        self.assertEqual(result['error'], 'service_unavailable')
        self.assertNotIn('10.0.0.5', str(result))

    @patch('httpx.post')
    def test_apify_error_is_generic(self, mock_post):
        mock_post.side_effect = Exception('boom internal host 10.0.0.5')
        result = ApifyLotProvider(token='tok').fetch_lot('https://copart.com/lot/1')
        self.assertEqual(result['error'], 'service_unavailable')
        self.assertNotIn('10.0.0.5', str(result))


class TestRegistryErrorNotCached(APITestCase):
    URL = '/api/v1/vehicles/1HGBH41JXMN109186/registry/'

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = auth_client(make_user('reg_err@test.com'))

    @patch('httpx.get')
    def test_registry_endpoint_error_not_cached(self, mock_get):
        mock_get.side_effect = _http_error()
        with patch('integrations.views.get_opendatabot_provider',
                   return_value=RealOpendatabotProvider(api_key='SECRET123')):
            resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(RegistryReport.objects.count(), 0)
        self.assertNotIn('SECRET123', resp.content.decode())

    def test_old_error_record_not_served_from_cache(self):
        RegistryReport.objects.create(
            vin='1HGBH41JXMN109186', provider='opendatabot', payload={'error': 'old', 'leak': 'SECRET123'},
        )
        with patch('integrations.views.get_opendatabot_provider',
                   return_value=RealOpendatabotProvider(api_key='')):
            resp = self.client.get(self.URL)
        self.assertNotIn('SECRET123', resp.content.decode())
        self.assertNotEqual(resp.json().get('cached'), True)

    @patch('httpx.get')
    def test_registry_endpoint_success_still_cached(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _MOCK_ODB_RESPONSE
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        with patch('integrations.views.get_opendatabot_provider',
                   return_value=RealOpendatabotProvider(api_key='k')):
            first = self.client.get(self.URL)
            second = self.client.get(self.URL)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()['cached'])
        self.assertTrue(second.json()['cached'])
        self.assertEqual(RegistryReport.objects.count(), 1)


class TestPurgeRegistryErrorsCommand(TestCase):

    def setUp(self):
        RegistryReport.objects.create(vin='A' * 17, provider='opendatabot', payload={'error': 'x'})
        RegistryReport.objects.create(vin='B' * 17, provider='opendatabot', payload={'brand': 'Honda'})

    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command('purge_registry_errors', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_does_not_delete(self):
        self.assertEqual(
            self._run().strip(),
            'dry-run: записей с error: 1. Для удаления добавьте --confirm.',
        )
        self.assertEqual(RegistryReport.objects.count(), 2)

    def test_confirm_deletes_only_error_records(self):
        self._run('--confirm')
        self.assertEqual(list(RegistryReport.objects.values_list('vin', flat=True)), ['B' * 17])


# ── upload_lot_photos: allowlist хостов, лимит, тип по содержимому (1.10, 03-S5, 23-D63) ──

LOT_MODULE = 'integrations.management.commands.upload_lot_photos'
LOT_CMD = f'{LOT_MODULE}._make_client'
PUBLIC_IP = '93.184.216.34'


@override_settings(LOT_PHOTO_ALLOWED_HOSTS=['cdn.lots.test', '*.img.test'], UPLOAD_IMAGE_MAX_SIZE_MB=1)
class TestUploadLotPhotos(TestCase):
    def setUp(self):
        use_temp_media(self)
        self.vehicle = Vehicle.objects.create(
            vin='LOTPHOTO000000001', make='Ford', model='Focus', year=2019,
            engine_cc=1600, fuel_type='petrol', mileage_km=1000,
        )
        self.calls = []
        # DNS в тестах не ходит: по умолчанию хосты резолвятся в публичный адрес.
        self.resolved = [PUBLIC_IP]
        resolver = patch(f'{LOT_MODULE}._resolve', side_effect=lambda host, port: list(self.resolved))
        self.resolve_mock = resolver.start()
        self.addCleanup(resolver.stop)

    def _image(self, url='https://cdn.lots.test/a.jpg'):
        return VehicleImage.objects.create(vehicle=self.vehicle, source_url=url)

    def _run(self, handler):
        def recording(request):
            self.calls.append(str(request.url))
            return handler(request)

        client = httpx.Client(transport=httpx.MockTransport(recording), follow_redirects=False)
        out = StringIO()
        with patch(LOT_CMD, return_value=client):
            call_command('upload_lot_photos', stdout=out)
        return out.getvalue()

    def test_valid_jpeg_saved_without_exif(self):
        img = self._image()
        self._run(lambda r: httpx.Response(200, content=image_bytes(gps=True),
                                           headers={'content-type': 'image/jpeg'}))
        img.refresh_from_db()
        self.assertRegex(img.image.name, r'^vehicle_photos/[0-9a-f]{32}\.jpg$')
        with img.image.open('rb') as fh, PILImage.open(fh) as saved:
            self.assertEqual(dict(saved.getexif()), {})

    def test_wildcard_subdomain_allowed(self):
        img = self._image('https://x1.img.test/a.jpg')
        self._run(lambda r: httpx.Response(200, content=image_bytes()))
        img.refresh_from_db()
        self.assertTrue(img.image)

    def test_wildcard_does_not_match_suffix_without_dot(self):
        img = self._image('https://evilimg.test/a.jpg')
        self._run(lambda r: httpx.Response(200, content=image_bytes()))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, [])

    def test_response_over_limit_skipped(self):
        img = self._image()
        # Без Content-Length: обрыв по счётчику байт при чтении потока.
        big = image_bytes() + b'\0' * (1024 * 1024)
        out = self._run(lambda r: httpx.Response(200, stream=httpx.ByteStream(big)))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertIn('ліміт', out)

    def test_html_with_image_content_type_skipped(self):
        img = self._image()
        self._run(lambda r: httpx.Response(200, content=b'<html><script>1</script></html>',
                                           headers={'content-type': 'image/jpeg'}))
        img.refresh_from_db()
        self.assertFalse(img.image)

    def test_redirect_to_foreign_host_not_followed(self):
        img = self._image()

        def handler(request):
            if request.url.host == 'cdn.lots.test':
                return httpx.Response(302, headers={'location': 'http://169.254.169.254/latest/meta-data'})
            return httpx.Response(200, content=image_bytes())

        out = self._run(handler)
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, ['https://cdn.lots.test/a.jpg'])
        self.assertIn('169.254.169.254', out)

    def test_redirect_within_allowed_hosts_followed(self):
        img = self._image()

        def handler(request):
            if request.url.path == '/a.jpg':
                return httpx.Response(302, headers={'location': '/b.jpg'})
            return httpx.Response(200, content=image_bytes())

        self._run(handler)
        img.refresh_from_db()
        self.assertTrue(img.image)
        self.assertEqual(self.calls, ['https://cdn.lots.test/a.jpg', 'https://cdn.lots.test/b.jpg'])

    def test_redirect_loop_stops(self):
        img = self._image()
        self._run(lambda r: httpx.Response(302, headers={'location': '/again.jpg'}))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(len(self.calls), 4)  # исходный запрос + 3 редиректа

    def test_source_host_outside_allowlist_not_requested(self):
        img = self._image('https://evil.test/a.jpg')
        self._run(lambda r: httpx.Response(200, content=image_bytes()))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, [])

    def test_http_source_rejected(self):
        img = self._image('http://cdn.lots.test/a.jpg')
        self._run(lambda r: httpx.Response(200, content=image_bytes()))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, [])

    def test_redirect_to_http_rejected(self):
        img = self._image()
        self._run(lambda r: httpx.Response(302, headers={'location': 'http://cdn.lots.test/b.jpg'}))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, ['https://cdn.lots.test/a.jpg'])

    def test_allowed_host_resolving_to_internal_ip_rejected(self):
        for ip in ('127.0.0.1', '10.0.0.5', '192.168.1.1', '169.254.169.254', '0.0.0.0',
                   '224.0.0.1', '240.0.0.1', '::1', 'fe80::1', '::ffff:127.0.0.1', '100.64.0.1'):
            with self.subTest(ip=ip):
                self.calls.clear()
                self.resolved = [PUBLIC_IP, ip]  # хоть один внутренний адрес — отказ
                img = self._image()
                out = self._run(lambda r: httpx.Response(200, content=image_bytes()))
                img.refresh_from_db()
                self.assertFalse(img.image)
                self.assertEqual(self.calls, [])
                self.assertIn('внутрішню адресу', out)
                img.delete()

    def test_redirect_target_resolving_to_internal_ip_rejected(self):
        img = self._image()

        def resolve(host, port):
            return ['10.1.2.3'] if host == 'x1.img.test' else [PUBLIC_IP]

        self.resolve_mock.side_effect = resolve
        self._run(lambda r: httpx.Response(302, headers={'location': 'https://x1.img.test/b.jpg'}))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, ['https://cdn.lots.test/a.jpg'])

    def test_unresolvable_host_rejected(self):
        img = self._image()
        self.resolve_mock.side_effect = OSError('no such host')
        self._run(lambda r: httpx.Response(200, content=image_bytes()))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertEqual(self.calls, [])

    def test_slow_download_hits_total_deadline(self):
        img = self._image()
        body = image_bytes()
        chunks = [body[i:i + 64] for i in range(0, len(body), 64)]
        clock = iter(range(0, 10_000, 10))  # каждый вызов monotonic() — +10 с
        with patch(f'{LOT_MODULE}.time.monotonic', side_effect=lambda: next(clock)):
            out = self._run(lambda r: httpx.Response(200, stream=_SlowStream(chunks)))
        img.refresh_from_db()
        self.assertFalse(img.image)
        self.assertIn('час завантаження', out)

    @override_settings(LOT_PHOTO_ALLOWED_HOSTS=[])
    def test_empty_allowlist_no_network(self):
        self._image()
        out = self._run(lambda r: httpx.Response(200, content=image_bytes()))
        self.assertIn('не настроено', out)
        self.assertEqual(self.calls, [])


class _SlowStream(httpx.SyncByteStream):
    """Тело ответа кусками (каждый кусок — отдельная итерация iter_bytes)."""

    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


# ── Каркас адаптеров и статус интеграций (задача 3.1) ─────────────────────────

from datetime import timedelta  # noqa: E402

from django.core.checks import run_checks  # noqa: E402
from django.core.exceptions import ImproperlyConfigured  # noqa: E402
from django.test import Client  # noqa: E402
from django.utils import timezone  # noqa: E402

from core.test_runner import ExternalNetworkBlocked  # noqa: E402
from integrations import base, registry  # noqa: E402
from integrations.models import IntegrationHealth  # noqa: E402

BASE_KEYS = ('nbu', 'vin_decode', 'vin_report', 'opendatabot', 'lots', 'liqpay', 'email', 'telegram')
EMPTY_ENV = dict(
    CARVERTICAL_API_KEY='', OPENDATABOT_API_KEY='', APIFY_TOKEN='', LIQPAY_PUBLIC_KEY='',
    LIQPAY_PRIVATE_KEY='', TELEGRAM_BOT_TOKEN='', TELEGRAM_CHANNEL_ID='', TELEGRAM_B2B_CHANNEL_ID='',
    TELEGRAM_WEBHOOK_SECRET='', EMAIL_HOST='', EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='',
)


class IsPlaceholderTests(SimpleTestCase):

    def test_placeholders_are_true(self):
        for value in ('', '   ', None, 'your_opendatabot_api_key', 'your-key', 'changeme', 'xxx', '<token>'):
            with self.subTest(value=value):
                self.assertTrue(base.is_placeholder(value))

    def test_real_value_is_not_placeholder(self):
        self.assertFalse(base.is_placeholder('a1b2c3d4e5f6a7b8'))


class ResolveModeTests(SimpleTestCase):

    @override_settings(OPENDATABOT_MODE='auto')
    def test_auto_with_key_is_real(self):
        res = base.resolve_mode('opendatabot', True, env_vars=('OPENDATABOT_API_KEY',))
        self.assertEqual((res.mode, res.configured), ('real', True))

    @override_settings(OPENDATABOT_MODE='auto', OPENDATABOT_API_KEY='your_opendatabot_api_key')
    def test_auto_with_placeholder_is_off_not_configured(self):
        status = registry.build_status(registry.RegisteredProvider('opendatabot', 'x', registry._opendatabot))
        self.assertEqual((status.mode, status.configured), ('off', False))
        self.assertIn('Не налаштовано: немає OPENDATABOT_API_KEY', status.reason)

    @override_settings(LOTS_MODE='demo')
    def test_demo_mode(self):
        res = base.resolve_mode('lots', False)
        self.assertEqual((res.mode, res.configured), ('demo', True))

    @override_settings(LIQPAY_MODE='real')
    def test_real_without_key_is_config_error(self):
        res = base.resolve_mode('liqpay', False, env_vars=('LIQPAY_PUBLIC_KEY',))
        self.assertEqual((res.mode, res.configured), ('real', False))
        self.assertIn('Помилка конфігурації', res.reason)

    @override_settings(TELEGRAM_MODE='off')
    def test_off_mode(self):
        res = base.resolve_mode('telegram', True)
        self.assertEqual((res.mode, res.configured), ('off', False))

    @override_settings(NBU_MODE='auto')
    def test_auto_without_credentials_provider_is_real(self):
        res = base.resolve_mode('nbu', False, needs_credentials=False)
        self.assertEqual((res.mode, res.configured), ('real', True))

    @override_settings(NBU_MODE='foo')
    def test_invalid_mode_is_not_configured(self):
        res = base.resolve_mode('nbu', True, needs_credentials=False)
        self.assertEqual((res.mode, res.configured, res.valid), ('off', False, False))


class _DemoAdapter(base.BaseProvider):
    key = 'lots'
    title = 'Тест'
    env_vars = ('APIFY_TOKEN',)


class BaseProviderResponseTests(SimpleTestCase):

    @override_settings(LOTS_MODE='off')
    def test_off_response_has_no_data_fields(self):
        resp = _DemoAdapter().wrap_response({'price': 100})
        self.assertEqual(set(resp), {'configured', 'demo', 'reason'})
        self.assertFalse(resp['configured'])

    @override_settings(LOTS_MODE='real')
    def test_real_without_key_response_not_configured(self):
        class NoKey(_DemoAdapter):
            def has_credentials(self):
                return False
        resp = NoKey().wrap_response({'price': 100})
        self.assertNotIn('price', resp)
        self.assertIs(resp['configured'], False)

    @override_settings(LOTS_MODE='demo')
    def test_demo_response_flags(self):
        resp = _DemoAdapter().wrap_response({'price': 100})
        self.assertEqual(resp, {'price': 100, 'configured': True, 'demo': True})

    @override_settings(LOTS_MODE='real')
    def test_real_response_flags(self):
        resp = _DemoAdapter().wrap_response({'price': 100})
        self.assertEqual(resp, {'price': 100, 'configured': True, 'demo': False})


class RegistryTests(TestCase):

    @override_settings(**EMPTY_ENV)
    def test_all_base_statuses_build(self):
        keys = {s.key for s in registry.get_statuses()}
        self.assertTrue(set(BASE_KEYS) <= keys)

    @override_settings(**{**EMPTY_ENV, 'OPENDATABOT_API_KEY': 'SECRET123', 'TELEGRAM_BOT_TOKEN': 'tok-12345-abc'})
    def test_status_does_not_contain_key_values(self):
        statuses = registry.get_statuses()
        blob = repr(statuses)
        self.assertNotIn('SECRET123', blob)
        self.assertNotIn('tok-12345-abc', blob)
        opendatabot = next(s for s in statuses if s.key == 'opendatabot')
        self.assertEqual(opendatabot.env_states['OPENDATABOT_API_KEY'], 'задано')

    def test_duplicate_registration_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, 'уже зарегистрирован'):
            registry.register_provider('nbu', 'Дубль', lambda: None)

    def test_broken_status_fn_does_not_break_registry(self):
        def boom():
            raise ValueError('boom')
        registry.register_provider('t_broken', 'Зламаний', boom)
        self.addCleanup(registry.unregister_provider, 't_broken')
        status = next(s for s in registry.get_statuses() if s.key == 't_broken')
        self.assertEqual(status.reason, 'Помилка перевірки статусу')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='smtp.example.com',
                       DEFAULT_FROM_EMAIL='noreply@example.com')
    def test_email_configured_with_smtp(self):
        status = next(s for s in registry.get_statuses() if s.key == 'email')
        self.assertEqual((status.mode, status.configured), ('real', True))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='')
    def test_email_smtp_without_host_not_configured(self):
        status = next(s for s in registry.get_statuses() if s.key == 'email')
        self.assertEqual((status.mode, status.configured), ('off', False))


class RecordErrorTests(TestCase):

    @override_settings(OPENDATABOT_API_KEY='SECRETVALUE-987654')
    def test_secrets_not_in_last_error_or_log(self):
        exc = RuntimeError(
            'GET https://api.example.com/v1?apikey=SECRET123 failed, key SECRETVALUE-987654'
        )
        with self.assertLogs('integrations.base', level='WARNING') as logs:
            base.record_error('opendatabot', exc)
        row = IntegrationHealth.objects.get(provider_key='opendatabot')
        for text in (row.last_error, '\n'.join(logs.output)):
            self.assertNotIn('SECRET123', text)
            self.assertNotIn('SECRETVALUE-987654', text)
        self.assertEqual(row.error_count, 1)
        self.assertIsNotNone(row.last_error_at)

    def test_last_error_truncated_and_count_grows(self):
        base.record_error('nbu', ValueError('x' * 2000))
        base.record_error('nbu', ValueError('y'))
        row = IntegrationHealth.objects.get(provider_key='nbu')
        self.assertEqual(row.error_count, 2)
        self.assertLessEqual(len(row.last_error), 500)

    def test_record_success_sets_time(self):
        base.record_success('nbu')
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='nbu').last_success_at)


class NetworkGuardNotSwallowedTests(TestCase):

    def test_blocked_network_propagates_and_health_untouched(self):
        adapter = _DemoAdapter()
        with self.assertRaisesMessage(ExternalNetworkBlocked, 'Внешний сетевой запрос в тесте'):
            adapter.call(httpx.get, 'http://example.com/')
        self.assertEqual(IntegrationHealth.objects.count(), 0)

    def test_retryable_error_is_recorded_and_returned(self):
        def fail():
            raise httpx.ConnectError('down')
        result = _DemoAdapter().call(fail)
        self.assertEqual(result['error'], 'service_unavailable')
        self.assertEqual(IntegrationHealth.objects.get(provider_key='lots').error_count, 1)

    def test_success_is_recorded(self):
        self.assertEqual(_DemoAdapter().call(lambda: {'ok': 1}), {'ok': 1})
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='lots').last_success_at)


class StatusPageTests(TestCase):
    URL = '/admin/integrations/status/'

    def _login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_superuser_sees_all_providers(self):
        resp = self._login(make_staff(superuser=True)).get(self.URL)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        providers = registry.get_providers()
        self.assertGreaterEqual(len(providers), 8)
        for provider in providers:
            self.assertIn(provider.title, html)

    @override_settings(OPENDATABOT_API_KEY='SECRET123456')
    def test_page_never_prints_key_values(self):
        html = self._login(make_staff(superuser=True)).get(self.URL).content.decode()
        self.assertIn('OPENDATABOT_API_KEY', html)
        self.assertNotIn('SECRET123456', html)

    def test_staff_without_permission_gets_403(self):
        self.assertEqual(self._login(make_staff()).get(self.URL).status_code, 403)

    def test_regular_user_redirected_to_admin_login(self):
        resp = self._login(make_user()).get(self.URL)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp['Location'].startswith('/admin/login/'))

    def test_anonymous_redirected(self):
        self.assertEqual(Client().get(self.URL).status_code, 302)

    def test_registered_provider_appears_without_registry_edit(self):
        registry.register_provider(
            't_extra', 'Додатковий тест-провайдер',
            lambda: base.ProviderStatus(key='t_extra', title='Додатковий тест-провайдер'),
        )
        self.addCleanup(registry.unregister_provider, 't_extra')
        resp = self._login(make_staff(superuser=True)).get(self.URL)
        self.assertContains(resp, 'Додатковий тест-провайдер')

    def test_index_has_link_without_attention_mark(self):
        html = self._login(make_staff(superuser=True)).get('/admin/').content.decode()
        self.assertIn(self.URL, html)
        self.assertNotIn('потрібна увага', html)

    @override_settings(LIQPAY_MODE='real', LIQPAY_PUBLIC_KEY='', LIQPAY_PRIVATE_KEY='')
    def test_index_attention_on_real_without_key(self):
        resp = self._login(make_staff(superuser=True)).get('/admin/')
        self.assertContains(resp, 'потрібна увага')

    def test_index_attention_on_recent_error(self):
        IntegrationHealth.objects.create(
            provider_key='nbu', last_error_at=timezone.now() - timedelta(hours=1), last_error='x',
        )
        resp = self._login(make_staff(superuser=True)).get('/admin/')
        self.assertContains(resp, 'потрібна увага')

    def test_old_error_does_not_raise_attention(self):
        IntegrationHealth.objects.create(
            provider_key='nbu', last_error_at=timezone.now() - timedelta(hours=30), last_error='x',
        )
        resp = self._login(make_staff(superuser=True)).get('/admin/')
        self.assertNotContains(resp, 'потрібна увага')

    def test_health_admin_add_forbidden(self):
        client = self._login(make_staff(superuser=True))
        self.assertEqual(client.post('/admin/integrations/integrationhealth/add/', {}).status_code, 403)

    def test_health_admin_change_forbidden(self):
        row = IntegrationHealth.objects.create(provider_key='nbu')
        client = self._login(make_staff(superuser=True))
        self.assertEqual(client.post(f'/admin/integrations/integrationhealth/{row.pk}/change/', {}).status_code, 403)

    def test_health_admin_delete_forbidden(self):
        row = IntegrationHealth.objects.create(provider_key='nbu')
        client = self._login(make_staff(superuser=True))
        self.assertEqual(client.post(f'/admin/integrations/integrationhealth/{row.pk}/delete/', {}).status_code, 403)


class SystemCheckTests(SimpleTestCase):

    @staticmethod
    def _ids():
        return [m.id for m in run_checks() if (m.id or '').startswith('integrations.')]

    def test_clean_env_has_no_integration_messages(self):
        self.assertEqual(self._ids(), [])

    @override_settings(LIQPAY_MODE='real', LIQPAY_PUBLIC_KEY='', LIQPAY_PRIVATE_KEY='')
    def test_w001_real_without_key(self):
        self.assertEqual(self._ids(), ['integrations.W001'])

    @override_settings(DEBUG=False, NBU_MODE='demo')
    def test_w002_demo_without_debug(self):
        self.assertEqual(self._ids(), ['integrations.W002'])

    @override_settings(DEBUG=True, NBU_MODE='demo')
    def test_demo_in_debug_is_fine(self):
        self.assertEqual(self._ids(), [])

    @override_settings(NBU_MODE='foo')
    def test_invalid_mode_is_error(self):
        self.assertEqual(self._ids(), ['integrations.E001'])


class MaskSecretsFormatTests(SimpleTestCase):

    def _assert_masked(self, text, secret):
        self.assertNotIn(secret, base.mask_secrets(text))

    def test_telegram_token_in_path(self):
        self._assert_masked(
            'POST https://api.telegram.org/bot123456789:AAHabcdefghijklmnopqrstuvwxyz0123456/sendMessage',
            'AAHabcdefghijklmnopqrstuvwxyz0123456',
        )

    def test_postgres_dsn_password(self):
        self._assert_masked('could not connect postgresql://user:pw-Secret1@db/x', 'pw-Secret1')

    def test_redis_dsn_password_without_user(self):
        self._assert_masked('redis://:pw-Secret2@redis:6379/0', 'pw-Secret2')

    def test_dsn_keeps_host(self):
        self.assertEqual(base.mask_secrets('redis://:pw-Secret2@redis'), 'redis://:***@redis')

    def test_authorization_bearer_header(self):
        self._assert_masked('Authorization: Bearer abc.DEF-secret9', 'abc.DEF-secret9')

    def test_x_api_key_header(self):
        self._assert_masked('X-API-Key: key-Secret3', 'key-Secret3')

    def test_api_key_dash_assignment(self):
        self._assert_masked('request api-key=Secret4 failed', 'Secret4')

    def test_json_api_key(self):
        self._assert_masked('{"api_key": "Secret5", "other": 1}', 'Secret5')

    def test_json_password_and_token(self):
        out = base.mask_secrets('{"password": "Secret6", "access_token": "Secret7"}')
        self.assertNotIn('Secret6', out)
        self.assertNotIn('Secret7', out)

    def test_token_equals_outside_url(self):
        self._assert_masked('call failed token=Secret8 retry', 'Secret8')

    def test_database_password_from_settings(self):
        from unittest.mock import patch
        with patch.dict(settings.DATABASES['default'], {'PASSWORD': 'dbpass-Secret9'}):
            self._assert_masked('connection refused, password dbpass-Secret9 rejected', 'dbpass-Secret9')

    def test_plain_text_unchanged(self):
        self.assertEqual(base.mask_secrets('ConnectError: timeout'), 'ConnectError: timeout')


class MorePlaceholderTests(SimpleTestCase):

    def test_extra_placeholders(self):
        for value in ('test', 'DUMMY', 'Placeholder', 'none', 'null', 'todo'):
            with self.subTest(value=value):
                self.assertTrue(base.is_placeholder(value))

    def test_sandbox_prefix_is_real_key(self):
        self.assertFalse(base.is_placeholder('sandbox_i12345678901'))


class IndexLinkPermissionTests(TestCase):

    def test_staff_without_permission_has_no_link(self):
        client = Client()
        client.force_login(make_staff())
        self.assertNotContains(client.get('/admin/'), '/admin/integrations/status/')


class NotAppliedNoteTests(SimpleTestCase):

    def test_liqpay_and_telegram_note_mode_not_applied(self):
        statuses = {s.key: s for s in registry.get_statuses(with_health=False)}
        for key in ('liqpay', 'telegram'):
            self.assertIn(registry.NOT_APPLIED_NOTE, statuses[key].notes)
