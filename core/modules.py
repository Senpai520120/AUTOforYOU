"""Флаги замороженных модулей (2.8, решение владельца по бизнес-плану). Одна точка чтения.

Источник правды - .env (не админка): смена значения требует перезапуска backend.
"""
from django.conf import settings

MODULE_SETTINGS = {
    'lots': 'LOTS_ENABLED',          # каталог лотов /listings, импорт лотов, /vehicles/
    'b2b': 'B2B_ENABLED',            # B2B-доска и выдача wholesale-листингов
    'dealers': 'DEALERS_ENABLED',    # заявки дилеров
    'shipments': 'SHIPMENTS_ENABLED',  # контейнеры и трекинг
}


def module_enabled(name: str) -> bool:
    return bool(getattr(settings, MODULE_SETTINGS[name], False))


def module_flags() -> dict:
    """Для GET /api/v1/site-settings/: lots_enabled, b2b_enabled, dealers_enabled, shipments_enabled."""
    return {f'{name}_enabled': module_enabled(name) for name in MODULE_SETTINGS}
