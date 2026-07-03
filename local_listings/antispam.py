"""Anti-spam detection for listings and messages.

What counts as a contact:
- phone: Ukrainian phone formats (+380XXXXXXXXX, 0XX XXX XX XX, (0XX)XXX-XX-XX)
  NOT triggered by: year (4 digits), mileage (<=7 digits without phone pattern),
  price (standalone numbers), engine cc (3-4 digits).
- url: http://, https://, www., or domain.tld patterns (com/ua/net/org/io)
- messenger: telegram/viber/whatsapp/signal keyword followed by @username or link

Mode is controlled by settings.ANTISPAM_MODE (default='soft'):
  'soft' -- flag listing, warn in message response (never hard block)
  'hard' -- raise ValidationError for listings, block message send
  'off'  -- detection disabled
"""

import re

_PHONE_RE = re.compile(
    r'(?:'
    r'\+\s?3\s?8\s?0?\s?\(?\s?\d{2}\s?\)?\s?[\d\s\-]{7,}'   # +380...
    r'|'
    r'(?<!\d)0\d{2}[\s\-\(]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)'  # 0XXXXXXXXX Ukrainian
    r')',
    re.IGNORECASE,
)

_URL_RE = re.compile(
    r'(?:https?://|www\.)\S+'
    r'|'
    r'(?<!\w)\S+\.(?:com|ua|net|org|info|io|me|biz)\b',
    re.IGNORECASE,
)

_MESSENGER_RE = re.compile(
    r'(?:telegram|телеграм|tg|viber|вайбер|whatsapp|ватсап|signal|вацап)'
    r'[\s:@\-]+\S+',
    re.IGNORECASE,
)

_TME_RE = re.compile(r't\.me/\S+', re.IGNORECASE)


def detect_contacts(text: str) -> list:
    """Return list of detected contact type strings. Empty = clean."""
    if not text:
        return []
    found = []
    if _PHONE_RE.search(text):
        found.append('phone')
    if _URL_RE.search(text):
        found.append('url')
    if _MESSENGER_RE.search(text) or _TME_RE.search(text):
        found.append('messenger')
    return found
