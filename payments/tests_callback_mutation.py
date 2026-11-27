"""LiqPay callback (payments/views.py): тесты против выживших мутантов cosmic-ray (scripts/mutation.sh callback).

Сверка подписанного callback с заказом - строго по равенству: валюта/action «меньше» или «больше»
по алфавиту, сумма больше заказа - отказ (FAILED). Возврат в чужой валюте не переводит платёж в REVERSED.
Ответ LiqPay всегда {"ok": true, ...}; неожиданная ошибка декодирования - 400, а не 500.
"""
from unittest import mock

from django.test import override_settings
from rest_framework import status

from .models import Payment
from .providers import LiqPayProvider
from .tests_liqpay_security import KEYS, _Base, signed


@override_settings(**KEYS)
class CallbackStrictMatchTests(_Base):
    def _assert_failed(self, **override):
        resp = self.post(signed(self.payment, **override))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json(), {'ok': True, 'status': Payment.Status.FAILED})
        self.assertIsNone(self.promoted_until())

    def test_other_currency_refused_whatever_its_order(self):
        for currency in ('EUR', 'USD'):  # 'EUR' < 'UAH' < 'USD'
            with self.subTest(currency=currency):
                self._assert_failed(currency=currency)
                Payment.objects.filter(pk=self.payment.pk).update(status=Payment.Status.PENDING)

    def test_other_action_refused_whatever_its_order(self):
        for action in ('hold', 'subscribe'):  # 'hold' < 'pay' < 'subscribe'
            with self.subTest(action=action):
                self._assert_failed(action=action)
                Payment.objects.filter(pk=self.payment.pk).update(status=Payment.Status.PENDING)

    def test_amount_above_order_refused(self):
        self._assert_failed(amount=str(self.payment.amount + 1))

    def test_success_answers_ok_true(self):
        resp = self.post(signed(self.payment))
        self.assertEqual(resp.json(), {'ok': True, 'status': Payment.Status.COMPLETED})
        self.assertIsNotNone(self.promoted_until())


@override_settings(**KEYS)
class CallbackAfterCompletedTests(_Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.post(signed(self.payment)).status_code, status.HTTP_200_OK)
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_repeat_success_ignored_ok_true(self):
        resp = self.post(signed(self.payment))
        self.assertEqual(resp.json(), {'ok': True, 'status': Payment.Status.COMPLETED})

    def test_refund_in_other_currency_ignored(self):
        for currency in ('EUR', 'USD'):
            with self.subTest(currency=currency):
                resp = self.post(signed(self.payment, status_='reversed', currency=currency))
                self.assertEqual(resp.json(), {'ok': True, 'status': Payment.Status.COMPLETED})
                self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_refund_in_order_currency_reverses_ok_true(self):
        resp = self.post(signed(self.payment, status_='reversed'))
        self.assertEqual(resp.json(), {'ok': True, 'status': Payment.Status.REVERSED})


@override_settings(**KEYS)
class CallbackDecodeErrorTests(_Base):
    def test_unexpected_decode_error_is_400_invalid(self):
        with mock.patch.object(LiqPayProvider, 'decode_callback', side_effect=ValueError('broken base64')):
            resp = self.post(signed(self.payment))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json(), {'detail': 'invalid'})
        self.assertEqual(self.reload().status, Payment.Status.PENDING)
