"""Валидаторы заявки: телефон UA и тихая нормализация атрибуции."""
import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

UTM_KEYS = ('source', 'medium', 'campaign', 'content')
UTM_MAX_LEN = 100
URL_MAX_LEN = 500

_UTM_VALUE = re.compile(r'^[\w.\-]{1,100}$')
_PHONE_JUNK = re.compile(r'[\s()\-]')


def normalize_ua_phone(value) -> str:
    """+380XXXXXXXXX | 380XXXXXXXXX | 0XXXXXXXXX (пробелы, скобки, дефисы) -> +380XXXXXXXXX."""
    raw = _PHONE_JUNK.sub('', str(value or ''))
    if raw.startswith('+380'):
        digits = raw[4:]
    elif raw.startswith('380'):
        digits = raw[3:]
    elif raw.startswith('0'):
        digits = raw[1:]
    else:
        digits = None
    if (digits is None or not (digits.isascii() and digits.isdigit() and len(digits) == 9)
            or digits.startswith('0')):
        raise ValidationError('Вкажіть номер у форматі +380XXXXXXXXX.')
    return f'+380{digits}'


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
    if not isinstance(value, str):
        return ''
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ''
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        return ''
    return f'{parts.scheme}://{parts.netloc}'[:URL_MAX_LEN]


def _clean_page(value) -> str:
    if not isinstance(value, str):
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
