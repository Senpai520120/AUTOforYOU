"""
Сервис заявок дилеров.

Бизнес-правила:
- Нельзя подать новую заявку при наличии pending.
- Одобрение: user.is_verified_dealer=True, role='dealer'.
- Email-уведомление при смене статуса (dev: console backend).
  # позже заменить на Telegram-уведомление (промт 11)
"""
import logging
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone

from integrations.email import send_email

from .consents import record_consents
from .models import ConsentDocument, ConsentMethod, DealerApplication


class DuplicatePendingError(Exception):
    pass


def apply_for_dealer(user, company_name, full_name, contact_phone, documents=''):
    """
    Создаёт pending-заявку. Raises DuplicatePendingError при наличии pending.

    Метка времени согласия ставится здесь: заявку без согласия принимать
    нельзя, а сериализатор не пропустит её без agreed_to_processing=True.
    """
    if DealerApplication.objects.filter(user=user, status=DealerApplication.Status.PENDING).exists():
        raise DuplicatePendingError('У вас уже есть заявка на рассмотрении.')
    with transaction.atomic():
        application = DealerApplication.objects.create(
            user=user,
            company_name=company_name,
            full_name=full_name,
            contact_phone=contact_phone,
            documents=documents,
            status=DealerApplication.Status.PENDING,
            agreed_to_processing_at=timezone.now(),
        )
        record_consents(
            user, [ConsentDocument.DEALER_PROCESSING, ConsentDocument.AGE_18], ConsentMethod.DEALER_FORM,
        )
    return application


@transaction.atomic
def approve_application(application, admin_user):
    """Одобряет заявку: is_verified_dealer=True, role='dealer'."""
    application.status = DealerApplication.Status.APPROVED
    application.reviewed_by = admin_user
    application.reviewed_at = timezone.now()
    application.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

    user = application.user
    user.is_verified_dealer = True
    user.role = 'dealer'
    user.save(update_fields=['is_verified_dealer', 'role'])

    _notify(user, approved=True)


@transaction.atomic
def reject_application(application, admin_user, notes=''):
    """Отклоняет заявку, сохраняет заметки рассмотрения."""
    application.status = DealerApplication.Status.REJECTED
    application.reviewed_by = admin_user
    application.reviewed_at = timezone.now()
    application.review_notes = notes
    application.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes'])

    _notify(application.user, approved=False)


def _notify(user, *, approved):
    subject = 'AUTOforYOU: заявка одобрена' if approved else 'AUTOforYOU: заявка отклонена'
    body = (
        'Ваша заявка на статус дилера одобрена. Добро пожаловать в B2B-клуб!'
        if approved else
        'Ваша заявка на статус дилера отклонена. Свяжитесь с поддержкой для уточнения.'
    )
    # позже заменить на Telegram-уведомление (промт 11)
    to = user.email
    # После фиксации транзакции: откат одобрения не должен оставлять отправленное письмо.
    transaction.on_commit(lambda: send_email(to, subject, body))  # не бросает


# ─── Сессии и бан ────────────────────────────────────────────────────────────

def revoke_all_sessions(user):
    """Отзывает все сессии пользователя (задача 1.7).

    session_version += 1 гасит живые access и любой refresh старой версии (в т.ч. ротируемый
    параллельно: refresh берёт ту же блокировку строки пользователя, см. users/jwt.py).
    Все refresh дополнительно уходят в blacklist. Работает и для неактивного пользователя
    (бан, анонимизация 1.8). Версия на переданном объекте обновляется.
    """
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    with transaction.atomic():
        locked = get_user_model().objects.select_for_update().get(pk=user.pk)
        locked.session_version += 1
        locked.save(update_fields=['session_version'])
        for outstanding in OutstandingToken.objects.filter(user=locked):
            BlacklistedToken.objects.get_or_create(token=outstanding)
        user.session_version = locked.session_version


def ban_user(user):
    """Бан: is_banned, is_active=False, сессии отозваны. Возвращает False, если уже забанен."""
    if user.is_banned:
        return False
    with transaction.atomic():
        user.is_banned = True
        user.is_active = False
        user.save(update_fields=['is_banned', 'is_active'])
        revoke_all_sessions(user)
    return True


def unban_user(user):
    """Разбан возвращает is_active только тому, кого забанил ban_user (is_banned=True)."""
    if not user.is_banned:
        return False
    user.is_banned = False
    user.is_active = True
    user.save(update_fields=['is_banned', 'is_active'])
    return True


# ─── Удаление аккаунта и обезличивание (задача 1.8, Q3) ───────────────────────

logger = logging.getLogger(__name__)


class AccountDeletionError(Exception):
    """Аккаунт нельзя поставить на удаление или обезличить (суперпользователь, уже удалён)."""


def deletion_grace_days() -> int:
    from site_settings.models import SiteSettings
    return SiteSettings.load().account_deletion_grace_days


def deletion_due_at(user, grace_days=None):
    """Когда истекает период отмены (None - удаление не запрошено)."""
    if user.deletion_scheduled_at is None:
        return None
    days = deletion_grace_days() if grace_days is None else grace_days
    return user.deletion_scheduled_at + timedelta(days=days)


def _hide_active_listings(user):
    from local_listings.models import LocalListing
    return LocalListing.objects.filter(
        owner=user, status__in=[LocalListing.Status.ACTIVE, LocalListing.Status.PENDING],
    ).update(status=LocalListing.Status.HIDDEN)


def schedule_account_deletion(user):
    """Запрос удаления: начало периода отмены, объявления сняты, все сессии отозваны, письмо.

    Повторный запрос не сдвигает дату. Возвращает дату окончательного удаления.
    """
    if user.is_superuser:
        raise AccountDeletionError('Акаунт суперкористувача видаляється вручну.')
    newly = False
    with transaction.atomic():
        locked = get_user_model().objects.select_for_update().get(pk=user.pk)
        if locked.deleted_at is not None:
            raise AccountDeletionError('Акаунт уже видалено.')
        if locked.deletion_scheduled_at is None:
            locked.deletion_scheduled_at = timezone.now()
            locked.save(update_fields=['deletion_scheduled_at'])
            newly = True
        user.deletion_scheduled_at = locked.deletion_scheduled_at
        _hide_active_listings(locked)
        revoke_all_sessions(user)
    due = deletion_due_at(user)
    if newly:
        from .emails import send_account_deletion_scheduled_email
        transaction.on_commit(lambda: send_account_deletion_scheduled_email(user, due))
        logger.info('account deletion scheduled: user=%s', user.pk)
    return due


def cancel_account_deletion(user) -> bool:
    """Отмена в период отмены. Снятые объявления остаются снятыми. False - отменять нечего."""
    updated = get_user_model().objects.filter(
        pk=user.pk, deletion_scheduled_at__isnull=False, deleted_at__isnull=True,
    ).update(deletion_scheduled_at=None)
    user.deletion_scheduled_at = None
    if updated:
        logger.info('account deletion cancelled: user=%s', user.pk)
    return bool(updated)


def _delete_files(names):
    from django.core.files.storage import default_storage
    for name in names:
        try:
            default_storage.delete(name)
        except Exception as exc:  # файл уже удалён/хранилище недоступно - строку БД это не возвращает
            logger.warning('anonymize: файл фото не удалён: %s', type(exc).__name__)


def anonymize_user(user, *, due_before=None) -> bool:
    """Обезличивание аккаунта: один сервис для Celery-задачи и админки (06-S11).

    Строки, на которые ссылаются другие люди (сделки, отзывы, переписка, жалобы, платежи),
    не удаляются - вторая сторона видит «Користувач видалений» (deleted_at, users/display.py).
    ConsentRecord не удаляется: user обнуляется явным UPDATE в обход неизменяемого менеджера.
    due_before (Celery-задача): обезличить, только если удаление всё ещё запрошено не позже этой
    даты - иначе пользователь успел отменить его, пока задача шла по списку.
    Возвращает False, если аккаунт уже обезличен или удаление отменено.
    """
    from favorites.models import Favorite
    from integrations.models import OutboxMessage
    from leads.services import anonymize_user_leads
    from local_listings.models import LocalListing, LocalListingImage
    from notifications.models import Notification
    from pricing.models import Calculation
    from saved_searches.models import SavedSearch
    from telegram_bot.models import TelegramLinkToken

    from .emails import send_account_deleted_email
    from .models import ConsentRecord, CustomUser, TrustedShop

    with transaction.atomic():
        locked = CustomUser.objects.select_for_update().get(pk=user.pk)
        if locked.is_superuser:
            raise AccountDeletionError('Акаунт суперкористувача видаляється вручну.')
        if locked.deleted_at is not None:
            return False
        if due_before is not None and (
            locked.deletion_scheduled_at is None or locked.deletion_scheduled_at > due_before
        ):
            return False
        email = locked.email

        anonymize_user_leads(locked)
        TrustedShop.objects.filter(owner=locked).delete()
        SavedSearch.objects.filter(user=locked).delete()
        Favorite.objects.filter(user=locked).delete()
        Notification.objects.filter(user=locked).delete()
        TelegramLinkToken.objects.filter(user=locked).delete()
        DealerApplication.objects.filter(user=locked).delete()
        # Демо-Outbox хранит адрес и тела писем (ссылки сброса): удаляем записи этого адреса.
        OutboxMessage.objects.filter(recipient__iexact=email).delete()

        # Объявления - в архив (hidden до задачи 4.3, она переведёт их в deleted по owner.deleted_at).
        # Фото удаляются целиком: на них бывают номера и дом.
        images = LocalListingImage.objects.filter(listing__owner=locked)
        files = [img.image.name for img in images if img.image]
        images.delete()
        LocalListing.objects.filter(owner=locked).update(
            status=LocalListing.Status.HIDDEN, contact_phone='', description='', has_contact_in_text=False,
            referrer='', entry_page_url='',  # источник визита (2.14): UTM без ПДн остаётся
        )

        Calculation.objects.filter(user=locked).update(user=None)
        locked.watched_shipments.clear()
        # Журнал согласий неизменяем для ConsentRecord.objects; запись остаётся доказательством.
        models.QuerySet(model=ConsentRecord).filter(user=locked).update(user=None)

        was_broker = locked.role == CustomUser.Role.BROKER
        locked.groups.clear()
        locked.user_permissions.clear()
        # Случайный адрес: предсказуемый deleted-<pk>@… можно было занять регистрацией и сорвать
        # обезличивание (unique email).
        locked.email = f'deleted-{uuid.uuid4().hex}@deleted.invalid'
        locked.first_name = locked.last_name = locked.phone = ''
        if locked.telegram_id:
            OutboxMessage.objects.filter(provider='telegram', recipient=str(locked.telegram_id)).delete()
        locked.telegram_id = None
        locked.first_touch_utm = {}
        locked.first_touch_referrer = locked.first_touch_entry_url = ''
        locked.role = CustomUser.Role.BUYER
        locked.is_verified_dealer = False
        locked.is_staff = False
        locked.is_active = False
        locked.is_email_verified = False
        locked.last_login = None
        locked.set_unusable_password()
        locked.deleted_at = timezone.now()
        locked.save()
        if was_broker:  # как при снятии роли: импортные диалоги передаются другому брокеру/админу
            _release_import_conversations(locked)
        revoke_all_sessions(locked)

        transaction.on_commit(lambda: _delete_files(files))
        transaction.on_commit(lambda: send_account_deleted_email(email))
    user.refresh_from_db()
    logger.info('account anonymized: user=%s', user.pk)
    return True


# ─── Назначение ролей (только админка) ───────────────────────────────────────

ROLE_GROUPS = {
    'broker': 'Брокери',
    'moderator': 'Модератори',
    'admin': 'Адміністратори',
}


def _audit(actor, user, action, role):
    # Точка расширения под журнал аудита (Н-8); пока - стандартный логгер.
    logging.getLogger('audit').info(
        'role %s: actor=%s user=%s role=%s',
        action, getattr(actor, 'pk', None), user.pk, role,
    )


@transaction.atomic
def assign_role(user, role, actor=None) -> bool:
    """
    Назначает broker/moderator: role + группа + is_staff (доступ в админку).
    Идемпотентно. Возвращает True, если что-то изменилось.
    """
    from django.contrib.auth.models import Group

    group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[role])
    other_groups = user.groups.filter(name__in=ROLE_GROUPS.values()).exclude(pk=group.pk)
    changed = (
        user.role != role or not user.is_staff
        or not user.groups.filter(pk=group.pk).exists() or other_groups.exists()
    )
    if not changed:
        return False
    # роли взаимоисключающие: снимаем группы прочих ролей (брокер -> модератор и т.п.)
    user.groups.remove(*other_groups)
    user.role = role
    user.is_staff = True
    user.save(update_fields=['role', 'is_staff'])
    user.groups.add(group)
    _audit(actor, user, 'assign', role)
    return True


@transaction.atomic
def revoke_role(user, role, actor=None) -> bool:
    """
    Снимает broker/moderator: роль возвращается к dealer (если верифицирован)
    или buyer, группа убирается, is_staff снимается (кроме суперпользователя
    и случая, когда есть другая роль-группа). Идемпотентно.
    """
    from django.contrib.auth.models import Group

    if user.role != role:
        return False
    group = Group.objects.filter(name=ROLE_GROUPS[role]).first()
    if group:
        user.groups.remove(group)
    user.role = 'dealer' if user.is_verified_dealer else 'buyer'
    if not user.is_superuser:
        user.is_staff = False
    user.save(update_fields=['role', 'is_staff'])
    if role == 'broker':
        _release_import_conversations(user)
    _audit(actor, user, 'revoke', role)
    return True


def _release_import_conversations(user):
    """Бывший брокер больше не участник импортных диалогов: передаём новому брокеру/админу."""
    from messaging.models import Conversation
    from messaging.services import _first_admin

    successor = _first_admin()
    for conv in Conversation.objects.filter(participants=user, imported_listing__isnull=False):
        conv.participants.remove(user)
        if successor and successor.pk != user.pk:
            conv.participants.add(successor)
