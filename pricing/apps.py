from django.apps import AppConfig
from django.core.checks import Tags, Warning, register


class PricingConfig(AppConfig):
    name = 'pricing'

    def ready(self):
        import pricing.signals  # noqa: F401


@register(Tags.database)
def check_auction_fee_tier_overlaps(app_configs=None, databases=None, **kwargs):
    """2.17 (E9): перечисляет уже существующие пересекающиеся тиры buyer fee (только вывод).

    Запуск: `python manage.py check --database default`. Данные не меняет.
    """
    if not databases:  # как встроенные database-проверки Django: только при `check --database`
        return []
    from .models import AuctionFeeTier, tiers_overlap
    warnings = []
    for alias in databases:
        warnings.extend(_tier_overlap_warnings(AuctionFeeTier, tiers_overlap, alias))
    return warnings


def _tier_overlap_warnings(AuctionFeeTier, tiers_overlap, alias):
    from django.db.utils import DatabaseError

    try:
        tiers = list(AuctionFeeTier.objects.using(alias).order_by('auction', 'member_type', 'payment_type', 'title_type', 'bid_min', 'pk'))
    except DatabaseError:  # таблицы ещё нет (до migrate)
        return []
    warnings = []
    for i, a in enumerate(tiers):
        for b in tiers[i + 1:]:
            if tiers_overlap(a, b):
                warnings.append(Warning(
                    f'Тири buyer fee перетинаються: id={a.pk} (${a.bid_min}-{a.bid_max or "∞"}, з {a.valid_from}) '
                    f'та id={b.pk} (${b.bid_min}-{b.bid_max or "∞"}, з {b.valid_from}).',
                    hint='Виправте діапазон або закрийте старий запис датою «по» в адмінці.',
                    obj=a, id='pricing.W001',
                ))
    return warnings
