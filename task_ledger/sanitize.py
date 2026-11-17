"""Безопасное представление аргументов задачи для FailedTask (8.9)."""
import re
import uuid

from django.conf import settings

from core.logging_filters import scrub

_DETAIL_RE = re.compile(r'DETAIL:.*', re.DOTALL)


def _max_len() -> int:
    return int(getattr(settings, 'FAILED_TASK_ARG_MAX_LEN', 64))


# 2.17 (E11): открыто хранятся только значения аргументов с этими именами (id объектов, флаги) -
# оператору нужно понять, КАКУЮ запись обрабатывала упавшая задача. Всё остальное - маска.
# Новое имя добавлять только если значение точно не ПДн (не email, телефон, токен, IBAN, VIN, текст).
SAFE_ARG_NAMES = frozenset({'lead_id', 'listing_id', 'user_id', 'seller_id', 'force'})


def mask(value) -> str:
    """Маска по умолчанию: тип и размер, без содержимого."""
    if isinstance(value, str):
        return f'<str:{len(value)}>'
    if isinstance(value, (int, float)):
        return f'<{type(value).__name__}>'
    try:
        size = len(value)
    except TypeError:
        return f'<{type(value).__name__}>'
    return f'<{type(value).__name__}:{size}>'


def safe_repr(value):
    """Значение из allowlist имён: int/bool/None/float - как есть; короткая строка без пробелов - после scrub;
    длинная или с пробелами - только <str:длина>; прочее - тип и длина."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > _max_len() or any(ch.isspace() for ch in value):
            return f'<str:{len(value)}>'
        return scrub(value)
    return mask(value)


def _is_plain_id(value) -> bool:
    """Для allowlist-имён открыто только число, строка из цифр или UUID; прочие строки (токены) - маска."""
    if not isinstance(value, str):
        return True
    if value.isascii() and value.isdigit():
        return True
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _arg(name, value):
    # None и bool хранятся открыто под ЛЮБЫМ именем: информации о данных пользователя они не несут.
    if value is None or isinstance(value, bool):
        return value
    if name in SAFE_ARG_NAMES and _is_plain_id(value):
        return safe_repr(value)
    return mask(value)


def safe_args(args, names=None) -> list:
    """names - имена параметров задачи по порядку (из сигнатуры); позиционный аргумент без имени - маска."""
    names = list(names or ())
    return [_arg(names[i] if i < len(names) else None, a) for i, a in enumerate(args or ())]


def safe_kwargs(kwargs) -> dict:
    return {str(k)[:50]: _arg(str(k), v) for k, v in (kwargs or {}).items()}


def safe_error(exc) -> str:
    from integrations.base import mask_secrets  # локально: integrations.base тянет модели/настройки
    text = _DETAIL_RE.sub('', str(exc))  # PG: «DETAIL:  Key (vin)=(...) already exists» - значения полей
    text = scrub(mask_secrets(text))
    limit = 1000
    return text if len(text) <= limit else text[:limit] + '…'
