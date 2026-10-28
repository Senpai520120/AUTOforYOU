"""Публичные идентификаторы веб-аналитики из .env (задача 3.5).

ID счётчиков публичны по природе (они видны в коде любой страницы), секретов здесь нет.
Значение, не прошедшее проверку формата, считается незаданным: провайдер выключен, ничего не вставляется
на страницу и не попадает в CSP. Тот же шаблон проверяет фронт (`frontend/lib/analytics/`) и nginx.
"""
import re

from django.conf import settings

GA4_ID_RE = re.compile(r'^G-[A-Z0-9]{4,20}$')
CLOUDFLARE_TOKEN_RE = re.compile(r'^[A-Za-z0-9]{16,64}$')


def _clean(name: str, pattern: re.Pattern) -> str:
    value = str(getattr(settings, name, '') or '').strip()
    return value if pattern.match(value) else ''


def ga4_measurement_id() -> str:
    return _clean('GA4_MEASUREMENT_ID', GA4_ID_RE)


def cloudflare_analytics_token() -> str:
    return _clean('CLOUDFLARE_ANALYTICS_TOKEN', CLOUDFLARE_TOKEN_RE)


def public_analytics() -> dict:
    """Только непустые и валидные ID. Пустой объект = аналитики нет."""
    out = {}
    if ga4_measurement_id():
        out['ga4_id'] = ga4_measurement_id()
    if cloudflare_analytics_token():
        out['cloudflare_token'] = cloudflare_analytics_token()
    return out


def mask(value: str) -> str:
    """G-ABCD123456 -> G-AB…56; для статуса интеграций (целиком ID не показываем)."""
    if len(value) <= 6:
        return '…'
    return f'{value[:4]}…{value[-2:]}'
