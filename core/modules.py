"""Флаги включения замороженных модулей (задача 2.8). Единственная точка чтения: module_enabled().

Источник правды - переменные окружения (`LOTS_ENABLED` и др.), в админке не редактируются.
По умолчанию все модули выключены. Смена значения требует перезапуска backend.
"""
from django.conf import settings

# имя модуля -> имя настройки в core/settings.py
MODULE_FLAGS = {
    'lots': 'LOTS_ENABLED',
    'b2b': 'B2B_ENABLED',
    'dealers': 'DEALERS_ENABLED',
    'shipments': 'SHIPMENTS_ENABLED',
    'vin_reports': 'VIN_REPORTS_ENABLED',  # 3.2a: carVertical-отчёт и реестры Opendatabot
}


def module_enabled(name: str) -> bool:
    """True, если модуль включён. Неизвестное имя - KeyError (опечатка не должна открывать модуль)."""
    return bool(getattr(settings, MODULE_FLAGS[name], False))
