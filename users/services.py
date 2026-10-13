"""
Сервис заявок дилеров.

Бизнес-правила:
- Нельзя подать новую заявку при наличии pending.
- Одобрение: user.is_verified_dealer=True, role='dealer'.
- Email-уведомление при смене статуса (dev: console backend).
  # позже заменить на Telegram-уведомление (промт 11)
"""
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import DealerApplication


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
    return DealerApplication.objects.create(
        user=user,
        company_name=company_name,
        full_name=full_name,
        contact_phone=contact_phone,
        documents=documents,
        status=DealerApplication.Status.PENDING,
        agreed_to_processing_at=timezone.now(),
    )


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
    send_mail(subject, body, 'noreply@autoforyou.ua', [user.email], fail_silently=True)


# ─── Назначение ролей (только админка) ───────────────────────────────────────

ROLE_GROUPS = {
    'broker': 'Брокери',
    'moderator': 'Модератори',
    'admin': 'Адміністратори',
}


def _audit(actor, user, action, role):
    # Точка расширения под журнал аудита (Н-8); пока - стандартный логгер.
    import logging
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
