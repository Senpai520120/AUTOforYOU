"""LiqPayClient: тесты против выживших мутантов cosmic-ray (scripts/mutation.sh liqpay).

Главное: по умолчанию НЕ sandbox (иначе прод принимал бы тестовые оплаты), версия API 3,
кириллица в описании уходит UTF-8 как есть (подпись считается по этим байтам).
"""
import base64
import json

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from payments.liqpay_client import LiqPayClient


def _params(checkout: dict) -> dict:
    return json.loads(base64.b64decode(checkout['form_data']['data']).decode('utf-8'))


class LiqPayClientDefaultsTests(SimpleTestCase):
    def test_client_is_not_sandbox_by_default(self):
        checkout = LiqPayClient('pk', 'sk').create_checkout('o-1', '10.00', 'UAH', 'Оплата')
        self.assertIs(checkout['sandbox'], False)
        self.assertEqual(_params(checkout)['sandbox'], 0)

    @override_settings(LIQPAY_PUBLIC_KEY='pk-real', LIQPAY_PRIVATE_KEY='sk-real', LIQPAY_SANDBOX=True)
    def test_from_settings_reads_keys_and_sandbox(self):
        client = LiqPayClient.from_settings()
        self.assertEqual((client.public_key, client.private_key, client.sandbox), ('pk-real', 'sk-real', True))

    def test_from_settings_without_sandbox_setting_is_not_sandbox(self):
        with self.settings():
            del settings.LIQPAY_SANDBOX
            self.assertIs(LiqPayClient.from_settings().sandbox, False)

    def test_checkout_uses_api_version_3(self):
        checkout = LiqPayClient('pk', 'sk').create_checkout('o-1', '10.00', 'UAH', 'Оплата')
        self.assertEqual(_params(checkout)['version'], 3)

    def test_cyrillic_description_is_raw_utf8_not_escaped(self):
        checkout = LiqPayClient('pk', 'sk').create_checkout('o-1', '10.00', 'UAH', 'Оплата')
        raw = base64.b64decode(checkout['form_data']['data'])
        self.assertIn('Оплата'.encode('utf-8'), raw)
        self.assertNotIn(b'\\u', raw)

    def test_map_status_works_on_instance(self):
        client = LiqPayClient('pk', 'sk')
        self.assertEqual(client.map_status('success'), 'completed')
        self.assertEqual(client.map_status('unknown'), 'pending')
