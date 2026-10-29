"""Задача 1.15: закрытие находок аудита 2026-10-25 по LiqPay (F1-F6, F12, F14). Сеть не нужна, LiqPay не вызывается."""
import base64
import hashlib
import importlib.util
import json
import os
import sys
import threading
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from local_listings.models import PromotionTariff
from tests.factories import auth_client, make_listing, make_local_listing, make_user, make_vehicle

from .liqpay_client import LiqPayClient, LiqPayNotConfigured
from .models import Payment
from .providers import LiqPayProvider
from .services import apply_payment_effect, build_liqpay_urls

PUB, PRIV = 'test-only-public-key', 'test-only-private-key'
KEYS = dict(LIQPAY_PUBLIC_KEY=PUB, LIQPAY_PRIVATE_KEY=PRIV, LIQPAY_MODE='auto', LIQPAY_SANDBOX=False,
            PAYMENTS_ENABLED=True, SITE_URL='https://site.example.test')
CHECKOUT = '/api/v1/payments/liqpay/checkout/'
CALLBACK = '/api/v1/payments/liqpay/callback/'
UNAVAILABLE = 'Оплата не налаштована'


def signed(payment, status_='success', key=PRIV, **override):
    """Подписанный callback LiqPay с полями, как у настоящего (amount/currency/action)."""
    payload = {'order_id': payment.order_id, 'status': status_, 'payment_id': 7, 'action': 'pay',
               'amount': str(payment.amount), 'currency': payment.currency}
    payload.update(override)
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    sign = base64.b64encode(hashlib.sha1((key + data + key).encode()).digest()).decode()
    return {'data': data, 'signature': sign}


def make_tariff(code='sec-top', type_='top', price='99.00', days=7):
    tariff, _ = PromotionTariff.objects.update_or_create(
        code=code, defaults=dict(name=code, type=type_, price=Decimal(price), currency='UAH', duration_days=days))
    return tariff


def make_payment(owner, listing, tariff, order_id='sec-1'):
    return Payment.objects.create(
        user=owner, local_listing=listing, tariff=tariff, order_id=order_id, amount=tariff.price,
        currency=tariff.currency, purpose=Payment.Purpose.LOCAL_LISTING_PROMOTE)


class _Base(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.listing = make_local_listing(self.owner)
        self.tariff = make_tariff()
        self.payment = make_payment(self.owner, self.listing, self.tariff)
        self.anon = APIClient()

    def post(self, body):
        return self.anon.post(CALLBACK, body, format='json')

    def promoted_until(self):
        self.listing.refresh_from_db()
        return self.listing.promoted_until

    def reload(self):
        self.payment.refresh_from_db()
        return self.payment


# ─── F1 ──────────────────────────────────────────────────────────────────────

class F1NotConfiguredTests(_Base):
    def _assert_closed(self, body):
        resp = self.post(body)
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.json(), {'detail': UNAVAILABLE})
        self.assertEqual(self.reload().status, Payment.Status.PENDING)
        self.assertIsNone(self.promoted_until())

    @override_settings(**{**KEYS, 'LIQPAY_PRIVATE_KEY': '', 'LIQPAY_PUBLIC_KEY': ''})
    def test_empty_key_forged_callback_503_and_nothing_changes(self):
        self._assert_closed(signed(self.payment, key=''))

    @override_settings(**{**KEYS, 'LIQPAY_PRIVATE_KEY': 'your_liqpay_private_key',
                          'LIQPAY_PUBLIC_KEY': 'your_liqpay_public_key'})
    def test_placeholder_key_forged_callback_503(self):
        self._assert_closed(signed(self.payment, key='your_liqpay_private_key'))

    @override_settings(**{**KEYS, 'LIQPAY_MODE': 'off'})
    def test_mode_off_503(self):
        self._assert_closed(signed(self.payment))

    @override_settings(**KEYS)
    def test_view_maps_decode_not_configured_to_503(self):
        with mock.patch.object(LiqPayProvider, 'decode_callback', side_effect=LiqPayNotConfigured('x')):
            self._assert_closed(signed(self.payment))

    def test_client_decode_with_empty_key_raises(self):
        body = signed(self.payment, key='')
        with self.assertRaisesMessage(LiqPayNotConfigured, 'LIQPAY_PRIVATE_KEY'):
            LiqPayClient(public_key='', private_key='').decode_callback(body['data'], body['signature'])

    @override_settings(**{**KEYS, 'LIQPAY_MODE': 'off'})
    def test_provider_decode_in_mode_off_raises(self):
        body = signed(self.payment)
        with self.assertRaises(LiqPayNotConfigured):
            LiqPayProvider().decode_callback(body['data'], body['signature'])

    @override_settings(**{**KEYS, 'LIQPAY_PRIVATE_KEY': '', 'LIQPAY_PUBLIC_KEY': ''})
    def test_promote_with_empty_key_503_no_payment(self):
        Payment.objects.all().delete()
        resp = auth_client(self.owner).post(
            f'/api/v1/local/listings/{self.listing.pk}/promote/', {'tariff': self.tariff.code}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(Payment.objects.exists())


# ─── F2 ──────────────────────────────────────────────────────────────────────

@override_settings(**KEYS)
class F2LegacyCheckoutTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user()
        self.own = make_listing(make_vehicle(), self.user, status='in_transit')
        self.foreign = make_listing(make_vehicle(), self.other, status='in_transit')
        self.client = auth_client(self.user)

    def body(self, listing, **extra):
        return {'listing_id': listing.pk, 'purpose': 'listing_unlock', **extra}

    def test_disabled_by_default_404_no_payment(self):
        resp = self.client.post(CHECKOUT, self.body(self.own), format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Payment.objects.exists())

    @override_settings(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
    def test_anonymous_401(self):
        resp = APIClient().post(CHECKOUT, self.body(self.own), format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
    def test_foreign_listing_404_no_payment(self):
        resp = self.client.post(CHECKOUT, self.body(self.foreign), format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Payment.objects.exists())

    @override_settings(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
    def test_purpose_without_server_price_400_even_with_client_amount(self):
        resp = self.client.post(CHECKOUT, self.body(self.own, amount='0.01', currency='UAH'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('purpose', resp.json())
        self.assertFalse(Payment.objects.exists())

    @override_settings(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
    def test_client_amount_currency_and_urls_are_ignored(self):
        with mock.patch('payments.views.legacy_price_for', return_value=(Decimal('50.00'), 'UAH')):
            resp = self.client.post(CHECKOUT, self.body(
                self.own, amount='0.01', currency='USD', order_id='client-chosen',
                server_url='https://evil.test/cb', result_url='https://evil.test/r'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        payment = Payment.objects.get()
        self.assertEqual((payment.amount, payment.currency), (Decimal('50.00'), 'UAH'))
        self.assertNotEqual(payment.order_id, 'client-chosen')
        self.assertTrue(payment.order_id.startswith('legacy-'))
        params = json.loads(base64.b64decode(resp.json()['form_data']['data']))
        self.assertEqual(params['amount'], '50.00')
        self.assertEqual(params['currency'], 'UAH')
        self.assertEqual(params['server_url'], 'https://site.example.test/api/v1/payments/liqpay/callback/')
        self.assertNotIn('evil.test', params['result_url'])

    @override_settings(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
    def test_unknown_purpose_400(self):
        # Даже если бы цена нашлась, неизвестный purpose отсекает сам сериализатор.
        with mock.patch('payments.views.legacy_price_for', return_value=(Decimal('5.00'), 'UAH')):
            resp = self.client.post(CHECKOUT, self.body(self.own, purpose='steal_everything'), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('purpose', resp.json())
        self.assertFalse(Payment.objects.exists())

    @override_settings(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
    def test_existing_order_id_does_not_leak(self):
        Payment.objects.create(order_id='taken-1', amount=1)
        resp = self.client.post(CHECKOUT, self.body(self.own, order_id='taken-1'), format='json')
        self.assertNotIn('order_id', resp.json())

    def test_unlock_foreign_listing_does_not_change_status(self):
        payment = Payment.objects.create(user=self.user, listing=self.foreign, order_id='u-1', amount=1,
                                         status=Payment.Status.COMPLETED)
        self.assertIs(payment.unlock_listing(), False)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.status, 'in_transit')

    def test_unlock_own_in_transit_listing_works(self):
        payment = Payment.objects.create(user=self.user, listing=self.own, order_id='u-2', amount=1,
                                         status=Payment.Status.COMPLETED)
        self.assertIs(payment.unlock_listing(), True)
        self.own.refresh_from_db()
        self.assertEqual(self.own.status, 'in_stock')

    def test_unlock_sold_listing_not_reopened(self):
        sold = make_listing(make_vehicle(), self.user, status='sold')
        payment = Payment.objects.create(user=self.user, listing=sold, order_id='u-3', amount=1,
                                         status=Payment.Status.COMPLETED)
        self.assertIs(payment.unlock_listing(), False)
        sold.refresh_from_db()
        self.assertEqual(sold.status, 'sold')


@override_settings(**KEYS)
class F2PromotePriceTests(TestCase):
    def test_client_amount_ignored_payment_amount_is_tariff_price(self):
        owner = make_user()
        listing = make_local_listing(owner)
        tariff = make_tariff()
        resp = auth_client(owner).post(
            f'/api/v1/local/listings/{listing.pk}/promote/',
            {'tariff': tariff.code, 'amount': '0.01', 'currency': 'USD'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get()
        self.assertEqual((payment.amount, payment.currency), (tariff.price, tariff.currency))


# ─── F3 ──────────────────────────────────────────────────────────────────────

@override_settings(**KEYS)
class F3TransitionTests(_Base):
    def test_success_failure_success_applies_top_once(self):
        before = timezone.now()
        self.assertEqual(self.post(signed(self.payment)).status_code, status.HTTP_200_OK)
        first = self.promoted_until()
        self.post(signed(self.payment, 'failure'))
        self.post(signed(self.payment))
        self.assertEqual(self.promoted_until(), first)
        self.assertLess(first - before, timedelta(days=self.tariff.duration_days, minutes=1))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_duplicate_success_keeps_applied_at(self):
        self.post(signed(self.payment))
        applied = self.reload().applied_at
        self.assertIsNotNone(applied)
        self.post(signed(self.payment))
        self.assertEqual(self.reload().applied_at, applied)

    def test_completed_to_failed_does_not_change_status(self):
        self.post(signed(self.payment))
        resp = self.post(signed(self.payment, 'failure'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_completed_to_pending_does_not_change_status(self):
        self.post(signed(self.payment))
        self.post(signed(self.payment, 'processing'))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_failed_then_success_completes(self):
        self.post(signed(self.payment, 'failure'))
        self.post(signed(self.payment))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_apply_payment_effect_is_idempotent(self):
        self.payment.status = Payment.Status.COMPLETED
        self.payment.save()
        self.assertIs(apply_payment_effect(self.payment), True)
        first = self.promoted_until()
        self.assertIs(apply_payment_effect(self.payment), False)
        self.assertEqual(self.promoted_until(), first)

    def test_effect_not_applied_for_pending_payment(self):
        self.assertIs(apply_payment_effect(self.payment), False)
        self.assertIsNone(self.promoted_until())

    def test_reversed_after_completed_changes_status_only(self):
        self.post(signed(self.payment))
        first = self.promoted_until()
        self.post(signed(self.payment, 'reversed'))
        self.assertEqual(self.reload().status, Payment.Status.REVERSED)
        self.assertEqual(self.promoted_until(), first)

    def test_reversed_is_final(self):
        self.post(signed(self.payment))
        self.post(signed(self.payment, 'reversed'))
        self.post(signed(self.payment))
        self.assertEqual(self.reload().status, Payment.Status.REVERSED)


@override_settings(**KEYS)
class F3ConcurrentCallbackTests(TransactionTestCase):
    """Два одновременных success: эффект применён один раз (на PostgreSQL; на sqlite - последовательный сценарий)."""

    def setUp(self):
        self.owner = make_user()
        self.listing = make_local_listing(self.owner)
        self.payment = make_payment(self.owner, self.listing, make_tariff(), 'conc-1')

    def _fire(self, results):
        try:
            results.append(APIClient().post(CALLBACK, signed(self.payment), format='json').status_code)
        finally:
            connections.close_all()

    def test_two_callbacks_apply_effect_once(self):
        results = []
        if connection.vendor == 'postgresql':
            threads = [threading.Thread(target=self._fire, args=(results,)) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        else:  # sqlite: select_for_update не поддерживается, проверяем последовательный повтор
            for _ in range(2):
                results.append(APIClient().post(CALLBACK, signed(self.payment), format='json').status_code)
        self.assertEqual(results, [status.HTTP_200_OK, status.HTTP_200_OK])
        self.listing.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.Status.COMPLETED)
        limit = timezone.now() + timedelta(days=self.payment.tariff.duration_days, minutes=1)
        self.assertLess(self.listing.promoted_until, limit)


# ─── F4 ──────────────────────────────────────────────────────────────────────

@override_settings(**KEYS)
class F4MismatchTests(_Base):
    def _assert_failed(self, body):
        with self.assertLogs('payments.views', level='WARNING') as logs:
            resp = self.post(body)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        payment = self.reload()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIsNotNone(payment.liqpay_raw)
        self.assertIsNone(payment.applied_at)
        self.assertIsNone(self.promoted_until())
        self.assertNotIn(self.payment.order_id, ' '.join(logs.output))

    def test_smaller_amount(self):
        self._assert_failed(signed(self.payment, amount='0.01'))

    def test_other_currency(self):
        self._assert_failed(signed(self.payment, currency='USD'))

    def test_action_subscribe(self):
        self._assert_failed(signed(self.payment, action='subscribe'))

    def test_missing_amount(self):
        self._assert_failed(signed(self.payment, amount=None))

    def test_garbage_amount(self):
        self._assert_failed(signed(self.payment, amount='abc'))

    def test_equal_amount_in_other_notation_passes(self):
        self.post(signed(self.payment, amount=99))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_amount_notations_accepted(self):
        for amount in (99.0, '99.00', '99'):
            with self.subTest(amount=amount):
                Payment.objects.filter(pk=self.payment.pk).update(status='pending', applied_at=None)
                self.post(signed(self.payment, amount=amount))
                self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_cent_price_accepted_and_one_cent_less_rejected(self):
        Payment.objects.filter(pk=self.payment.pk).update(amount=Decimal('99.99'))
        self.payment.refresh_from_db()
        self.post(signed(self.payment, amount=99.98))
        self.assertEqual(self.reload().status, Payment.Status.FAILED)
        Payment.objects.filter(pk=self.payment.pk).update(status='pending')
        self.post(signed(self.payment, amount=99.99))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    def test_mismatch_does_not_downgrade_completed(self):
        self.post(signed(self.payment))
        self.post(signed(self.payment, amount='0.01'))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)


# ─── F5 ──────────────────────────────────────────────────────────────────────

@override_settings(**KEYS)
class F5UrlTests(TestCase):
    def test_build_urls_from_site_url(self):
        urls = build_liqpay_urls('o-1')
        self.assertEqual(urls['server_url'], 'https://site.example.test/api/v1/payments/liqpay/callback/')
        self.assertEqual(urls['result_url'], 'https://site.example.test/me')

    @override_settings(SITE_URL='https://other.example.test/')
    def test_trailing_slash_stripped(self):
        self.assertEqual(build_liqpay_urls('o-1')['server_url'],
                         'https://other.example.test/api/v1/payments/liqpay/callback/')

    def test_promote_ignores_client_urls(self):
        owner = make_user()
        listing = make_local_listing(owner)
        tariff = make_tariff()
        resp = auth_client(owner).post(
            f'/api/v1/local/listings/{listing.pk}/promote/',
            {'tariff': tariff.code, 'server_url': 'https://evil.test/cb', 'result_url': 'https://evil.test/r'},
            format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        params = json.loads(base64.b64decode(resp.json()['form_data']['data']))
        self.assertEqual(params['server_url'], 'https://site.example.test/api/v1/payments/liqpay/callback/')
        self.assertEqual(params['result_url'], 'https://site.example.test/me')


# ─── F6 ──────────────────────────────────────────────────────────────────────

class F6SandboxTests(_Base):
    @override_settings(**{**KEYS, 'LIQPAY_SANDBOX': False})
    def test_sandbox_status_rejected_when_flag_false(self):
        with self.assertLogs('payments.providers', level='WARNING'):
            resp = self.post(signed(self.payment, 'sandbox'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.reload().status, Payment.Status.FAILED)
        self.assertIsNone(self.promoted_until())

    @override_settings(**{**KEYS, 'LIQPAY_SANDBOX': True})
    def test_sandbox_status_counts_when_flag_true(self):
        self.post(signed(self.payment, 'sandbox'))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)
        self.assertIsNotNone(self.promoted_until())

    @override_settings(**{**KEYS, 'LIQPAY_MODE': 'sandbox', 'LIQPAY_SANDBOX': False})
    def test_sandbox_status_counts_in_explicit_sandbox_mode(self):
        self.post(signed(self.payment, 'sandbox'))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)

    @override_settings(**{**KEYS, 'LIQPAY_MODE': 'real', 'LIQPAY_SANDBOX': True})
    def test_sandbox_status_rejected_in_real_mode_even_if_flag_true(self):
        self.post(signed(self.payment, 'sandbox'))
        self.assertEqual(self.reload().status, Payment.Status.FAILED)

    @override_settings(**{**KEYS, 'LIQPAY_SANDBOX': False})
    def test_real_success_still_counts_when_flag_false(self):
        self.post(signed(self.payment))
        self.assertEqual(self.reload().status, Payment.Status.COMPLETED)


class F6SettingsDefaultTests(SimpleTestCase):
    def _load(self, **env):
        spec = importlib.util.spec_from_file_location('settings_probe_1_15', Path(settings.BASE_DIR, 'core', 'settings.py'))
        module = importlib.util.module_from_spec(spec)
        clean = {k: v for k, v in os.environ.items() if k not in ('LIQPAY_SANDBOX', 'PAYMENTS_LEGACY_CHECKOUT_ENABLED')}
        clean.update(env)
        clean.update(DEBUG='true')
        with (
            mock.patch.dict(os.environ, clean, clear=True),
            mock.patch.object(sys, 'argv', ['manage.py', 'check']),
            mock.patch('dotenv.load_dotenv'),  # локальный .env не должен влиять на проверку дефолтов
        ):
            spec.loader.exec_module(module)
        return module

    def test_defaults_are_false(self):
        module = self._load()
        self.assertIs(module.LIQPAY_SANDBOX, False)
        self.assertIs(module.PAYMENTS_LEGACY_CHECKOUT_ENABLED, False)

    def test_explicit_true_is_read(self):
        module = self._load(LIQPAY_SANDBOX='true', PAYMENTS_LEGACY_CHECKOUT_ENABLED='true')
        self.assertIs(module.LIQPAY_SANDBOX, True)
        self.assertIs(module.PAYMENTS_LEGACY_CHECKOUT_ENABLED, True)


# ─── F12 / ответы / F14 ──────────────────────────────────────────────────────

@override_settings(**KEYS)
class ResponseAndSignatureTests(_Base):
    def test_last_char_differs_400_and_no_order_id_in_body(self):
        body = signed(self.payment)
        body['signature'] = body['signature'][:-1] + ('A' if body['signature'][-1] != 'A' else 'B')
        resp = self.post(body)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json(), {'detail': 'invalid'})
        self.assertNotIn(self.payment.order_id, resp.content.decode())
        self.assertEqual(self.reload().status, Payment.Status.PENDING)

    def test_compare_digest_used(self):
        with mock.patch('payments.liqpay_client.hmac.compare_digest', return_value=False) as compare:
            resp = self.post(signed(self.payment))
        compare.assert_called_once()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_signature_400_same_body(self):
        resp = self.post({'data': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json(), {'detail': 'invalid'})

    def test_unknown_order_id_200_ok_false_without_order_id(self):
        ghost = Payment(order_id='ghost-order-77', amount=Decimal('1.00'), currency='UAH')
        resp = self.post(signed(ghost))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json(), {'ok': False})
        self.assertNotIn('ghost-order-77', resp.content.decode())


class AppliedAtMigrationTests(TransactionTestCase):
    """0005: платёж, бывший completed, получает applied_at = updated_at; остальные не затронуты."""

    def test_backfill_sets_applied_at_for_completed_only(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('payments', '0004_payment_applied_at')])
        old_apps = executor.loader.project_state([('payments', '0004_payment_applied_at')]).apps
        OldPayment = old_apps.get_model('payments', 'Payment')
        done = OldPayment.objects.create(order_id='mig-done', amount=1, status='completed')
        wait = OldPayment.objects.create(order_id='mig-wait', amount=1, status='pending')
        stamp = OldPayment.objects.get(pk=done.pk).updated_at

        executor = MigrationExecutor(connection)
        executor.migrate([('payments', '0005_backfill_applied_at')])
        done.refresh_from_db()
        wait.refresh_from_db()
        self.assertEqual(Payment.objects.get(pk=done.pk).applied_at, stamp)
        self.assertIsNone(Payment.objects.get(pk=wait.pk).applied_at)

    @override_settings(**KEYS)
    def test_repeated_success_after_backfill_applies_nothing(self):
        owner = make_user()
        listing = make_local_listing(owner)
        payment = make_payment(owner, listing, make_tariff(), 'mig-2')
        Payment.objects.filter(pk=payment.pk).update(status='completed', applied_at=timezone.now())
        APIClient().post(CALLBACK, signed(payment), format='json')
        listing.refresh_from_db()
        self.assertIsNone(listing.promoted_until)
