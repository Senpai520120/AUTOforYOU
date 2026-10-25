"""Бизнес-логика заявок: создание, смена статуса, номер AFY-ГГГГ-NNNN, квалификация, журнал в группу."""
import calendar
import html
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from metrics import services as metrics_services
from metrics.models import MetricKey
from site_settings.models import SiteSettings
from users.consents import record_consents
from users.models import ConsentDocument, ConsentMethod

from .models import (
    Lead,
    LeadCounter,
    LeadJournalSettings,
    LeadPartnerStatusChange,
    LeadSource,
    LeadStatus,
    LeadStatusChange,
    Qualification,
)
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
    """Личное уведомление брокеру (2.2). Без ПДн в логе."""
    from .tasks import notify_broker_new_lead
    notify_broker_new_lead.delay(lead_id)


def notify_journal(lead_id: int) -> None:
    """Журнал в группу с партнёром (2.15): отдельная отправка, не влияет на уведомление брокеру."""
    from .tasks import send_journal_task
    send_journal_task.delay(lead_id)


def record_metric(event: str) -> None:
    """Серверные счётчики (8.7): 'lead_created' -> metrics.lead. Не падает, без ПДн."""
    if event == 'lead_created':
        metrics_services.record_metric(MetricKey.LEAD)
    else:
        logger.info('metric event=%s', event)


def _after_commit(lead_id: int) -> None:
    # Сбой уведомления не должен ронять создание заявки; в лог только lead_id.
    for hook, args in ((notify_new_lead, (lead_id,)), (notify_journal, (lead_id,)), (record_metric, ('lead_created',))):
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


def add_months(dt: datetime, months: int) -> datetime:
    """dt + months месяцев; если такого дня нет (31 августа + 6), берётся последний день месяца."""
    index = dt.month - 1 + months
    year, month = dt.year + index // 12, index % 12 + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


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
    journal_cfg = LeadJournalSettings.get_solo()
    budget = fields.get('budget_usd')
    if budget is not None:
        # Автоматический ответ на вопрос о бюджете; брокер может поправить вручную.
        fields['q_budget_ok'] = Decimal(str(budget)) >= journal_cfg.hot_budget_usd
    with transaction.atomic():
        lead = Lead.objects.create(
            attribution_until=add_months(now, journal_cfg.attribution_window_months),
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
            LeadPartnerStatusChange.objects.create(lead=locked, from_status=old, to_status=value, changed_by=by)
    lead.partner_status = locked.partner_status
    lead.updated_at = locked.updated_at
    return lead


Q_FIELDS = ('q_budget_ok', 'q_term_ok', 'q_knows_repair', 'q_ready_deposit')


def compute_qualification(lead: Lead, cfg: LeadJournalSettings | None = None) -> str:
    """hot: «так» не меньше hot_min_score из четырёх; cold: ответили на все, но меньше; иначе unrated."""
    cfg = cfg or LeadJournalSettings.get_solo()
    answers = [getattr(lead, f) for f in Q_FIELDS]
    if any(a is None for a in answers):
        return Qualification.UNRATED
    return Qualification.HOT if sum(answers) >= cfg.hot_min_score else Qualification.COLD


def qualify_lead(lead: Lead, answers: dict, *, by, is_admin: bool = False) -> Lead:
    """Записывает ответы (ключи Q_FIELDS; None очищает) и пересчитывает qualification по порогам из админки.
    Если на бюджет не ответили, а он известен - ответ считается автоматически."""
    unknown = set(answers) - set(Q_FIELDS)
    if unknown:
        raise ValueError(f'Невідомі поля: {sorted(unknown)}')
    cfg = LeadJournalSettings.get_solo()
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        _check_owner(locked, by, is_admin)
        for key, value in answers.items():
            setattr(locked, key, value)
        if locked.q_budget_ok is None and locked.budget_usd is not None:
            locked.q_budget_ok = locked.budget_usd >= cfg.hot_budget_usd
        locked.qualification = compute_qualification(locked, cfg)
        locked.save(update_fields=[*Q_FIELDS, 'qualification', 'updated_at'])
    for f in (*Q_FIELDS, 'qualification', 'updated_at'):
        setattr(lead, f, getattr(locked, f))
    return lead


_PHONE_LIKE = re.compile(r'\d(?:[\s\-().]*\d){4,}')
NOT_SET = 'не вказано'


def _journal_safe(value: str) -> str:
    """Свободный текст в группу: 5+ цифр подряд (с пробелами, дефисами, скобками), @ или e-mail -> «не вказано»."""
    value = (value or '').strip()
    if not value or '@' in value or _PHONE_LIKE.search(value):
        return NOT_SET
    return value[:100]


def _journal_car(lead: Lead) -> str:
    """Марка/модель только из лота или расчёта, но не из клиентского vehicle_label."""
    if lead.listing_id:
        vehicle = lead.listing.vehicle
        return _journal_safe(f'{vehicle.make} {vehicle.model}')
    inputs = (lead.calculation_snapshot or {}).get('inputs_snapshot') or {}
    parts = [str(inputs.get(k)) for k in ('make', 'model', 'year') if inputs.get(k)]
    return _journal_safe(' '.join(parts))


def journal_text(lead: Lead) -> str:
    """Текст для группы с партнёром по белому списку: AFY-ID, авто, бюджет, город, время UTC.
    Имя, телефон, email, комментарий и ссылки сюда не попадают никогда."""
    from . import notify
    budget = f'${notify._money(lead.budget_usd)}' if lead.budget_usd is not None else NOT_SET
    when = lead.created_at.astimezone(UTC).strftime('%Y-%m-%d %H:%M')
    lines = [
        f'🧾 <b>Заявка {html.escape(lead.public_id)}</b>',
        f'🚗 {html.escape(_journal_car(lead))}',
        f'💵 Бюджет: {html.escape(budget)}',
        f'📍 Місто: {html.escape(_journal_safe(lead.city))}',
        f'🕒 {when} UTC',
    ]
    return '\n'.join(lines)


SENDING_STALE = timedelta(minutes=5)


def send_journal_message(lead_id: int) -> str:
    """Шлёт запись в LEAD_JOURNAL_CHAT_ID и сохраняет journal_message_id.
    Возврат: sent / already_sent / in_progress / disabled / not_found / failed (failed - повторить).
    Отправка идёт вне транзакции: перед ней атомарно ставится метка journal_sending_at.
    Исключения не пробрасываются, в лог идут только lead_id и класс ошибки."""
    from django.conf import settings

    from telegram_bot import sender
    from telegram_bot.provider import telegram_configured

    chat_id = str(getattr(settings, 'LEAD_JOURNAL_CHAT_ID', '') or '').strip()
    if not chat_id or not telegram_configured():
        return 'disabled'
    now = timezone.now()
    claimed = Lead.objects.filter(pk=lead_id, journal_message_id__isnull=True).filter(
        Q(journal_sending_at__isnull=True) | Q(journal_sending_at__lt=now - SENDING_STALE),
    ).update(journal_sending_at=now)
    if not claimed:
        lead = Lead.objects.filter(pk=lead_id).values('journal_message_id').first()
        if lead is None:
            return 'not_found'
        return 'already_sent' if lead['journal_message_id'] is not None else 'in_progress'
    try:
        lead = Lead.objects.select_related('listing__vehicle').get(pk=lead_id)
        result = sender.send_message(chat_id, journal_text(lead), demo_body=f'lead #{lead_id}')
        if not result.ok or result.message_id is None:
            logger.warning('lead.journal lead_id=%s reason=%s', lead_id, result.reason or 'no_message_id')
            raise RuntimeError('send_failed')
        Lead.objects.filter(pk=lead_id).update(
            journal_message_id=result.message_id, journal_sent_at=timezone.now(), journal_sending_at=None)
        return 'sent'
    except Exception as exc:
        if str(exc) != 'send_failed':
            logger.warning('lead.journal lead_id=%s error=%s', lead_id, type(exc).__name__)
        Lead.objects.filter(pk=lead_id).update(journal_sending_at=None)
        return 'failed'


# ─── Обезличивание при удалении аккаунта (1.8) ─────────────────────────────────

def anonymize_user_leads(user) -> int:
    """Стирает контакты в заявках пользователя и отвязывает их от аккаунта.

    Не трогает то, что нужно для сверки с партнёром и доказательства согласий (2.15):
    public_id, partner_name/partner_status, journal_message_id, attribution_until,
    calculation_snapshot, UTM/реферер/страницы, журналы статусов и экспорта, ConsentRecord.
    Возвращает число заявок.
    """
    from users.display import DELETED_NAME

    return Lead.objects.filter(user=user).update(
        name=DELETED_NAME, phone='', email='', contact_handle='', comment='', user=None,
    )
