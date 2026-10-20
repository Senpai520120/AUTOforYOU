"""
Тесты интеграции: Opendatabot (провайдер, кэш, эндпоинт) + импорт лотов аукционов.
"""
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

import httpx
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
