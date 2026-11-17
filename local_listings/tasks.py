from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from core.c2c import c2c_enabled


# Пакетная задача: глобальный лимит 120/180 с (CELERY_TASK_SOFT_TIME_LIMIT) мал для большого объёма, поэтому свой лимит.
@shared_task(soft_time_limit=900, time_limit=960)
def warn_expiring_listings():
    """За 3 дні до expires_at — попередження власнику (один раз, idempotent)."""
    if not c2c_enabled():  # 6.7: раздел выключен - ни БД, ни писем
        return {'skipped': 'c2c_disabled'}
    from integrations.tasks import send_notification
    from notifications.models import Notification
    from notifications.services import create_notification

    from .models import LocalListing

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


# Пакетная задача: глобальный лимит 120/180 с (CELERY_TASK_SOFT_TIME_LIMIT) мал для большого объёма, поэтому свой лимит.
@shared_task(soft_time_limit=900, time_limit=960)
def expire_listings():
    """Переводить прострочені active-оголошення в expired (idempotent)."""
    if not c2c_enabled():  # 6.7
        return {'skipped': 'c2c_disabled'}
    from integrations.tasks import send_notification
    from notifications.models import Notification
    from notifications.services import create_notification

    from .models import LocalListing

    now = timezone.now()
    qs = LocalListing.objects.filter(
        status=LocalListing.Status.ACTIVE,
        expires_at__lte=now,
    )
    count = 0
    for listing in qs:
        # Условный UPDATE вместо save(): если владелец продлил объявление между выборкой и записью,
        # expires_at уже в будущем, строка не совпадёт и статус не затрётся (гонка с продлением).
        # post_save-ресиверов на LocalListing нет (только post_delete у изображений) - ничего не теряем.
        updated = LocalListing.objects.filter(
            pk=listing.pk,
            status=LocalListing.Status.ACTIVE,
            expires_at__lte=now,
        ).update(status=LocalListing.Status.EXPIRED)
        if updated != 1:
            continue
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


# Пакетная задача: глобальный лимит 120/180 с (CELERY_TASK_SOFT_TIME_LIMIT) мал для большого объёма, поэтому свой лимит.
@shared_task(soft_time_limit=900, time_limit=960)
def cleanup_contact_views():
    """4.5a (05-S6): журнал показов телефона старше CONTACT_VIEW_RETENTION_DAYS удаляется (раз в сутки)."""
    from django.conf import settings

    from .models import ContactView

    cutoff = timezone.now() - timedelta(days=settings.CONTACT_VIEW_RETENTION_DAYS)
    deleted, _ = ContactView.objects.filter(created_at__lt=cutoff).delete()
    return {'deleted': deleted}
