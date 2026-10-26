"""Публичная конфигурация сайта из .env и данных (6.4): лимиты объявлений, имя бота, признак демо-тарифов.

Только несекретные значения. Отдаётся в GET /api/v1/site-settings/ поверх кэша модели: значения окружения
дешёвые и не должны залипать в кэше; признак демо-тарифов берётся из кэша тарифов (сбрасывается сигналами).
"""
from django.conf import settings

ENV_FIELDS = (
    'local_listing_max_active', 'local_listing_expiry_days', 'local_listing_max_photos',
    'local_listing_photo_max_size_mb', 'telegram_bot_username', 'tariffs_demo',
)


def tariffs_demo() -> bool:
    """Тот же признак, что у демо-баннера калькулятора (2.6): есть непроверенные тарифы или курс из сида."""
    from django.utils import timezone

    from pricing import cache as pricing_cache
    from pricing.calculator import catalog_is_demo
    try:
        return catalog_is_demo(pricing_cache.get_catalog(), timezone.localdate())
    except Exception:  # пометка «Тестові тарифи» не должна ронять страницу; безопаснее показать её
        return True


def env_config() -> dict:
    return {
        'local_listing_max_active': settings.LOCAL_LISTING_MAX_ACTIVE,
        'local_listing_expiry_days': settings.LOCAL_LISTING_EXPIRY_DAYS,
        'local_listing_max_photos': settings.LOCAL_LISTING_MAX_PHOTOS,
        'local_listing_photo_max_size_mb': settings.LOCAL_LISTING_PHOTO_MAX_SIZE_MB,
        'telegram_bot_username': (settings.TELEGRAM_BOT_USERNAME or '').strip().lstrip('@'),
        'tariffs_demo': tariffs_demo(),
    }
