"""
Сервісний шар мессенджера (non-realtime).

Місцеві оголошення  → покупець ↔ автор оголошення.
Імпортні оголошення → покупець ↔ брокер (перший broker, інакше перший admin).
                      Ці діалоги бачать лише broker і admin (не просто is_staff).
"""
import logging

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from users.display import public_display_name

from .exceptions import ContactsInTextError, ConversationClosed, RecipientDeleted
from .models import Conversation, Message

logger = logging.getLogger(__name__)

CONVERSATION_CLOSED = 'Діалог закрито: оголошення продане або зняте.'
RECIPIENT_DELETED = 'Користувач видалений'

User = get_user_model()


class ListingUnavailable(LookupError):
    """Лот не існує або недоступний користувачу (не розрізняємо) - view відповідає 404."""


def handles_imports(user) -> bool:
    """Імпортні діалоги бачать лише broker і admin (06-S9), is_staff без ролі - ні."""
    return bool(
        getattr(user, 'is_authenticated', False)
        and (user.is_broker or user.is_admin_role)
    )


def _first_admin():
    """Отримувач імпортного діалогу: перший брокер, за його відсутності - перший admin."""
    return (
        User.objects.filter(role=User.Role.BROKER).order_by('pk').first()
        or User.objects.filter(
            Q(role=User.Role.ADMIN, is_staff=True) | Q(is_superuser=True)
        ).order_by('pk').first()
    )


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

        conv, created = _get_or_create(initiator, local_listing=listing)
        if not created:
            msg, _ = _add_message(initiator, conv, first_text)
            return conv, False, msg
        conv.participants.set([initiator.pk, listing.owner_id])

    elif listing_type == 'imported':
        from core.modules import module_enabled
        from listings.permissions import can_view_wholesale

        if not module_enabled('lots'):
            raise ListingUnavailable('Оголошення не знайдено.')
        try:
            listing = Listing.objects.get(pk=listing_id)
        except Listing.DoesNotExist:
            raise ListingUnavailable('Оголошення не знайдено.')
        if listing.channel == Listing.Channel.WHOLESALE and not (
            module_enabled('b2b') and can_view_wholesale(initiator)
        ):
            raise ListingUnavailable('Оголошення не знайдено.')

        conv, created = _get_or_create(initiator, imported_listing=listing)
        if not created:
            msg, _ = _add_message(initiator, conv, first_text)
            return conv, False, msg
        admin = _first_admin()
        participants = [initiator.pk] + ([admin.pk] if admin else [])
        conv.participants.set(participants)
    else:
        raise ValueError('Невідомий тип оголошення.')

    msg, _ = _add_message(initiator, conv, first_text)
    return conv, True, msg


def _get_or_create(initiator, **listing):
    """(conversation, created). Двойной клик «Написати» - существующий диалог, а не 500 (06-Q9, E6)."""
    conv = Conversation.objects.filter(initiator=initiator, **listing).first()
    if conv:
        return conv, False
    try:
        with transaction.atomic():
            return Conversation.objects.create(initiator=initiator, **listing), True
    except IntegrityError:
        conv = Conversation.objects.filter(initiator=initiator, **listing).first()
        if conv is None:
            raise  # другое ограничение - не гонка двойного клика
        return conv, False


def incoming_q(user, prefix=''):
    """Какие сообщения «входящие» для user (E3).

    Инициатор (покупатель) читает всё, что пишут ему. Остальные (продавец, брокеры, админ) - только
    сообщения инициатора: ответы коллеги-брокера покупателю не считаются и не помечаются ими.
    """
    initiator = f'{prefix}conversation__initiator'
    return (
        (Q(**{initiator: user}) & ~Q(**{f'{prefix}sender': user}))
        | (~Q(**{initiator: user}) & Q(**{f'{prefix}sender_id': F(f'{initiator}_id')}))
    )


def send_message_to_conversation(sender, conversation: Conversation, text: str):
    """Returns (message, detected_contacts_list).

    Raises PermissionError (не участник), ConversationClosed (объявление продано/снято, E5),
    RecipientDeleted (собеседник удалил аккаунт, Q3), ContactsInTextError (антиспам hard).
    """
    from local_listings.models import LocalListing

    is_participant = conversation.participants.filter(pk=sender.pk).exists()
    is_admin_imported = (
        handles_imports(sender)
        and conversation.imported_listing_id is not None
    )
    if not is_participant and not is_admin_imported:
        raise PermissionError('Ви не є учасником цього діалогу.')
    # E5: писать можно, пока объявление active или на модерации (pending); проданное, снятое, отклонённое,
    # истёкшее или удалённое (local_listing стал NULL) - диалог закрыт. Статусы 4.3 добавятся сюда же.
    ll = conversation.local_listing
    if conversation.imported_listing_id is None and (
        ll is None or ll.status not in (LocalListing.Status.ACTIVE, LocalListing.Status.PENDING)
    ):
        raise ConversationClosed(CONVERSATION_CLOSED)
    others = conversation.participants.exclude(pk=sender.pk)
    if conversation.local_listing_id and others.exists() and not others.filter(deleted_at__isnull=True).exists():
        raise RecipientDeleted(RECIPIENT_DELETED)
    return _add_message(sender, conversation, text)


def mark_as_read(user, conversation: Conversation) -> int:
    """Позначити вхідні як прочитані. Повертає кількість оновлених.

    E3, 06-Q11: «вхідні» - за incoming_q; брокер (учасник чи ні) позначає лише повідомлення покупця,
    відповіді колег покупцю лишаються непрочитаними для покупця.
    """
    return Message.objects.filter(
        incoming_q(user), conversation=conversation, read_at__isnull=True,
    ).update(read_at=timezone.now())


def unread_count_for_user(user) -> int:
    """Загальна кількість непрочитаних повідомлень для користувача."""
    qs = Message.objects.filter(incoming_q(user), read_at__isnull=True)
    if handles_imports(user):
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
        raise ContactsInTextError()

    msg = Message.objects.create(conversation=conversation, sender=sender, text=text)
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=msg.created_at)
    _notify_recipients(sender, conversation, msg)
    return msg, detected


def _notify_recipients(sender, conversation: Conversation, message: Message) -> None:
    """Уведомления через notifications.notify: текст - шаблон new_message, Telegram после коммита (4.7)."""
    from notifications.services import notify

    if conversation.local_listing_id and conversation.local_listing:
        ll = conversation.local_listing
        listing_label = f'{ll.make} {ll.model} {ll.year}'
    elif conversation.imported_listing_id:
        listing_label = f'Оголошення #{conversation.imported_listing_id}'
    else:
        listing_label = 'оголошення'
    link = f'/me/messages?conv={conversation.pk}'
    context = {'sender': public_display_name(sender), 'listing': listing_label, 'preview': message.text[:80]}

    recipient_ids = set(conversation.participants.exclude(pk=sender.pk).values_list('pk', flat=True))
    # Для імпортних — додатково брокери й адміни, які не є учасниками
    if conversation.imported_listing_id:
        recipient_ids |= set(
            User.objects.brokers_and_admins().exclude(pk=sender.pk).values_list('pk', flat=True)
        )
    for user_id in sorted(recipient_ids):
        notify(user_id, 'new_message', context, link)
