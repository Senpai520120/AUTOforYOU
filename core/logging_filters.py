"""Фильтр персональных данных в логах (задача 7.2, 12-S8, 01-S14, 23-D107).

`scrub(text)` маскирует email, телефоны, секреты в query-строках и JSON, заголовки
Authorization/Cookie. Её же использует мониторинг ошибок (7.6) в before_send.
`PiiScrubFilter` форматирует запись и заменяет msg/args - запись не выбрасывается.
`RequestPathFilter` убирает query-строку из записей django.request (ошибки 4xx/5xx).
"""
import logging
import re

MASK = '***'

_SECRET_NAMES = r'(?:token|key|signature|password|secret|code|apikey|api_key|access|refresh|uid|sessionid|csrftoken|jwt)'
# Имена людей в JSON ("first_name": "...") - только в JSON-ключах, не в тексте.
_NAME_KEYS = r'(?:first_name|last_name|full_name|name|phone|email|contact_phone|contact_handle)'

_PATTERNS = [
    # Заголовки и Bearer-токены
    (re.compile(r'(?i)(?:\b|_)(authorization|cookie|set-cookie)\b(["\']?\s*[:=]\s*["\']?)[^"\'\n]+'), rf'\1\2{MASK}'),
    # голый JWT (eyJ...header.payload.signature)
    (re.compile(r'\beyJ[\w-]+\.[\w-]+\.[\w-]+'), MASK),
    (re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+'), f'Bearer {MASK}'),
    # name=value в query-строках и формах
    (re.compile(rf'(?i)\b(\w*{_SECRET_NAMES}\w*)=([^&\s"\']+)'), rf'\1={MASK}'),
    # "name": "value" в JSON
    (re.compile(rf'(?i)(["\']\w*{_SECRET_NAMES}\w*["\']\s*:\s*)(["\'])(.*?)\2'), rf'\1\2{MASK}\2'),
    (re.compile(rf'(?i)(["\']{_NAME_KEYS}["\']\s*:\s*)(["\'])(.*?)\2'), rf'\1\2{MASK}\2'),
    # email (в том числе в URL-кодировке %40)
    (re.compile(r'(?i)[a-z0-9._%+-]+(?:@|%40)[a-z0-9.-]+\.[a-z]{2,}'), MASK),
    # телефоны: международные +\d{10,15} (с пробелами, скобками, дефисами) и украинские 380.../0XX...
    (re.compile(r'(?:(?<![\w+])\+|%2B)\d(?:[\s()-]{0,2}\d){9,14}(?!\d)', re.I), MASK),
    (re.compile(r'(?<![\w+])(?:380|\(?0)\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)'), MASK),
]


def scrub(text) -> str:
    if not isinstance(text, str):
        text = str(text)
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class PiiScrubFilter(logging.Filter):
    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # кривые args: не теряем запись
            message = str(record.msg)
        record.msg = scrub(message)
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = scrub(record.exc_text)  # Formatter берёт готовый exc_text
        return True


class RequestPathFilter(logging.Filter):
    """django.request: путь без query, без объекта запроса (иначе форматтеры выводят тело и заголовки)."""

    def filter(self, record):
        if record.name.startswith('django.request') or record.name.startswith('django.server'):
            request = getattr(record, 'request', None)
            if request is not None:
                record.request = None
            if isinstance(record.args, tuple):
                record.args = tuple(a.split('?', 1)[0] if isinstance(a, str) else a for a in record.args)
        return True
