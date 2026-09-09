"""
Валідація вхідних даних чекауту.

Раніше в'ю читала поля прямо з request.data: нечислова сума давала 500,
неіснуючий листинг мовчки створював платіж у нікуди.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Payment

User = get_user_model()

CHECKOUT_URL = '/api/v1/payments/liqpay/checkout/'


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
