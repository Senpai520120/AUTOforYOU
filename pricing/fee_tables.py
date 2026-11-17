"""Сетки сборов аукционов из публичных страниц (9.51): чтение CSV, посев/обновление БД и сверка БД с CSV.

CSV лежат в `pricing/data/` и содержат ТОЛЬКО ставки, снятые с публичных страниц Copart и IAA
(`source_url` и `checked_at` в каждой строке). Ставки без публичного источника (брокер, IAA licensed,
IAA environmental) остаются baseline в `seed_auction_fees` и в сверку не попадают.

Модуль не ходит в сеть: CSV обновляет человек, раз в квартал, читая страницы (docs/LAUNCH_CHECKLIST.md).
"""
import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from .models import AuctionFeeTier, AuctionFixedFee

DATA_DIR = Path(__file__).resolve().parent / 'data'
TIERS_CSV = DATA_DIR / 'auction_fee_tiers.csv'
FIXED_CSV = DATA_DIR / 'auction_fixed_fees.csv'


def _dec(value: str):
    return Decimal(value) if value not in ('', None) else None


def _date(value: str):
    return date.fromisoformat(value) if value else None


def load_tier_rows(path: Path = TIERS_CSV) -> list[dict]:
    with open(path, newline='', encoding='utf8') as fh:
        return [{
            'auction': r['auction'], 'member_type': r['member_type'], 'payment_type': r['payment_type'],
            'title_type': r['title_type'], 'bid_min': _dec(r['bid_min']), 'bid_max': _dec(r['bid_max']),
            'fee_flat': _dec(r['fee_flat']), 'fee_percent': _dec(r['fee_percent']),
            'source_url': r['source_url'], 'checked_at': _date(r['checked_at']), 'valid_from': _date(r['valid_from']),
        } for r in csv.DictReader(fh)]


def load_fixed_rows(path: Path = FIXED_CSV) -> list[dict]:
    with open(path, newline='', encoding='utf8') as fh:
        return [{
            'auction': r['auction'], 'fee_type': r['fee_type'], 'title_type': r['title_type'],
            'bid_min': _dec(r['bid_min']), 'bid_max': _dec(r['bid_max']), 'amount': _dec(r['amount']),
            'source_url': r['source_url'], 'checked_at': _date(r['checked_at']), 'valid_from': _date(r['valid_from']),
        } for r in csv.DictReader(fh)]


# Поля-значения: по ним строка БД считается «той же», что строка CSV (valid_from и дата сверки не сравниваются).
TIER_KEY = ('auction', 'member_type', 'payment_type', 'title_type', 'bid_min')
TIER_VALUES = ('bid_max', 'fee_flat', 'fee_percent')
FIXED_KEY = ('auction', 'fee_type', 'title_type', 'bid_min')
FIXED_VALUES = ('bid_max', 'amount')

# Группа = всё, что CSV обещает описать целиком: лишняя действующая запись группы - расхождение.
TIER_GROUP = ('auction', 'member_type', 'payment_type')
FIXED_GROUP = ('auction', 'fee_type')


def _active_on(qs, on_date: date):
    from django.db.models import Q
    return qs.filter(valid_from__lte=on_date).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))


def _sig(obj_or_row, key_fields, value_fields):
    get = obj_or_row.get if isinstance(obj_or_row, dict) else (lambda k: getattr(obj_or_row, k))
    return tuple(get(f) for f in (*key_fields, *value_fields))


@dataclass
class Discrepancy:
    kind: str       # 'missing' (в CSV есть, в БД нет / другое значение) | 'extra' (в БД действует, в CSV нет)
    model: str
    text: str

    def __str__(self):
        return f'[{self.kind}] {self.model}: {self.text}'


def _compare(model, model_name, rows, key_fields, value_fields, group_fields, on_date):
    groups = {tuple(r[f] for f in group_fields) for r in rows}
    wanted = {_sig(r, key_fields, value_fields): r for r in rows}
    active = [o for o in _active_on(model.objects.all(), on_date)
              if tuple(getattr(o, f) for f in group_fields) in groups]
    have = {_sig(o, key_fields, value_fields): o for o in active}
    out = []
    for sig, row in wanted.items():
        if sig not in have and row['valid_from'] <= on_date:
            out.append(Discrepancy('missing', model_name, f'{dict(zip((*key_fields, *value_fields), sig))}'))
    for sig, obj in have.items():
        if sig not in wanted:
            out.append(Discrepancy('extra', model_name, f'id={obj.pk} {obj}'))
    return out


def compare_with_db(on_date: date | None = None, tier_rows=None, fixed_rows=None) -> list[Discrepancy]:
    """Только чтение: действующие на дату записи БД против CSV. Пусто - всё совпало."""
    on_date = on_date or date.today()
    tier_rows = load_tier_rows() if tier_rows is None else tier_rows
    fixed_rows = load_fixed_rows() if fixed_rows is None else fixed_rows
    return [
        *_compare(AuctionFeeTier, 'AuctionFeeTier', tier_rows, TIER_KEY, TIER_VALUES, TIER_GROUP, on_date),
        *_compare(AuctionFixedFee, 'AuctionFixedFee', fixed_rows, FIXED_KEY, FIXED_VALUES, FIXED_GROUP, on_date),
    ]


def _close_and_create(model, rows, key_fields, value_fields, group_fields, create_fields):
    """Для каждой группы CSV: действующие записи, не совпавшие с CSV, закрываются датой «по», недостающие создаются.

    Ничего не удаляется: старые ставки остаются в истории (valid_to), старые расчёты читают снимок.
    Возвращает (закрыто, создано).
    """
    closed = created = 0
    by_group: dict[tuple, list[dict]] = {}
    for r in rows:
        by_group.setdefault(tuple(r[f] for f in group_fields), []).append(r)
    for group, grows in by_group.items():
        new_from = min(r['valid_from'] for r in grows)
        wanted = {_sig(r, key_fields, value_fields) for r in grows}
        existing = _active_on(model.objects.filter(**dict(zip(group_fields, group))), date.max)
        have = set()
        for obj in existing:
            sig = _sig(obj, key_fields, value_fields)
            if sig in wanted and sig not in have:
                have.add(sig)
                continue
            cutoff = max(obj.valid_from, new_from - timedelta(days=1))
            if obj.valid_to is None or obj.valid_to > cutoff:
                obj.valid_to = cutoff
                obj.save(update_fields=['valid_to'])
                closed += 1
        for r in grows:
            if _sig(r, key_fields, value_fields) in have:
                continue
            model.objects.create(**{f: r[f] for f in create_fields})
            created += 1
    return closed, created


TIER_CREATE = (*TIER_KEY, *TIER_VALUES, 'source_url', 'checked_at', 'valid_from')
FIXED_CREATE = (*FIXED_KEY, *FIXED_VALUES, 'source_url', 'checked_at', 'valid_from')


@transaction.atomic
def apply_csv(tier_rows=None, fixed_rows=None) -> dict:
    """Приводит БД к CSV (режим `seed_auction_fees --update`). Совпавшие записи не трогает."""
    tier_rows = load_tier_rows() if tier_rows is None else tier_rows
    fixed_rows = load_fixed_rows() if fixed_rows is None else fixed_rows
    tc, tn = _close_and_create(AuctionFeeTier, tier_rows, TIER_KEY, TIER_VALUES, TIER_GROUP, TIER_CREATE)
    fc, fn = _close_and_create(AuctionFixedFee, fixed_rows, FIXED_KEY, FIXED_VALUES, FIXED_GROUP, FIXED_CREATE)
    return {'tiers_closed': tc, 'tiers_created': tn, 'fixed_closed': fc, 'fixed_created': fn}
