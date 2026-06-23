"""
Кэш тарифных справочников.

Редко меняющиеся таблицы (AuctionFeeTier, ExchangeRate, …) кэшируются
целиком. Расчёт делает in-memory фильтрацию — 0 запросов к БД на cache hit.

Инвалидация — через post_save/post_delete сигналы (pricing/signals.py).
Изменил ставку в админке → следующий расчёт сразу использует новую.
"""
from django.core.cache import cache

_TTL = 60 * 60 * 24  # 24 ч — тарифы меняются редко

KEYS = {
    'tiers':    'pricing:auction_fee_tiers',
    'fixed':    'pricing:auction_fixed_fees',
    'us_land':  'pricing:us_land_routes',
    'ocean':    'pricing:ocean_freight',
    'eu_to_ua': 'pricing:eu_to_ua',
    'exchange': 'pricing:exchange_rates',
    'excise':   'pricing:customs_excise',
    'pension':  'pricing:pension_brackets',
}


def _load(key, loader):
    result = cache.get(key)
    if result is None:
        result = loader()
        cache.set(key, result, _TTL)
    return result


def get_auction_fee_tiers():
    from .models import AuctionFeeTier
    return _load(KEYS['tiers'], lambda: list(AuctionFeeTier.objects.all()))


def get_auction_fixed_fees():
    from .models import AuctionFixedFee
    return _load(KEYS['fixed'], lambda: list(AuctionFixedFee.objects.all()))


def get_us_land_routes():
    from .models import UsLandRoute
    return _load(KEYS['us_land'], lambda: list(UsLandRoute.objects.all()))


def get_ocean_freight():
    from .models import OceanFreightRate
    return _load(KEYS['ocean'], lambda: list(OceanFreightRate.objects.all()))


def get_eu_to_ua():
    from .models import EuToUaDeliveryRate
    return _load(KEYS['eu_to_ua'], lambda: list(EuToUaDeliveryRate.objects.all()))


def get_exchange_rates():
    from .models import ExchangeRate
    return _load(KEYS['exchange'], lambda: list(ExchangeRate.objects.all()))


def get_customs_excise():
    from .models import CustomsExciseRate
    return _load(KEYS['excise'], lambda: list(CustomsExciseRate.objects.all()))


def get_pension_brackets():
    from .models import PensionFundBracket
    return _load(KEYS['pension'], lambda: list(PensionFundBracket.objects.all()))


def invalidate(key_name: str):
    cache.delete(KEYS[key_name])


def invalidate_all():
    cache.delete_many(list(KEYS.values()))
