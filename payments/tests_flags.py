"""PAYMENTS_ENABLED и callback LiqPay (задача 6.7, Q17): создание оплат закрыто флагом, callback открыт, подпись обязательна."""
import base64
import hashlib
import json
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from local_listings.models import PromotionTariff
from tests.factories import auth_client, make_local_listing, make_user

from .models import Payment

PUB, PRIV = 'test_pub', 'test_priv'
KEYS = dict(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='sandbox')
CHECKOUT = '/api/v1/payments/liqpay/checkout/'
CALLBACK = '/api/v1/payments/liqpay/callback/'
SECTION_OFF = dict(C2C_ENABLED=False, C2C_PUBLIC_POSTING_ENABLED=False)


def _signed(order_id, key=PRIV, status_='success'):
    data = base64.b64encode(json.dumps({'order_id': order_id, 'status': status_, 'payment_id': 7}).encode()).decode()
    sign = base64.b64encode(hashlib.sha1((key + data + key).encode()).digest()).decode()
    return {'data': data, 'signature': sign}


@override_settings(PAYMENTS_ENABLED=False, **KEYS)
class TestCreationClosedByFlag(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client = auth_client(self.user)

    def test_checkout_404_and_no_payment(self):
        resp = self.client.post(CHECKOUT, {'order_id': 'o-1', 'amount': '10.00', 'currency': 'USD'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Payment.objects.exists())

    def test_promote_404_and_no_payment(self):
        listing = make_local_listing(self.user)
        PromotionTariff.objects.create(code='t-top', name='top', type='top', price=Decimal('10'), currency='UAH')
        resp = self.client.post(f'/api/v1/local/listings/{listing.pk}/promote/', {'tariff': 't-top'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Payment.objects.exists())

    def test_site_settings_reports_payments_disabled(self):
        self.assertIs(APIClient().get('/api/v1/site-settings/').json()['payments_enabled'], False)

    @override_settings(PAYMENTS_ENABLED=True)
    def test_flag_on_checkout_creates_payment(self):
        resp = self.client.post(CHECKOUT, {'order_id': 'o-2', 'amount': '10.00', 'currency': 'USD'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Payment.objects.filter(order_id='o-2').exists())

    @override_settings(PAYMENTS_ENABLED=True)
    def test_flag_on_promote_creates_payment(self):
        listing = make_local_listing(self.user)
        PromotionTariff.objects.create(code='t-top', name='top', type='top', price=Decimal('10'), currency='UAH')
        resp = self.client.post(f'/api/v1/local/listings/{listing.pk}/promote/', {'tariff': 't-top'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.count(), 1)


@override_settings(PAYMENTS_ENABLED=False, **SECTION_OFF)
class TestCallbackAlwaysOpenButSigned(APITestCase):
    """Все флаги выключены: callback не 404, подпись решает."""

    def setUp(self):
        self.payment = Payment.objects.create(
            user=make_user(), order_id='cb-1', amount=Decimal('10.00'), currency='USD', description='t')

    @override_settings(**KEYS)
    def test_valid_signature_is_processed(self):
        resp = APIClient().post(CALLBACK, _signed('cb-1'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.COMPLETED)

    @override_settings(**KEYS)
    def test_wrong_signature_400_and_payment_untouched(self):
        resp = APIClient().post(CALLBACK, _signed('cb-1', key='other_key'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    @override_settings(**KEYS)
    def test_missing_signature_400(self):
        resp = APIClient().post(CALLBACK, {'data': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(LIQPAY_PUBLIC_KEY='', LIQPAY_PRIVATE_KEY='')
    def test_no_key_503_without_db_queries(self):
        # Подпись с пустым ключом подделывается кем угодно: без ключа платёж не трогаем и в БД не ходим.
        body = _signed('cb-1', key='')
        with self.assertNumQueries(0):
            resp = APIClient().post(CALLBACK, body, format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.json(), {'detail': 'Оплата не налаштована'})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)

    @override_settings(LIQPAY_PUBLIC_KEY='your_liqpay_public_key', LIQPAY_PRIVATE_KEY='your_liqpay_private_key')
    def test_placeholder_key_503(self):
        resp = APIClient().post(CALLBACK, _signed('cb-1', key='your_liqpay_private_key'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(LIQPAY_MODE='off', LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV)
    def test_mode_off_503_without_db_queries(self):
        with self.assertNumQueries(0):
            resp = APIClient().post(CALLBACK, _signed('cb-1'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(**KEYS)
    def test_signature_compared_with_compare_digest(self):
        with mock.patch('payments.liqpay_client.hmac.compare_digest', return_value=False) as compare:
            resp = APIClient().post(CALLBACK, _signed('cb-1'), format='json')
        compare.assert_called_once()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.PENDING)
