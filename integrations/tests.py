"""
Тесты интеграции Opendatabot: провайдер, кэш RegistryReport, эндпоинт.
"""
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
