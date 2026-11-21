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


class ListingNotReadyError(ValueError):
    """8.4: объявление нельзя одобрить (например, фото меньше LOCAL_LISTING_MIN_PHOTOS)."""


def min_photos() -> int:
    from django.conf import settings
    return max(0, int(settings.LOCAL_LISTING_MIN_PHOTOS))


def not_enough_photos_text(n: int) -> str:
    return f'Недостатньо фото: потрібно щонайменше {n}.'


def check_ready_for_approval(listing: LocalListing) -> None:
    need = min_photos()
    if need and listing.images.count() < need:
        raise ListingNotReadyError(not_enough_photos_text(need))


def approve_listing(listing: LocalListing, admin_user, request=None) -> LocalListing:
    """Перевести оголошення в active + зафіксувати модератора + журнал аудиту + повідомити власника.

    Ничего не делает, если статус изменился параллельно или владелец заблокирован.
    8.4: фото меньше LOCAL_LISTING_MIN_PHOTOS - ListingNotReadyError, статус не меняется.
    """
    check_ready_for_approval(listing)
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


# ─── Журнал показов телефона (4.5a, 05-S6) ───────────────────────────────────

def _mask_email(email: str) -> str:
    """ivan.petrenko@gmail.com -> iv…@gmail.com: модератору хватает для узнавания, полный адрес - в админке."""
    local, _, domain = (email or '').partition('@')
    if not domain:
        return '…'
    return f'{local[:2]}…@{domain}'


def moderator_ids() -> list[int]:
    """Получатели сигналов модерации: активные с правом moderate_locallisting (группа или лично) и superuser."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.db.models import Q

    perm = Permission.objects.filter(codename='moderate_locallisting', content_type__app_label='local_listings').first()
    q = Q(is_superuser=True)
    if perm is not None:
        q |= Q(groups__permissions=perm) | Q(user_permissions=perm)
    return list(
        get_user_model().objects.filter(q, is_active=True, deleted_at__isnull=True)
        .values_list('pk', flat=True).distinct()
    )


def record_contact_view(listing: LocalListing, *, user=None, ip_hash: str = '') -> None:
    """Записать показ и проверить порог аномалии. Пользователь: повтор того же объявления за час - без записи.

    Гость: запись на каждый показ (is_guest=True, только хэш IP). Номер, user-agent и IP не пишутся.
    """
    from datetime import timedelta

    from django.conf import settings

    from .models import ContactView

    now = timezone.now()
    if user is not None:
        if ContactView.objects.filter(user=user, listing=listing, created_at__gte=now - timedelta(hours=1)).exists():
            return
        ContactView.objects.create(user=user, listing=listing, created_at=now)
        scope = {'user': user}
    else:
        ContactView.objects.create(is_guest=True, ip_hash=ip_hash, listing=listing, created_at=now)
        scope = {'ip_hash': ip_hash, 'is_guest': True}

    threshold = settings.CONTACT_VIEW_ALERT_THRESHOLD
    distinct = (
        ContactView.objects.filter(created_at__gte=now - timedelta(days=1), **scope)
        .values('listing_id').distinct().count()
    )
    if threshold > 0 and distinct >= threshold:
        _alert_anomaly(user=user, ip_hash=ip_hash, count=distinct)


def _alert_anomaly(*, user, ip_hash: str, count: int) -> None:
    """Одно in-app уведомление модераторам в сутки на пользователя/хэш (cache.add - атомарная отметка)."""
    from django.core.cache import cache

    from notifications.services import notify

    if user is not None:
        mark = f'contact_anomaly:user:{user.pk}'
        who = f'Користувач #{user.pk} ({_mask_email(user.email)})'
        link = f'/admin/local_listings/contactview/?user__id__exact={user.pk}'
    else:
        mark = f'contact_anomaly:ip:{ip_hash}'
        who = f'Гість (хеш {ip_hash[:8]}…)'
        link = f'/admin/local_listings/contactview/?q={ip_hash[:8]}'
    if not cache.add(mark, 1, timeout=86400):
        return
    for moderator_id in moderator_ids():
        notify(moderator_id, 'contact_anomaly', {'who': who, 'count': count}, link, telegram=False)


# ─── История цены (8.6, D5.1) ────────────────────────────────────────────────

def record_price_change(listing: LocalListing) -> bool:
    """Записать цену, если она отличается от последней записи (сравнение Decimal и валюты). True - записано."""
    from .models import ListingPriceHistory

    last = ListingPriceHistory.objects.filter(listing=listing).order_by('-changed_at', '-pk').first()
    price = Decimal(str(listing.price))
    if last is not None and last.price == price and last.currency == listing.currency:
        return False
    ListingPriceHistory.objects.create(listing=listing, price=price, currency=listing.currency)
    return True


# 10.30: фото закрытых объявлений. Ссылка на /media/local_listings/... работает по UUID без авторизации,
# поэтому у rejected и sold файлы не должны лежать вечно. Hidden/expired не трогаем: владелец может вернуть их.
PURGE_PHOTO_STATUSES = (LocalListing.Status.REJECTED, LocalListing.Status.SOLD)


def photo_purge_days() -> int:
    from django.conf import settings
    return max(1, int(settings.LOCAL_LISTING_PHOTO_PURGE_DAYS))


def listings_due_for_photo_purge(now=None):
    """Объявления rejected/sold, закрытые (updated_at) не позже N дней назад и ещё с фото."""
    from datetime import timedelta
    border = (now or timezone.now()) - timedelta(days=photo_purge_days())
    return LocalListing.objects.filter(
        status__in=PURGE_PHOTO_STATUSES, updated_at__lte=border, images__isnull=False,
    ).distinct()


def purge_listing_photos(listing: LocalListing) -> int:
    """Удалить фото объявления (записи; файлы и миниатюры уйдут сигналом post_delete после коммита).

    Только для rejected/sold: иначе 0. Идемпотентно. Возвращает число удалённых фото.
    """
    if listing.status not in PURGE_PHOTO_STATUSES:
        return 0
    count = 0
    with transaction.atomic():
        for image in listing.images.all():
            image.delete()
            count += 1
    return count
