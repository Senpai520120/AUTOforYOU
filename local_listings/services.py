"""
Сервісний шар для модерації місцевих оголошень.

Суттєві поля (редагування → ремодерація):
  make, model, year, price, description
Несуттєві (правка без ремодерації):
  currency, price_type, contact_phone, mileage_km, engine_cc,
  fuel_type, transmission, body_type, condition, region, city
"""
from django.core.mail import send_mail
from django.utils import timezone

from .models import LocalListing

# Поля, редагування яких повертає active-оголошення на pending (ремодерація)
SUBSTANTIVE_FIELDS = frozenset({'make', 'model', 'year', 'price', 'description'})


def approve_listing(listing: LocalListing, admin_user) -> LocalListing:
    """Перевести оголошення в active + зафіксувати модератора + повідомити власника."""
    listing.status = LocalListing.Status.ACTIVE
    listing.moderated_by = admin_user
    listing.moderated_at = timezone.now()
    listing.rejection_reason = ''
    listing.save(update_fields=['status', 'moderated_by', 'moderated_at', 'rejection_reason'])
    _notify_owner(listing, approved=True)
    return listing


def reject_listing(listing: LocalListing, admin_user, reason: str = '') -> LocalListing:
    """Відхилити оголошення, зберегти причину, повідомити власника."""
    listing.status = LocalListing.Status.REJECTED
    listing.moderated_by = admin_user
    listing.moderated_at = timezone.now()
    listing.rejection_reason = reason or 'Не відповідає правилам розміщення.'
    listing.save(update_fields=['status', 'moderated_by', 'moderated_at', 'rejection_reason'])
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

    send_mail(subject, body, 'noreply@autoforyou.ua', [user.email], fail_silently=True)

    # In-app сповіщення
    try:
        from notifications.services import create_notification
        from notifications.models import Notification as NotifModel
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
