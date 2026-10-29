"""Агрегаты «Воронка за місяць». Только счётчики, без ПДн."""
import re
from datetime import UTC, datetime

from django.db.models import Count
from django.utils import timezone

from .models import Lead, PartnerStatus, Qualification

DIRECT = 'пряме'
NOT_SET = 'не вказано'
_MONTH = re.compile(r'^(\d{4})-(\d{2})$')


def parse_month(raw: str | None) -> tuple[int, int]:
    """?month=ГГГГ-ММ; при неверном значении - текущий месяц (UTC)."""
    match = _MONTH.match((raw or '').strip())
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 2000 <= year <= 2100 and 1 <= month <= 12:
            return year, month
    now = timezone.now().astimezone(UTC)
    return now.year, now.month


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=UTC)
    return start, end


def funnel(year: int, month: int) -> dict:
    start, end = month_bounds(year, month)
    qs = Lead.objects.filter(created_at__gte=start, created_at__lt=end)

    by_source: dict[str, int] = {}
    for row in qs.values('utm__source').annotate(n=Count('pk')):
        value = row['utm__source']
        key = value if isinstance(value, str) and value else DIRECT
        by_source[key] = by_source.get(key, 0) + row['n']

    partner_counts = {row['partner_status']: row['n'] for row in qs.values('partner_status').annotate(n=Count('pk'))}
    by_partner = [(NOT_SET, partner_counts.get('', 0))] + [
        (label, partner_counts.get(value, 0)) for value, label in PartnerStatus.choices]

    return {
        'month': f'{year:04d}-{month:02d}',
        'total': qs.count(),
        'hot': qs.filter(qualification=Qualification.HOT).count(),
        'by_source': sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0])),
        'by_partner_status': by_partner,
    }
