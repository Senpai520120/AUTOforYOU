from celery import shared_task
from datetime import timedelta
from django.utils import timezone


@shared_task
def warn_expiring_listings():
    """За 3 дні до expires_at — попередження власнику (один раз, idempotent)."""
    from .models import LocalListing
    from notifications.models import Notification
    from notifications.services import create_notification
    from integrations.tasks import send_notification

    threshold = timezone.now() + timedelta(days=3)
    qs = LocalListing.objects.filter(
        status=LocalListing.Status.ACTIVE,
        expires_at__lte=threshold,
        expires_at__gt=timezone.now(),
        expiry_warned=False,
    )
    count = 0
    for listing in qs:
        days_left = max(0, (listing.expires_at - timezone.now()).days)
        create_notification(
            user_id=listing.owner_id,
            ntype=Notification.Type.LISTING_EXPIRING,
            title=f'Оголошення «{listing.make} {listing.model}» завершується через {days_left} дн.',
            text='Продовжте оголошення, щоб воно залишалось у каталозі.',
            link='/me/local-listings',
        )
        send_notification.delay(
            listing.owner_id,
            f'⏰ Ваше оголошення {listing.make} {listing.model} {listing.year} '
            f'завершується через {days_left} дн. Продовжте в кабінеті.',
        )
        listing.expiry_warned = True
        listing.save(update_fields=['expiry_warned'])
        count += 1
    return f'warned={count}'


@shared_task
def expire_listings():
    """Переводить прострочені active-оголошення в expired (idempotent)."""
    from .models import LocalListing
    from notifications.models import Notification
    from notifications.services import create_notification
    from integrations.tasks import send_notification

    now = timezone.now()
    qs = LocalListing.objects.filter(
        status=LocalListing.Status.ACTIVE,
        expires_at__lte=now,
    )
    count = 0
    for listing in qs:
        listing.status = LocalListing.Status.EXPIRED
        listing.save(update_fields=['status'])
        create_notification(
            user_id=listing.owner_id,
            ntype=Notification.Type.LISTING_EXPIRING,
            title=f'Оголошення «{listing.make} {listing.model}» знято з каталогу',
            text='Термін дії закінчився. Натисніть «Продовжити» для відновлення.',
            link='/me/local-listings',
        )
        send_notification.delay(
            listing.owner_id,
            f'❌ Ваше оголошення {listing.make} {listing.model} {listing.year} '
            f'знято з каталогу — термін закінчився. Продовжте в кабінеті.',
        )
        count += 1
    return f'expired={count}'
