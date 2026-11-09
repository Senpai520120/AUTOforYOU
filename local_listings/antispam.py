"""Anti-spam detection for listings and messages.

What counts as a contact:
- phone: Ukrainian phone formats (+380XXXXXXXXX, 0XX XXX XX XX, (0XX)XXX-XX-XX)
  NOT triggered by: year (4 digits), mileage (<=7 digits without phone pattern),
  price (standalone numbers), engine cc (3-4 digits).
- url: http://, https://, www., or domain.tld patterns (com/ua/net/org/io)
- messenger: telegram/viber/whatsapp/signal keyword (whole word) followed by @username or link
- email: name@domain.tld (8.5; before 8.5 it was caught only by chance via the url rule)

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

# 8.5 (05-Q20): ключевое слово - целым словом: «tg» внутри слова и «ватсапп»/«телеграмний» не срабатывают.
_MESSENGER_RE = re.compile(
    r'(?<!\w)(?:telegram|телеграм|tg|viber|вайбер|whatsapp|ватсап|signal|сигнал|вацап)(?!\w)'
    r'[\s:@\-]+\S+',
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r'[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+', re.IGNORECASE)

# Подписи типов для сообщений об ошибке (украинский интерфейс).
CONTACT_LABELS = {'phone': 'телефон', 'email': 'email', 'url': 'посилання', 'messenger': 'месенджер'}


def contacts_error(found: list) -> str:
    kinds = ', '.join(CONTACT_LABELS.get(k, k) for k in found)
    return f'Текст містить контактні дані ({kinds}). Видаліть їх.'

_TME_RE = re.compile(r't\.me/\S+', re.IGNORECASE)


def detect_contacts(text: str) -> list:
    """Return list of detected contact type strings. Empty = clean."""
    if not text:
        return []
    found = []
    if _PHONE_RE.search(text):
        found.append('phone')
    if _EMAIL_RE.search(text):
        found.append('email')
    # email не считается ещё и ссылкой (домен адреса похож на url)
    if _URL_RE.search(_EMAIL_RE.sub(' ', text)):
        found.append('url')
    if _MESSENGER_RE.search(text) or _TME_RE.search(text):
        found.append('messenger')
    return found
