"""
Валідація вхідних даних чекауту.

Раніше в'ю читала поля прямо з request.data: нечислова сума давала 500,
неіснуючий листинг мовчки створював платіж у нікуди.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Payment

User = get_user_model()

CHECKOUT_URL = '/api/v1/payments/liqpay/checkout/'


@override_settings(LIQPAY_PUBLIC_KEY='test_pub', LIQPAY_PRIVATE_KEY='test_priv')
class TestCheckoutValidation(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='pay@test.com', password='pass1234')
        self.client.force_authenticate(user=self.user)

    def _post(self, **overrides):
        payload = {'order_id': 'ord-1', 'amount': '100.00', 'currency': 'USD'}
        payload.update(overrides)
        return self.client.post(CHECKOUT_URL, payload, format='json')

    def test_valid_payload_creates_pending_payment(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        payment = Payment.objects.get(order_id='ord-1')
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, Decimal('100.00'))

    def test_non_numeric_amount_returns_400_not_500(self):
        resp = self._post(amount='не число')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('amount', resp.data)

    def test_zero_amount_rejected(self):
        self.assertEqual(self._post(amount='0').status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_amount_rejected(self):
        self.assertEqual(self._post(amount='-50').status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_currency_rejected(self):
        resp = self._post(currency='XYZ')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('currency', resp.data)

    def test_unknown_purpose_rejected(self):
        resp = self._post(purpose='steal_everything')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('purpose', resp.data)

    def test_nonexistent_listing_rejected(self):
        resp = self._post(listing_id=999999)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('listing_id', resp.data)
        self.assertFalse(Payment.objects.filter(order_id='ord-1').exists())

    def test_missing_amount_rejected(self):
        resp = self.client.post(CHECKOUT_URL, {'order_id': 'ord-2'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TestCallbackErrorTexts(APITestCase):
    """Клиенту (LiqPay/атакующему) не уходит текст исключения, тип и детали - в лог."""

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

PUB, PRIV = 'test_pub', 'test_priv'
NO_KEYS = {'LIQPAY_PUBLIC_KEY': '', 'LIQPAY_PRIVATE_KEY': ''}
UNAVAILABLE = 'Оплата тимчасово недоступна'


def _sent_params(resp):
    """Параметры, подписанные в checkout (поле data в форме)."""
    return json.loads(base64.b64decode(resp.data['form_data']['data']))


class CheckoutUnavailableTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=User.objects.create_user(email='na@test.com', password='pass1234'))

    def _assert_503(self):
        resp = self.client.post(CHECKOUT_URL, {'order_id': 'ord-na', 'amount': '10.00', 'currency': 'USD'},
                                format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.data['detail'], UNAVAILABLE)
        self.assertIs(resp.data['configured'], False)
        self.assertFalse(Payment.objects.filter(order_id='ord-na').exists())

    @override_settings(**NO_KEYS)
    def test_empty_keys_503(self):
        self._assert_503()

    @override_settings(LIQPAY_PUBLIC_KEY='your_liqpay_public_key', LIQPAY_PRIVATE_KEY='your_liqpay_private_key')
    def test_placeholder_keys_503(self):
        self._assert_503()

    @override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='off')
    def test_mode_off_503(self):
        self._assert_503()

    @override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='demo')
    def test_invalid_mode_503(self):
        self._assert_503()


@override_settings(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
class CheckoutModeTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=User.objects.create_user(email='mode@test.com', password='pass1234'))

    def _post(self):
        return self.client.post(CHECKOUT_URL, {'order_id': 'ord-m', 'amount': '10.00', 'currency': 'USD'},
                                format='json')

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_SANDBOX=False)
    def test_sandbox_mode_sends_sandbox_1(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIs(resp.data['sandbox'], True)
        self.assertEqual(_sent_params(resp)['sandbox'], 1)

    @override_settings(LIQPAY_MODE='real', LIQPAY_SANDBOX=True)
    def test_real_mode_sends_sandbox_0(self):
        resp = self._post()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIs(resp.data['sandbox'], False)
        self.assertEqual(_sent_params(resp)['sandbox'], 0)

    @override_settings(LIQPAY_MODE='auto', LIQPAY_SANDBOX=False)
    def test_auto_follows_liqpay_sandbox_flag(self):
        self.assertEqual(_sent_params(self._post())['sandbox'], 0)

    @override_settings(LIQPAY_MODE='auto', LIQPAY_SANDBOX=True)
    def test_auto_default_is_sandbox(self):
        self.assertEqual(_sent_params(self._post())['sandbox'], 1)


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
