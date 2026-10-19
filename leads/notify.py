"""Сборка текста уведомления брокеру и in-app рассылка. Все значения от гостя экранируются."""
import html
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

from notifications.models import Notification
from notifications.services import create_notification

from .models import ContactMethod, Lead, LeadNotificationSettings

TELEGRAM_LIMIT = 4096
DIRECT = 'пряме'
# Поля, значения которых обрезаются при превышении лимита (комментарий и источник - первыми).
_GUEST_FIELDS = ('comment', 'source_details', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_content',
                 'referrer', 'page_url', 'car', 'contact_handle', 'name', 'email')


# Запасной текст, если шаблон в админке очищен (основной - в LeadNotificationSettings).
FALLBACK_TEMPLATE = '🆕 <b>Нова заявка #{id}</b>\n👤 {name}\n📞 {phone}\n🚗 {car}\n📍 Джерело: {source_details}\n💬 {comment}'


class MessageTooLong(Exception):
    """Шаблон из админки сам длиннее лимита Telegram."""


def tg_len(text: str) -> int:
    """Длина в единицах UTF-16, как считает Telegram."""
    return len(text.encode('utf-16-le')) // 2


def broker_chat_id() -> str:
    return (LeadNotificationSettings.get_solo().telegram_chat_id.strip()
            or getattr(settings, 'TELEGRAM_BROKER_CHAT_ID', '').strip())


def admin_url(lead: Lead) -> str:
    return settings.SITE_URL.rstrip('/') + reverse('admin:leads_lead_change', args=[lead.pk])


def cabinet_url(lead: Lead) -> str:
    return f'{settings.SITE_URL.rstrip("/")}/broker/leads/{lead.pk}'


def _money(value) -> str:
    return f'{Decimal(value):,.0f}'.replace(',', ' ') if value is not None else '—'


def _car(lead: Lead) -> str:
    if lead.vehicle_label:
        return lead.vehicle_label
    inputs = (lead.calculation_snapshot or {}).get('inputs_snapshot') or {}
    parts = [str(inputs.get(k)) for k in ('make', 'model', 'year') if inputs.get(k)]
    return ' '.join(parts) or '—'


def _source_details(lead: Lead) -> str:
    utm = lead.utm or {}
    parts = [str(utm[k]) for k in ('source', 'medium', 'campaign') if utm.get(k)]
    if parts:
        return ' / '.join(parts)
    return lead.referrer or DIRECT


def raw_context(lead: Lead) -> dict[str, str]:
    """Значения без экранирования. Ссылки гостя выводятся текстом, не <a>."""
    utm = lead.utm or {}
    method = ContactMethod(lead.contact_method).label if lead.contact_method in ContactMethod.values else ''
    return {
        'id': lead.public_id, 'name': lead.name, 'phone': lead.phone, 'email': lead.email,
        'contact_method': method, 'contact_handle': lead.contact_handle,
        'car': _car(lead), 'total_usd': _money(lead.total_usd), 'total_uah': _money(lead.total_uah),
        'source': lead.get_source_display(), 'source_details': _source_details(lead),
        'utm_source': str(utm.get('source', '')), 'utm_medium': str(utm.get('medium', '')),
        'utm_campaign': str(utm.get('campaign', '')), 'utm_content': str(utm.get('content', '')),
        'referrer': lead.referrer, 'page_url': lead.page_url, 'comment': lead.comment,
        'admin_url': admin_url(lead), 'cabinet_url': cabinet_url(lead),
    }


def _render(template: str, raw: dict[str, str], caps: dict[str, int]) -> str:
    safe = defaultdict(str)
    for key, value in raw.items():
        if key in caps:
            value = value[:caps[key]]
        safe[key] = html.escape(value)
    return template.format_map(safe)


def render_new_lead_text(lead: Lead, template: str) -> str:
    """Подставляет экранированные значения. Поля обрезаются ДО escape, пока текст не влезет в лимит.
    Неизвестный плейсхолдер даёт пустую строку. MessageTooLong, если не влезает и без полей гостя."""
    template = template if template.strip() else FALLBACK_TEMPLATE
    raw = raw_context(lead)
    caps = {k: 10 ** 6 for k in _GUEST_FIELDS}
    while True:
        text = _render(template, raw, caps)
        if tg_len(text) <= TELEGRAM_LIMIT:
            return text
        # Режем поля по очереди: сначала комментарий и источник.
        for key in _GUEST_FIELDS:
            current = min(caps[key], len(raw[key]))
            if current > 0:
                caps[key] = current // 2 if current > 40 else 0
                break
        else:
            raise MessageTooLong()


def notify_brokers_in_app(title: str, link: str, text: str = '') -> int:
    users = get_user_model().objects.filter(role='broker', is_active=True)
    count = 0
    for user_id in users.values_list('pk', flat=True):
        create_notification(user_id, Notification.Type.NEW_LEAD, title, text=text, link=link)
        count += 1
    return count
