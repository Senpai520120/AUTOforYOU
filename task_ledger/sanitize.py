"""Безопасное представление аргументов задачи для FailedTask (8.9)."""
from django.conf import settings

from core.logging_filters import scrub


def _max_len() -> int:
    return int(getattr(settings, 'FAILED_TASK_ARG_MAX_LEN', 64))


def safe_repr(value):
    """int/bool/None - как есть; короткая строка без пробелов (id, код) - после scrub;
    длинная или с пробелами (текст письма, сообщения, имя) - только <str:длина>; прочее - тип и длина."""
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        if len(value) > _max_len() or any(ch.isspace() for ch in value):
            return f'<str:{len(value)}>'
        return scrub(value)
    try:
        size = len(value)
    except TypeError:
        return f'<{type(value).__name__}>'
    return f'<{type(value).__name__}:{size}>'


def safe_args(args) -> list:
    return [safe_repr(a) for a in (args or ())]


def safe_kwargs(kwargs) -> dict:
    return {str(k)[:50]: safe_repr(v) for k, v in (kwargs or {}).items()}


def safe_error(exc) -> str:
    text = scrub(str(exc))
    limit = 1000
    return text if len(text) <= limit else text[:limit] + '…'
