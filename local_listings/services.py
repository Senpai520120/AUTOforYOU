"""
Сервісний шар для модерації місцевих оголошень.

Суттєві поля (редагування → ремодерація):
  make, model, year, price, currency, description
Несуттєві (правка без ремодерації):
  price_type, contact_phone, mileage_km, engine_cc,
  fuel_type, transmission, body_type, condition, region, city
"""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from audit.models import AuditAction
from audit.services import log_action

from integrations.email import send_email

from .models import LocalListing

# Поля, редагування яких повертає active-оголошення на pending (ремодерація)
# currency - тоже: 15000 UAH -> 15000 USD меняет цену в ~40 раз (ревью 4.2).
SUBSTANTIVE_FIELDS = frozenset({'make', 'model', 'year', 'price', 'currency', 'description'})


def _normalized(field, value):
    if value is None:
        return None
    if field == 'price':
        return Decimal(str(value))
    if isinstance(value, str):
        return value.strip()
    return value


def is_substantive_change(instance: LocalListing, validated_data: dict) -> bool:
    """Существенная правка - значение поля из SUBSTANTIVE_FIELDS реально изменилось (10-Q3).

    Сравниваются значения, а не наличие ключей: форма может прислать поле с тем же значением
    (цена `15000` и `15000.00`, текст с пробелами по краям).
    """
    return any(
        _normalized(field, validated_data[field]) != _normalized(field, getattr(instance, field))
        for field in SUBSTANTIVE_FIELDS if field in validated_data
    )


def _lock_unchanged(listing: LocalListing):
    """Строка под блокировкой; None, если статус изменился с момента выборки (гонка с block_user, ревью 1.13)."""
    fresh = LocalListing.objects.select_for_update().select_related('owner').get(pk=listing.pk)
    return None if fresh.status != listing.status else fresh


def approve_listing(listing: LocalListing, admin_user, request=None) -> LocalListing:
    """Перевести оголошення в active + зафіксувати модератора + журнал аудиту + повідомити власника.

    Ничего не делает, если статус изменился параллельно или владелец заблокирован.
    """
    with transaction.atomic():
        fresh = _lock_unchanged(listing)
        if fresh is None or fresh.owner.is_banned:
            return listing
        before = {'status': fresh.status}
        listing.status = LocalListing.Status.ACTIVE
        listing.moderated_by = admin_user
        listing.moderated_at = timezone.now()
        listing.rejection_reason = ''
        listing.save(update_fields=['status', 'moderated_by', 'moderated_at', 'rejection_reason'])
        log_action(
            admin_user, AuditAction.LISTING_APPROVE, listing, request=request,
            before=before, after={'status': listing.status},
        )
    _notify_owner(listing, approved=True)
    return listing


def reject_listing(listing: LocalListing, admin_user, reason: str = '', request=None) -> LocalListing:
    """Відхилити оголошення, зберегти причину, журнал аудиту, повідомити власника.

    Ничего не делает, если статус изменился параллельно.
    """
    with transaction.atomic():
        if _lock_unchanged(listing) is None:
            return listing
        before = {'status': listing.status}
        listing.status = LocalListing.Status.REJECTED
        listing.moderated_by = admin_user
        listing.moderated_at = timezone.now()
        listing.rejection_reason = reason or 'Не відповідає правилам розміщення.'
        listing.save(update_fields=['status', 'moderated_by', 'moderated_at', 'rejection_reason'])
        log_action(
            admin_user, AuditAction.LISTING_REJECT, listing, request=request, reason=listing.rejection_reason,
            before=before, after={'status': listing.status},
        )
    _notify_owner(listing, approved=False, reason=listing.rejection_reason)
    return listing


def _notify_owner(listing: LocalListing, *, approved: bool, reason: str = '') -> None:
    """Email + Telegram-сповіщення власника (Telegram-механізм з промту 11)."""
    user = listing.owner
    title = f'{listing.make} {listing.model} {listing.year}'

    if approved:
        subject = f'AUTOforYOU: оголошення «{title}» опубліковано'
        body = (
            f'Ваше оголошення «{title}» пройшло модерацію і опубліковано в Каталозі Україна.\n'
            f'Переглянути: {_listing_url(listing)}'
        )
        tg_text = f'✅ Оголошення «{title}» опубліковано в Каталозі Україна!'
    else:
        subject = f'AUTOforYOU: оголошення «{title}» відхилено'
        body = (
            f'Ваше оголошення «{title}» відхилено.\n'
            f'Причина: {reason}\n\n'
            f'Ви можете відредагувати та надіслати повторно.'
        )
        tg_text = f'❌ Оголошення «{title}» відхилено.\nПричина: {reason}'

    send_email(user.email, subject, body)  # не бросает: модерация не зависит от почты

    # In-app сповіщення
    try:
        from notifications.models import Notification as NotifModel
        from notifications.services import create_notification
        ntype = NotifModel.Type.LISTING_APPROVED if approved else NotifModel.Type.LISTING_REJECTED
        create_notification(user.pk, ntype, subject, body[:500], f'/local/{listing.pk}')
    except Exception:
        pass

    # Telegram-сповіщення (реального токена може не бути — send_notification no-op)
    try:
        from integrations.tasks import send_notification
        send_notification.delay(user.pk, tg_text)
    except Exception:
        pass


def _listing_url(listing: LocalListing) -> str:
    from django.conf import settings
    site = getattr(settings, 'SITE_URL', 'http://localhost:3000')
    return f'{site}/local/{listing.pk}'
