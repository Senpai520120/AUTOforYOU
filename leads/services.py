"""Бизнес-логика заявок: создание, смена статуса, номер AFY-ГГГГ-NNNN."""
import logging

from django.db import transaction
from django.utils import timezone

from site_settings.models import SiteSettings
from users.consents import record_consents
from users.models import ConsentDocument, ConsentMethod

from .models import Lead, LeadCounter, LeadSource, LeadStatus, LeadStatusChange
from .validators import clean_attribution, normalize_ua_phone

logger = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    LeadStatus.NEW: {LeadStatus.IN_PROGRESS, LeadStatus.REJECTED, LeadStatus.SPAM},
    LeadStatus.IN_PROGRESS: {LeadStatus.CONTRACT, LeadStatus.REJECTED},
    LeadStatus.CONTRACT: {LeadStatus.CAR_BOUGHT, LeadStatus.REJECTED},
    LeadStatus.CAR_BOUGHT: {LeadStatus.IN_TRANSIT, LeadStatus.REJECTED},
    LeadStatus.IN_TRANSIT: {LeadStatus.CUSTOMS},
    LeadStatus.CUSTOMS: {LeadStatus.DELIVERED},
    LeadStatus.DELIVERED: set(),
    LeadStatus.REJECTED: set(),
    LeadStatus.SPAM: set(),
}

# Поля, которые принимаются из data (остальное сервис выставляет сам).
_DATA_FIELDS = (
    'name', 'email', 'contact_method', 'contact_handle', 'comment', 'landing_slug',
    'budget_usd', 'needed_when', 'city', 'vehicle_label',
)

PARTNER_CONSENT_TEMPLATE = 'Погоджуюсь на передачу моїх контактних даних партнеру: {partner}'


class InvalidTransition(Exception):
    pass


class AlreadyTaken(Exception):
    """Заявку уже взял другой брокер (API отвечает 409)."""


class PartnerNotConfigured(Exception):
    """SiteSettings.partner_name пуст: заявки не принимаются (API отвечает 503)."""


def notify_new_lead(lead_id: int) -> None:
    """Личное уведомление брокеру (2.2); журнал в группу - 2.15. Без ПДн в логе."""
    from .tasks import notify_broker_new_lead
    notify_broker_new_lead.delay(lead_id)


def record_metric(event: str) -> None:
    """Заглушка серверных счётчиков (8.7). Не падает, без ПДн."""
    logger.info('metric event=%s', event)


def _after_commit(lead_id: int) -> None:
    # Сбой уведомления не должен ронять создание заявки; в лог только lead_id.
    for hook, args in ((notify_new_lead, (lead_id,)), (record_metric, ('lead_created',))):
        try:
            hook(*args)
        except Exception:
            logger.exception('lead.hook_failed lead_id=%s hook=%s', lead_id, getattr(hook, '__name__', 'hook'))


def _next_public_id(year: int) -> str:
    counter, _ = LeadCounter.objects.get_or_create(year=year)
    counter = LeadCounter.objects.select_for_update().get(pk=year)
    counter.last_number += 1
    counter.save(update_fields=['last_number'])
    return f'AFY-{year}-{counter.last_number:04d}'


def build_calculation_snapshot(calculation) -> dict:
    if calculation is None:
        return {}
    return {
        'calculation_id': calculation.pk,
        'created_at': calculation.created_at.isoformat(),
        'is_estimate': calculation.is_estimate,
        'inputs_snapshot': calculation.inputs_snapshot,
        'rates_snapshot': calculation.rates_snapshot,
        'breakdown': calculation.breakdown,
        'total_usd': str(calculation.total_usd),
        'total_uah': str(calculation.total_uah),
    }


def create_lead(*, user, data: dict, calculation=None, listing=None) -> Lead:
    """Создаёт заявку. data уже провалидирован сериализатором; телефон и атрибуция
    нормализуются повторно (идемпотентно). Бросает PartnerNotConfigured при пустом partner_name."""
    if calculation is not None and calculation.user_id is not None and (
            user is None or not getattr(user, 'is_authenticated', False) or calculation.user_id != user.pk):
        raise ValueError('Розрахунок належить іншому користувачу')
    partner_name = SiteSettings.load().partner_name.strip()
    if not partner_name:
        raise PartnerNotConfigured()

    fields = {k: data[k] for k in _DATA_FIELDS if data.get(k) not in (None, '')}
    fields.update(clean_attribution(data))
    if user is not None and not getattr(user, 'is_authenticated', False):
        user = None

    if data.get('source') in LeadSource.values:
        source = data['source']
    elif calculation is not None:
        source = LeadSource.CALCULATOR
    elif listing is not None:
        source = LeadSource.LISTING
    else:
        source = LeadSource.LANDING
    if listing is not None:
        # С лотом подпись формирует сервер: клиентскому значению не доверяем.
        vehicle = listing.vehicle
        fields['vehicle_label'] = f'{vehicle.make} {vehicle.model}'.strip()[:150]

    now = timezone.now()
    with transaction.atomic():
        lead = Lead.objects.create(
            public_id=_next_public_id(now.year),
            user=user,
            phone=normalize_ua_phone(data.get('phone')),
            source=source,
            calculation=calculation,
            listing=listing,
            calculation_snapshot=build_calculation_snapshot(calculation),
            total_usd=calculation.total_usd if calculation else None,
            total_uah=calculation.total_uah if calculation else None,
            status=LeadStatus.NEW,
            consent_at=now,
            partner_name=partner_name,
            partner_consent_at=now,
            partner_consent_text=PARTNER_CONSENT_TEMPLATE.format(partner=partner_name)[:500],
            **fields,
        )
        LeadStatusChange.objects.create(lead=lead, from_status='', to_status=LeadStatus.NEW, changed_by=user)
        # Журнал згод (1.14): ті ж документи, що знімок на Lead; контакти не копіюються.
        record_consents(
            user, [ConsentDocument.LEAD_PROCESSING, ConsentDocument.PARTNER_TRANSFER],
            ConsentMethod.LEAD_FORM, lead=lead, partner_name=partner_name,
        )
        lead_id = lead.pk
        transaction.on_commit(lambda: _after_commit(lead_id))
    return lead


def change_status(lead: Lead, new_status: str, *, by, note: str = '', force: bool = False) -> Lead:
    """Меняет статус и пишет журнал. force — переоткрытие (только admin, решает вызывающий)."""
    if new_status not in LeadStatus.values:
        raise InvalidTransition(f'Невідомий статус: {new_status}')
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        old = locked.status
        if old == new_status:
            raise InvalidTransition('Статус не змінився')
        if not force and new_status not in ALLOWED_TRANSITIONS.get(old, set()):
            raise InvalidTransition(f'Перехід {old} -> {new_status} неприпустимий')
        locked.status = new_status
        fields = ['status', 'updated_at']
        if old == LeadStatus.NEW and new_status != LeadStatus.SPAM and locked.first_response_at is None:
            locked.first_response_at = timezone.now()
            fields.append('first_response_at')
        locked.save(update_fields=fields)
        LeadStatusChange.objects.create(
            lead=locked, from_status=old, to_status=new_status,
            changed_by=by if getattr(by, 'is_authenticated', False) else None,
            note=(f'force: {note}' if force else note)[:500],
        )
    lead.status = locked.status
    lead.first_response_at = locked.first_response_at
    lead.updated_at = locked.updated_at
    return lead


def allowed_transitions(status: str) -> list[str]:
    """Допустимые переходы из статуса в порядке LeadStatus (для кабинета, без дублирования на фронте)."""
    allowed = ALLOWED_TRANSITIONS.get(status, set())
    return [s for s in LeadStatus.values if s in allowed]


def take_lead(lead: Lead, by) -> Lead:
    """«Взяти в роботу»: назначает by и переводит new -> in_progress. Повтор своим - идемпотентен."""
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        if locked.assigned_to_id is not None and locked.assigned_to_id != by.pk:
            raise AlreadyTaken()
        if locked.status in (LeadStatus.DELIVERED, LeadStatus.REJECTED, LeadStatus.SPAM):
            raise InvalidTransition('Заявку закрито, взяти її в роботу не можна')
        if locked.assigned_to_id != by.pk:
            locked.assigned_to = by
            locked.save(update_fields=['assigned_to', 'updated_at'])
        if locked.status == LeadStatus.NEW:
            change_status(locked, LeadStatus.IN_PROGRESS, by=by)
    lead.assigned_to = locked.assigned_to
    lead.status = locked.status
    lead.first_response_at = locked.first_response_at
    lead.updated_at = locked.updated_at
    return lead


def _check_owner(locked: Lead, by, is_admin: bool) -> None:
    if not is_admin and locked.assigned_to_id not in (None, by.pk):
        raise AlreadyTaken()


def broker_change_status(lead: Lead, new_status: str, *, by, note: str = '', is_admin: bool = False) -> Lead:
    """Смена статуса из кабинета: чужую заявку (assigned_to другой) меняет только admin.
    Переход из new автоматически назначает заявку на by (как take). force не принимается."""
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        _check_owner(locked, by, is_admin)
        change_status(locked, new_status, by=by, note=note)
        if locked.assigned_to_id is None:
            locked.assigned_to = by
            locked.save(update_fields=['assigned_to', 'updated_at'])
    lead.assigned_to = locked.assigned_to
    lead.status = locked.status
    lead.first_response_at = locked.first_response_at
    lead.updated_at = locked.updated_at
    return lead


def set_partner_status(lead: Lead, value: str, *, by, is_admin: bool = False) -> Lead:
    """Статус партнёра вручную; каждое изменение пишется в журнал (статус заявки не меняется)."""
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        _check_owner(locked, by, is_admin)
        old = locked.partner_status
        if old != value:
            locked.partner_status = value
            locked.save(update_fields=['partner_status', 'updated_at'])
            LeadStatusChange.objects.create(
                lead=locked, from_status=locked.status, to_status=locked.status, changed_by=by,
                note=f'partner: {old or "—"} → {value or "—"}'[:500],
            )
    lead.partner_status = locked.partner_status
    lead.updated_at = locked.updated_at
    return lead
