"""
Сервісний шар мессенджера (non-realtime).

Місцеві оголошення  → покупець ↔ автор оголошення.
Імпортні оголошення → покупець ↔ адмін (перший is_staff=True).
                      Всі адміни бачать ці діалоги через permissions у views.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Conversation, Message

User = get_user_model()


def _first_admin():
    return User.objects.filter(is_staff=True).order_by('pk').first()


@transaction.atomic
def get_or_create_conversation(initiator, listing_type: str, listing_id: int, first_text: str):
    """
    Повертає (conversation, created, message).
    Якщо діалог вже є — відкриває його і надсилає перше повідомлення.
    Raises ValueError: оголошення не знайдено / initiator == власник.
    """
    from listings.models import Listing
    from local_listings.models import LocalListing

    if listing_type == 'local':
        try:
            listing = LocalListing.objects.get(pk=listing_id, status=LocalListing.Status.ACTIVE)
        except LocalListing.DoesNotExist:
            raise ValueError('Оголошення не знайдено або неактивне.')
        if listing.owner_id == initiator.pk:
            raise ValueError('Не можна писати самому собі.')

        conv = Conversation.objects.filter(
            initiator=initiator, local_listing=listing
        ).first()
        if conv:
            msg, _ = _add_message(initiator, conv, first_text)
            return conv, False, msg

        conv = Conversation.objects.create(initiator=initiator, local_listing=listing)
        conv.participants.set([initiator.pk, listing.owner_id])

    elif listing_type == 'imported':
        try:
            listing = Listing.objects.get(pk=listing_id)
        except Listing.DoesNotExist:
            raise ValueError('Оголошення не знайдено.')

        conv = Conversation.objects.filter(
            initiator=initiator, imported_listing=listing
        ).first()
        if conv:
            msg, _ = _add_message(initiator, conv, first_text)
            return conv, False, msg

        conv = Conversation.objects.create(initiator=initiator, imported_listing=listing)
        admin = _first_admin()
        participants = [initiator.pk] + ([admin.pk] if admin else [])
        conv.participants.set(participants)
    else:
        raise ValueError('Невідомий тип оголошення.')

    msg, _ = _add_message(initiator, conv, first_text)
    return conv, True, msg


def send_message_to_conversation(sender, conversation: Conversation, text: str):
    """Returns (message, detected_contacts_list). Raises PermissionError if not participant."""
    is_participant = conversation.participants.filter(pk=sender.pk).exists()
    is_admin_imported = (
        bool(getattr(sender, 'is_staff', False))
        and conversation.imported_listing_id is not None
    )
    if not is_participant and not is_admin_imported:
        raise PermissionError('Ви не є учасником цього діалогу.')
    return _add_message(sender, conversation, text)


def mark_as_read(user, conversation: Conversation) -> int:
    """Позначити всі вхідні як прочитані. Повертає кількість оновлених."""
    return Message.objects.filter(
        conversation=conversation,
        read_at__isnull=True,
    ).exclude(sender=user).update(read_at=timezone.now())


def unread_count_for_user(user) -> int:
    """Загальна кількість непрочитаних повідомлень для користувача."""
    from django.db.models import Q
    qs = Message.objects.filter(read_at__isnull=True).exclude(sender=user)
    if getattr(user, 'is_staff', False):
        qs = qs.filter(
            Q(conversation__participants=user)
            | Q(conversation__imported_listing__isnull=False)
        )
    else:
        qs = qs.filter(conversation__participants=user)
    return qs.distinct().count()


def _add_message(sender, conversation: Conversation, text: str):
    """Returns (message, detected_contacts_list)."""
    from django.conf import settings as dj_settings

    from local_listings.antispam import detect_contacts

    antispam_mode = getattr(dj_settings, 'ANTISPAM_MODE', 'soft')
    detected = detect_contacts(text) if antispam_mode != 'off' else []

    if detected and antispam_mode == 'hard':
        raise PermissionError('Повідомлення містить контактні дані (телефон, посилання). Видаліть їх.')

    msg = Message.objects.create(conversation=conversation, sender=sender, text=text)
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=msg.created_at)
    _notify_recipients(sender, conversation, msg)
    return msg, detected


def _notify_recipients(sender, conversation: Conversation, message: Message) -> None:
    try:
        from integrations.tasks import send_notification
    except ImportError:
        send_notification = None

    try:
        from notifications.models import Notification as NotifModel
        from notifications.services import create_notification
    except ImportError:
        create_notification = None
        NotifModel = None

    if conversation.local_listing_id and conversation.local_listing:
        ll = conversation.local_listing
        subject_label = f'{ll.make} {ll.model} {ll.year}'
        conv_link = f'/me/messages?conv={conversation.pk}'
    elif conversation.imported_listing_id:
        subject_label = f'Оголошення #{conversation.imported_listing_id}'
        conv_link = f'/me/messages?conv={conversation.pk}'
    else:
        subject_label = 'оголошення'
        conv_link = '/me/messages'

    sender_label = sender.first_name or sender.email.split('@')[0]
    preview = message.text[:80]
    tg_text = f'Нове повідомлення від {sender_label} по {subject_label}:\n«{preview}»'
    notif_title = f'Нове повідомлення від {sender_label}'
    notif_text = f'{subject_label}: «{preview}»'

    recipients = list(conversation.participants.exclude(pk=sender.pk))
    # Для імпортних — додатково адміни, які не є учасниками
    if conversation.imported_listing_id:
        existing_ids = {r.pk for r in recipients} | {sender.pk}
        extra_admins = User.objects.filter(is_staff=True).exclude(pk__in=existing_ids)
        for admin in extra_admins:
            _send_one(admin.pk, tg_text, notif_title, notif_text, conv_link, send_notification, create_notification, NotifModel)

    for recipient in recipients:
        _send_one(recipient.pk, tg_text, notif_title, notif_text, conv_link, send_notification, create_notification, NotifModel)


def _send_one(user_id, tg_text, notif_title, notif_text, link, send_notification, create_notification, NotifModel):
    if create_notification and NotifModel:
        try:
            create_notification(user_id, NotifModel.Type.NEW_MESSAGE, notif_title, notif_text, link)
        except Exception:
            pass
    if send_notification:
        try:
            send_notification.delay(user_id, tg_text)
        except Exception:
            pass
