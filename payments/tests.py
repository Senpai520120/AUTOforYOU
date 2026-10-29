"""Callback LiqPay: тексти помилок, адаптер провайдера, режим у checkout. Безпека платежів (1.15) - tests_liqpay_security."""
from decimal import Decimal

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from local_listings.models import PromotionTariff
from tests.factories import auth_client, make_local_listing, make_user


class TestCallbackErrorTexts(APITestCase):
    """Клиенту (LiqPay/атакующему) не уходит текст исключения, тип и детали - в лог."""

    @override_settings(LIQPAY_PUBLIC_KEY='test_pub', LIQPAY_PRIVATE_KEY='test_priv')
    def test_bad_signature_has_generic_text(self):
        from unittest import mock

        from .liqpay_client import LiqPayClient, LiqPaySignatureError

        secret = 'SECRET-INTERNAL-DETAIL'
        with mock.patch.object(LiqPayClient, 'decode_callback', side_effect=LiqPaySignatureError(secret)):
            with self.assertLogs('payments.views', level='WARNING') as logs:
                resp = self.client.post(
                    '/api/v1/payments/liqpay/callback/', {'data': 'x', 'signature': 'y'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn(secret, resp.content.decode())
        self.assertIn('LiqPaySignatureError', logs.output[0])


# ─── Адаптер LiqPay (задача 3.4b) ─────────────────────────────────────────────

import base64  # noqa: E402
import json  # noqa: E402

from django.test import SimpleTestCase  # noqa: E402

from integrations.base import MODE_DEMO, MODE_OFF, MODE_REAL  # noqa: E402

from .providers import LiqPayProvider  # noqa: E402

PUB, PRIV = 'test-only-public-key', 'test-only-private-key'
NO_KEYS = {'LIQPAY_PUBLIC_KEY': '', 'LIQPAY_PRIVATE_KEY': ''}
UNAVAILABLE = 'Оплата тимчасово недоступна'


def _sent_params(resp):
    """Параметры, подписанные в checkout (поле data в форме)."""
    return json.loads(base64.b64decode(resp.data['form_data']['data']))


class PromoteCheckoutModeTests(APITestCase):
    """Режим LiqPay в подписанных параметрах checkout (promote: единственный рабочий вход после 1.15)."""

    def setUp(self):
        owner = make_user()
        self.client = auth_client(owner)
        self.url = f'/api/v1/local/listings/{make_local_listing(owner).pk}/promote/'
        PromotionTariff.objects.create(code='t-top', name='top', type='top', price=Decimal('10'), currency='UAH')

    def _post(self):
        return self.client.post(self.url, {'tariff': 't-top'}, format='json')

    @override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='auto', LIQPAY_SANDBOX=False)
    def test_auto_follows_liqpay_sandbox_flag(self):
        self.assertEqual(_sent_params(self._post())['sandbox'], 0)

    @override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='auto', LIQPAY_SANDBOX=True)
    def test_auto_sandbox_when_flag_true(self):
        self.assertEqual(_sent_params(self._post())['sandbox'], 1)

    @override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='sandbox', LIQPAY_SANDBOX=False)
    def test_sandbox_mode_sends_sandbox_1(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIs(resp.data['sandbox'], True)
        self.assertEqual(_sent_params(resp)['sandbox'], 1)

    @override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='real', LIQPAY_SANDBOX=True)
    def test_real_mode_sends_sandbox_0(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertIs(resp.data['sandbox'], False)
        self.assertEqual(_sent_params(resp)['sandbox'], 0)


class LiqPayProviderTests(SimpleTestCase):
    @override_settings(LIQPAY_MODE='real', **NO_KEYS)
    def test_real_without_keys_is_config_error(self):
        res = LiqPayProvider().resolution()
        self.assertEqual((res.mode, res.configured), (MODE_REAL, False))

    @override_settings(LIQPAY_MODE='auto', **NO_KEYS)
    def test_auto_without_keys_off(self):
        res = LiqPayProvider().resolution()
        self.assertEqual((res.mode, res.configured), (MODE_OFF, False))
        self.assertFalse(LiqPayProvider().is_configured())

    @override_settings(LIQPAY_MODE='auto', LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY='')
    def test_one_key_is_not_enough(self):
        self.assertFalse(LiqPayProvider().is_configured())

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
    def test_mode_switches_sandbox_and_real(self):
        provider = LiqPayProvider()
        self.assertEqual(provider.resolution().mode, MODE_DEMO)
        self.assertTrue(provider.is_sandbox)
        with override_settings(LIQPAY_MODE='real'):
            self.assertEqual(provider.resolution().mode, MODE_REAL)
            self.assertFalse(provider.is_sandbox)

    @override_settings(LIQPAY_MODE='sandbox', PAYMENTS_ENABLED=False,
                       LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
    def test_checkout_works_when_payments_flag_off(self):
        checkout = LiqPayProvider().create_checkout('o-1', '5.00', 'USD', 'тест')
        self.assertIs(checkout['sandbox'], True)

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
    def test_status_shows_both_levels_without_key_values(self):
        for flag, text in ((False, 'Платежі: вимкнено'), (True, 'Платежі: увімкнено')):
            with override_settings(PAYMENTS_ENABLED=flag):
                st = LiqPayProvider().status()
            self.assertIn(text, ' '.join(st.notes))
            self.assertEqual(st.mode_label, 'sandbox')
        self.assertNotIn(PRIV, repr(st))

    @override_settings(LIQPAY_MODE='real', LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
    def test_status_real_label(self):
        self.assertEqual(LiqPayProvider().status().mode_label, 'real')

    @override_settings(LIQPAY_MODE='off', LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
    def test_create_checkout_refuses_when_not_configured(self):
        from .providers import PaymentNotConfigured
        with self.assertRaises(PaymentNotConfigured):
            LiqPayProvider().create_checkout('o-2', '5.00', 'USD', 'тест')

    def test_no_from_settings_in_views(self):
        from pathlib import Path

        from django.conf import settings as dj
        for rel in ('payments/views.py', 'local_listings/views.py'):
            self.assertNotIn('from_settings', Path(dj.BASE_DIR, rel).read_text(encoding='utf-8'), rel)
