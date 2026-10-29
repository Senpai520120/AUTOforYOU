"""Валидаторы заявки: телефон UA и тихая нормализация атрибуции."""
import re

from django.core.exceptions import ValidationError

# Очистка источника визита - общая для заявки, регистрации и объявления (2.14): core/attribution.py.
from core.attribution import URL_MAX_LEN, UTM_KEYS, UTM_MAX_LEN, clean_attribution  # noqa: F401

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
