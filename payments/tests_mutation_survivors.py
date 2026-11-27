"""payments: тесты против выживших мутантов cosmic-ray (scripts/mutation.sh payments).

services: эффект тарифа (срок продления/ТОП от правильной базы, только нужное поле, реактивация
только истёкшего), применение только завершённой оплаты, откат при ошибке.
providers: матрица режимов LiqPay (LIQPAY_MODE x ключи x LIQPAY_SANDBOX), засчитывание статуса sandbox.
"""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from integrations.base import MODE_DEMO, MODE_OFF, MODE_REAL
from local_listings.models import LocalListing, PromotionTariff
from payments.models import Payment
from payments.providers import LiqPayProvider, unavailable_response
from payments.services import _apply_local_listing_promote, apply_payment_effect
from tests.factories import make_listing, make_local_listing, make_user, make_vehicle

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=dt_timezone.utc)


def _tariff(type_, days=10):
    tariff, _ = PromotionTariff.objects.update_or_create(
        code=f'mut-{type_}', defaults=dict(name=type_, type=type_, price=Decimal('50'), currency='UAH',
                                           duration_days=days))
    return tariff


@patch('payments.services.timezone.now', return_value=NOW)
class PromoteEffectTests(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.listing = make_local_listing(self.owner)

    def _pay(self, tariff, status=Payment.Status.COMPLETED, purpose=Payment.Purpose.LOCAL_LISTING_PROMOTE):
        return Payment.objects.create(user=self.owner, local_listing=self.listing, tariff=tariff, order_id=f'm-{tariff.code}',
                                      amount=tariff.price, currency='UAH', purpose=purpose, status=status)

    def _set(self, **fields):
        LocalListing.objects.filter(pk=self.listing.pk).update(**fields)
        self.listing.refresh_from_db()

    def test_renew_extends_from_future_expiry(self, _now):
        self._set(expires_at=NOW + timedelta(days=3), expiry_warned=True, promoted_until=None, bumped_at=None)
        self.assertIs(apply_payment_effect(self._pay(_tariff('renew', 10))), True)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.expires_at, NOW + timedelta(days=13))
        self.assertIs(self.listing.expiry_warned, False)
        self.assertEqual((self.listing.promoted_until, self.listing.bumped_at), (None, None))

    def test_renew_from_now_when_expired_or_empty(self, _now):
        for expires in (None, NOW - timedelta(days=5)):
            with self.subTest(expires=expires):
                self._set(expires_at=expires)
                _apply_local_listing_promote(self._pay(_tariff('renew', 10)))
                self.listing.refresh_from_db()
                self.assertEqual(self.listing.expires_at, NOW + timedelta(days=10))
                Payment.objects.all().delete()

    def test_renew_reactivates_only_expired(self, _now):
        cases = [(LocalListing.Status.EXPIRED, LocalListing.Status.ACTIVE),
                 (LocalListing.Status.SOLD, LocalListing.Status.SOLD),
                 (LocalListing.Status.DRAFT, LocalListing.Status.DRAFT),
                 (LocalListing.Status.ACTIVE, LocalListing.Status.ACTIVE)]
        for before, after in cases:
            with self.subTest(before=before):
                self._set(status=before)
                _apply_local_listing_promote(self._pay(_tariff('renew')))
                self.listing.refresh_from_db()
                self.assertEqual(self.listing.status, after)
                Payment.objects.all().delete()

    def test_bump_only_sets_bumped_at(self, _now):
        expires = NOW + timedelta(days=3)
        self._set(expires_at=expires, promoted_until=None, bumped_at=None)
        apply_payment_effect(self._pay(_tariff('bump')))
        self.listing.refresh_from_db()
        self.assertEqual((self.listing.bumped_at, self.listing.expires_at, self.listing.promoted_until),
                         (NOW, expires, None))

    def test_top_extends_promotion_from_future_end(self, _now):
        expires = NOW + timedelta(days=3)
        self._set(expires_at=expires, promoted_until=NOW + timedelta(days=2), bumped_at=None)
        apply_payment_effect(self._pay(_tariff('top', 7)))
        self.listing.refresh_from_db()
        self.assertEqual((self.listing.promoted_until, self.listing.expires_at, self.listing.bumped_at),
                         (NOW + timedelta(days=9), expires, None))

    def test_not_completed_payment_is_not_applied(self, _now):
        for status in (Payment.Status.PENDING, Payment.Status.FAILED, Payment.Status.REVERSED):
            with self.subTest(status=status):
                self._set(promoted_until=None)
                payment = self._pay(_tariff('top'), status=status)
                self.assertIs(apply_payment_effect(payment), False)
                self.listing.refresh_from_db()
                self.assertIsNone(self.listing.promoted_until)
                payment.delete()

    def test_other_purpose_applies_without_touching_listing(self, _now):
        self._set(promoted_until=None)
        payment = self._pay(_tariff('top'), purpose=Payment.Purpose.OTHER)
        self.assertIs(apply_payment_effect(payment), True)
        self.listing.refresh_from_db()
        self.assertIsNone(self.listing.promoted_until)
        self.assertIsNotNone(Payment.objects.get(pk=payment.pk).applied_at)

    def test_other_purpose_without_listing_or_tariff_is_applied(self, _now):
        payment = Payment.objects.create(user=self.owner, order_id='m-other', amount=1, currency='UAH',
                                         purpose=Payment.Purpose.OTHER, status=Payment.Status.COMPLETED)
        self.assertIs(apply_payment_effect(payment), True)

    def test_unlock_purpose_ignores_attached_tariff(self, _now):
        self._set(promoted_until=None)
        payment = self._pay(_tariff('top'), purpose=Payment.Purpose.LISTING_UNLOCK)
        self.assertIs(_apply_local_listing_promote(payment), True)
        self.listing.refresh_from_db()
        self.assertIsNone(self.listing.promoted_until)

    def test_missing_tariff_is_not_applied(self, _now):
        payment = self._pay(_tariff('top'))
        payment.tariff = None
        self.assertIs(_apply_local_listing_promote(payment), False)

    def test_failed_effect_leaves_payment_unapplied(self, _now):
        payment = self._pay(_tariff('top'))
        with patch('payments.services._apply_local_listing_promote', return_value=False):
            self.assertIs(apply_payment_effect(payment), False)
        self.assertIsNone(Payment.objects.get(pk=payment.pk).applied_at)

    def test_error_rolls_back_unlock(self, _now):
        listing = make_listing(make_vehicle(), self.owner, status='in_transit')
        payment = Payment.objects.create(user=self.owner, listing=listing, order_id='m-unlock', amount=1,
                                         currency='UAH', purpose=Payment.Purpose.LISTING_UNLOCK,
                                         status=Payment.Status.COMPLETED)
        with patch('payments.services._apply_local_listing_promote', side_effect=RuntimeError('boom')):
            with self.assertRaisesMessage(RuntimeError, 'boom'):
                apply_payment_effect(payment)
        listing.refresh_from_db()
        self.assertEqual(listing.status, 'in_transit')


REAL_KEYS = dict(LIQPAY_PUBLIC_KEY='i000000000001', LIQPAY_PRIVATE_KEY='real-private-key-123456')
SANDBOX_KEYS = dict(LIQPAY_PUBLIC_KEY='sandbox_i000000001', LIQPAY_PRIVATE_KEY='sandbox-private-key-1234')
NO_KEYS = dict(LIQPAY_PUBLIC_KEY='', LIQPAY_PRIVATE_KEY='')


class LiqPayModeMatrixTests(SimpleTestCase):
    """(LIQPAY_MODE, ключи, LIQPAY_SANDBOX) -> (режим, налаштовано, valid)."""
    CASES = [
        ('auto', REAL_KEYS, False, MODE_REAL, True, True),
        ('auto', SANDBOX_KEYS, True, MODE_DEMO, True, True),
        ('auto', NO_KEYS, False, MODE_OFF, False, True),
        ('real', REAL_KEYS, False, MODE_REAL, True, True),
        ('real', SANDBOX_KEYS, False, MODE_REAL, False, True),  # боевой режим с sandbox-ключом
        ('real', NO_KEYS, False, MODE_REAL, False, True),
        ('sandbox', SANDBOX_KEYS, False, MODE_DEMO, True, True),
        ('sandbox', NO_KEYS, False, MODE_DEMO, False, True),
        ('off', REAL_KEYS, False, MODE_OFF, False, True),
        ('bogus', REAL_KEYS, False, MODE_OFF, False, False),
    ]

    def test_resolution_matrix(self):
        for mode, keys, sandbox_flag, exp_mode, exp_configured, exp_valid in self.CASES:
            with self.subTest(mode=mode, keys=keys['LIQPAY_PUBLIC_KEY'][:8], sandbox=sandbox_flag):
                with override_settings(LIQPAY_MODE=mode, LIQPAY_SANDBOX=sandbox_flag, **keys):
                    res = LiqPayProvider().resolution()
                self.assertEqual((res.mode, res.configured, res.valid), (exp_mode, exp_configured, exp_valid))

    @override_settings(LIQPAY_MODE='auto', **REAL_KEYS)
    def test_auto_without_sandbox_setting_is_real(self):
        from django.conf import settings
        with self.settings():
            del settings.LIQPAY_SANDBOX
            self.assertEqual(LiqPayProvider().resolution().mode, MODE_REAL)

    def test_is_sandbox_false_only_for_configured_real(self):
        for mode, keys, expected in (('real', REAL_KEYS, False), ('sandbox', SANDBOX_KEYS, True),
                                     ('real', NO_KEYS, True), ('off', REAL_KEYS, True)):
            with self.subTest(mode=mode), override_settings(LIQPAY_MODE=mode, LIQPAY_SANDBOX=False, **keys):
                self.assertIs(LiqPayProvider().is_sandbox, expected)

    def test_sandbox_status_counts_only_in_sandbox_mode(self):
        for mode, keys, expected in (('sandbox', SANDBOX_KEYS, 'completed'), ('real', REAL_KEYS, 'failed'),
                                     ('sandbox', NO_KEYS, 'failed')):
            with self.subTest(mode=mode), override_settings(LIQPAY_MODE=mode, LIQPAY_SANDBOX=False, **keys):
                self.assertEqual(LiqPayProvider().map_status('sandbox'), expected)
                self.assertEqual(LiqPayProvider().map_status('success'), 'completed')

    def test_status_shows_sandbox_only_for_configured_sandbox(self):
        with override_settings(LIQPAY_MODE='sandbox', LIQPAY_SANDBOX=False, **SANDBOX_KEYS):
            self.assertEqual(LiqPayProvider().status().mode_display, 'sandbox')
        with override_settings(LIQPAY_MODE='real', LIQPAY_SANDBOX=False, **REAL_KEYS):
            self.assertNotEqual(LiqPayProvider().status().mode_display, 'sandbox')

    def test_unavailable_response_says_not_configured(self):
        response = unavailable_response()
        self.assertEqual(response.status_code, 503)
        self.assertIs(response.data['configured'], False)
