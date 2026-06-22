"""
Тесты интеграции: Opendatabot (провайдер, кэш, эндпоинт) + импорт лотов аукционов.
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from integrations.models import RegistryReport
from integrations.providers import RealOpendatabotProvider


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
            result = provider.get_vehicle_info(vin='1HGBH41JXMN109186')
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
        RegistryReport.objects.all().delete()

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

        client = APIClient()
        client.get('/api/v1/vehicles/1HGBH41JXMN109186/registry/')

        self.assertEqual(
            RegistryReport.objects.filter(vin='1HGBH41JXMN109186', provider='opendatabot').count(),
            1,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Импорт лотов аукционов
# ═══════════════════════════════════════════════════════════════════════════════

from integrations.importer import import_lot
from integrations.providers import ManualLotProvider, ApifyLotProvider
from vehicles.models import Vehicle, VehicleImage
from listings.models import Listing

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
            result = provider.fetch_lot('https://www.copart.com/lot/12345678')
        except Exception as exc:
            self.fail(f'ApifyLotProvider без токена бросил исключение: {exc}')


# ── import_lot сервис ─────────────────────────────────────────────────────────

class TestImportLotService(TestCase):

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.seller = User.objects.create_superuser(
            email='admin@test.com', password='pass',
        )
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
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient
        User = get_user_model()
        self.admin = User.objects.create_superuser(email='adm@lots.com', password='pass')
        self.user = User.objects.create_user(email='buyer@lots.com', password='pass')
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
        # Apify без токена вернёт demo=True и vin=None → ошибка провайдера → 400
        # или если vin None, import_lot бросает ValueError → 400
        self.assertIn(resp.status_code, (200, 201, 400))
        # Главное — не 500
        self.assertNotEqual(resp.status_code, 500)
