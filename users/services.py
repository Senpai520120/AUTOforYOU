"""
Сервис заявок дилеров.

Бизнес-правила:
- Нельзя подать новую заявку при наличии pending.
- Одобрение: user.is_verified_dealer=True, role='dealer'.
- Email-уведомление при смене статуса (dev: console backend).
  # позже заменить на Telegram-уведомление (промт 11)
"""
from django.core.mail import send_mail
from django.utils import timezone

from .models import DealerApplication


class DuplicatePendingError(Exception):
    pass


def apply_for_dealer(user, company_name, full_name, contact_phone, documents=''):
    """Создаёт pending-заявку. Raises DuplicatePendingError при наличии pending."""
    if DealerApplication.objects.filter(user=user, status=DealerApplication.Status.PENDING).exists():
        raise DuplicatePendingError('У вас уже есть заявка на рассмотрении.')
    return DealerApplication.objects.create(
        user=user,
        company_name=company_name,
        full_name=full_name,
        contact_phone=contact_phone,
        documents=documents,
        status=DealerApplication.Status.PENDING,
    )


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
        f'Ваша заявка на статус дилера одобрена. Добро пожаловать в B2B-клуб!'
        if approved else
        'Ваша заявка на статус дилера отклонена. Свяжитесь с поддержкой для уточнения.'
    )
    # позже заменить на Telegram-уведомление (промт 11)
    send_mail(subject, body, 'noreply@autoforyou.ua', [user.email], fail_silently=True)
