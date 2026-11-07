"""CSV-выгрузка заявок для сверки с партнёром. Без ПДн: имя, телефон, email, комментарий, referrer и URL не выводятся."""
import csv
import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta

from django.http import StreamingHttpResponse

from .models import Lead, LeadExportLog

logger = logging.getLogger('audit')

COLUMNS = [
    'public_id', 'created_at_utc', 'status', 'partner_status', 'qualification', 'utm_source', 'utm_campaign',
    'source', 'city', 'budget_usd', 'partner_consent_at_utc', 'partner_name', 'attribution_until_utc',
]
_DANGEROUS = ('=', '+', '-', '@', '\t', '\r')


def csv_safe(value) -> str:
    """Защита от CSV-инъекции: ячейка, начинающаяся с = + - @ (или tab/CR), получает префикс '."""
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(_DANGEROUS) or text.startswith(_DANGEROUS) else text


def _dt(value) -> str:
    return value.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S') if value else ''


def _utm(lead: Lead, key: str):
    value = (lead.utm or {}).get(key, '')
    return value if isinstance(value, str) else ''


def lead_row(lead: Lead) -> list[str]:
    return [csv_safe(v) for v in (
        lead.public_id, _dt(lead.created_at), lead.status, lead.partner_status, lead.qualification,
        _utm(lead, 'source'), _utm(lead, 'campaign'), lead.source, lead.city,
        '' if lead.budget_usd is None else f'{lead.budget_usd:.2f}',
        _dt(lead.partner_consent_at), lead.partner_name, _dt(lead.attribution_until),
    )]


class _Echo:
    def write(self, value):
        return value


def iter_csv(queryset) -> Iterator[str]:
    writer = csv.writer(_Echo())
    yield '﻿' + writer.writerow(COLUMNS)
    for lead in queryset.only(
        'public_id', 'created_at', 'status', 'partner_status', 'qualification', 'utm', 'source', 'city',
        'budget_usd', 'partner_consent_at', 'partner_name', 'attribution_until',
    ).iterator(chunk_size=500):
        yield writer.writerow(lead_row(lead))


def parse_day(raw: str) -> date:
    return date.fromisoformat(raw)


def filter_leads(status: str = '', date_from: date | None = None, date_to: date | None = None):
    """Период включает обе границы (по UTC)."""
    qs = Lead.objects.all()
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(created_at__gte=datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to:
        qs = qs.filter(created_at__lt=datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC))
    return qs.order_by('created_at', 'pk')


def csv_response(queryset, *, user, channel: str, filters: dict) -> StreamingHttpResponse:
    """Потоковый ответ + запись аудита (кто, когда, фильтр, число строк)."""
    count = queryset.count()
    LeadExportLog.objects.create(
        user=user if getattr(user, 'is_authenticated', False) else None,
        channel=channel, filters=filters, row_count=count)
    logger.info('lead.export user_id=%s channel=%s rows=%s', getattr(user, 'pk', None), channel, count)
    response = StreamingHttpResponse(iter_csv(queryset), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="leads-{datetime.now(UTC):%Y%m%d-%H%M}.csv"'
    response['Cache-Control'] = 'no-store'
    return response
