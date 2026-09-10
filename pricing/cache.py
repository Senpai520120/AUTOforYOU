"""
Кэш тарифных справочников.

Редко меняющиеся таблицы (AuctionFeeTier, ExchangeRate, …) кэшируются
целиком. Расчёт делает in-memory фильтрацию — 0 запросов к БД на cache hit.

Инвалидация — через post_save/post_delete сигналы (pricing/signals.py).
Изменил ставку в админке → следующий расчёт сразу использует новую.
"""
import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _ttl() -> int:
    """
    LocMemCache живёт в памяти одного процесса, и сигналы инвалидации из
    соседнего воркера туда не долетают. При GUNICORN_WORKERS=3 правка ставки
    в админке обновляла кэш только того воркера, который обработал запрос, —
    два остальных сутки отдавали старые тарифы, ничем себя не выдавая.

    Короткий TTL — единственная страховка, пока кэш не общий.
    """
    backend = settings.CACHES.get('default', {}).get('BACKEND', '')
    if 'locmem' in backend.lower():
        return 30
    return 60 * 60 * 24  # 24 ч — тарифы меняются редко

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
    try:
        result = cache.get(key)
    except Exception:
        # Redis недоступен — считаем из БД. Расчёт не должен падать из-за кэша.
        logger.warning('pricing.cache: чтение %s не удалось, читаем из БД', key, exc_info=True)
        return loader()

    if result is None:
        result = loader()
        try:
            cache.set(key, result, _ttl())
        except Exception:
            logger.warning('pricing.cache: запись %s не удалась', key, exc_info=True)
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
    """
    Инвалидация не должна ронять вызывающий код.

    seed_rates падал с ConnectionError, если .env указывал на redis:6379, а
    команду запускали вне Docker: сигнал post_save дергал cache.delete(),
    и django-redis пробрасывал исключение наружу. В docker/entrypoint.sh это
    было замаскировано `|| true` — то есть при недоступном Redis сиды тихо
    не применялись, и никто об этом не узнавал.
    """
    try:
        cache.delete(KEYS[key_name])
    except Exception:
        logger.warning('pricing.cache: инвалидация %s не удалась', key_name, exc_info=True)


def invalidate_all():
    try:
        cache.delete_many(list(KEYS.values()))
    except Exception:
        logger.warning('pricing.cache: полная инвалидация не удалась', exc_info=True)
