"""Очистка источника визита (UTM, реферер, страница входа) - одна функция на все точки (задача 2.14).

Используют заявка брокеру (2.1), регистрация и подача объявления. Никогда не бросает исключений:
мусор в атрибуции не мешает отправке формы, он просто отбрасывается.
- UTM: только ключи source/medium/campaign/content, значения [буквы, цифры, _ . -] до 100 символов.
- referrer: только http/https и только origin (без пути, query и fragment - там бывают токены и ПДн).
- страницы: только путь своего сайта, без query и fragment.
"""
import re
from urllib.parse import urlsplit

UTM_KEYS = ('source', 'medium', 'campaign', 'content')
UTM_MAX_LEN = 100
URL_MAX_LEN = 500

_UTM_VALUE = re.compile(r'^[\w.\-]{1,100}$')
# Управляющие символы (в т.ч. \x00): PostgreSQL не сохраняет NUL в текст - регистрация упала бы с 500.
_CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def _clean_utm(value) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in UTM_KEYS:
        v = value.get(key)
        if isinstance(v, str):
            v = v.strip()
            if _UTM_VALUE.fullmatch(v):
                result[key] = v
    return result


def _clean_referrer(value) -> str:
    if not isinstance(value, str) or _CONTROL.search(value):
        return ''
    try:
        parts = urlsplit(value.strip())
        host, port = parts.hostname, parts.port
    except ValueError:
        return ''
    if parts.scheme not in ('http', 'https') or not host:
        return ''
    # Только хост и порт: логин и пароль из https://user:pass@host не сохраняются.
    return f'{parts.scheme}://{host}{f":{port}" if port else ""}'[:URL_MAX_LEN]


def _clean_page(value) -> str:
    if not isinstance(value, str) or _CONTROL.search(value):
        return ''
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ''
    if parts.scheme:
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            return ''
        path = parts.path or '/'
    elif parts.netloc:  # '//evil.test'
        return ''
    else:
        path = parts.path
    if not path.startswith('/') or path.startswith('//') or '\\' in path:
        return ''
    return path[:URL_MAX_LEN]


def clean_attribution(data) -> dict:
    """Тихо нормализует поля источника; никогда не бросает исключений.

    Возвращает ровно ключи utm, referrer, entry_page_url, page_url.
    """
    if not isinstance(data, dict):
        data = {}
    return {
        'utm': _clean_utm(data.get('utm')),
        'referrer': _clean_referrer(data.get('referrer')),
        'entry_page_url': _clean_page(data.get('entry_page_url')),
        'page_url': _clean_page(data.get('page_url')),
    }
