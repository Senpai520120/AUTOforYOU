"""Сервисы платежей (задача 1.15): URL для LiqPay только из SITE_URL и однократное применение эффекта оплаты."""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Payment

logger = logging.getLogger(__name__)

CALLBACK_PATH = '/api/v1/payments/liqpay/callback/'
RESULT_PATH = '/me'


def build_liqpay_urls(order_id: str) -> dict:
    """`server_url` и `result_url` для checkout. Только из settings.SITE_URL, значения клиента не принимаются (F5).

    `order_id` пока не входит в URL (страницы статуса оплаты нет, она в 4.1); параметр оставлен для неё.
    """
    base = str(getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    return {'server_url': f'{base}{CALLBACK_PATH}', 'result_url': f'{base}{RESULT_PATH}'}


def legacy_price_for(purpose: str):
    """Серверна ціна (amount, currency) для purpose старого checkout, або None.

    Зараз цін немає (Q13/Q14: listing_unlock і listing_vip не потрібні), тому будь-який purpose відхиляється 400.
    Ціна, коли з'явиться, береться з БД (тарифи в адмінці), а не з константи.
    """
    return None


def _apply_local_listing_promote(payment):
    """Застосувати ефект тарифу після успішної оплати просування."""
    if payment.purpose != payment.Purpose.LOCAL_LISTING_PROMOTE:
        return
    if not payment.local_listing or not payment.tariff:
        return

    from local_listings.models import LocalListing, PromotionTariff

    listing = payment.local_listing
    tariff = payment.tariff
    now = timezone.now()

    if tariff.type == PromotionTariff.TariffType.RENEW:
        base = max(listing.expires_at or now, now)
        listing.expires_at = base + timedelta(days=tariff.duration_days)
        listing.expiry_warned = False
        if listing.status == LocalListing.Status.EXPIRED:
            listing.status = LocalListing.Status.ACTIVE
        listing.save(update_fields=['expires_at', 'expiry_warned', 'status'])

    elif tariff.type == PromotionTariff.TariffType.BUMP:
        listing.bumped_at = now
        listing.save(update_fields=['bumped_at'])

    elif tariff.type == PromotionTariff.TariffType.TOP:
        base = max(listing.promoted_until or now, now)
        listing.promoted_until = base + timedelta(days=tariff.duration_days)
        listing.save(update_fields=['promoted_until'])

    logger.info('Tariff %s applied to listing %s', tariff.code, listing.pk)


@transaction.atomic
def apply_payment_effect(payment) -> bool:
    """Применить эффект оплаченного платежа ровно один раз (F3).

    Строка платежа блокируется `select_for_update`, повторный вызов видит `applied_at` и ничего не делает.
    Возвращает True, если эффект применён сейчас.
    """
    locked = Payment.objects.select_for_update().select_related('listing', 'local_listing', 'tariff').get(pk=payment.pk)
    if locked.status != Payment.Status.COMPLETED or locked.applied_at is not None:
        return False
    locked.unlock_listing()
    _apply_local_listing_promote(locked)
    locked.applied_at = timezone.now()
    locked.save(update_fields=['applied_at', 'updated_at'])
    payment.applied_at = locked.applied_at
    return True
