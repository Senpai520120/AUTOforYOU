"""Тексты Telegram-сообщений с экранированием (задача 5.1, 07-S3).

Единственная точка, где значения из БД и от пользователя попадают в HTML-разметку
(`parse_mode='HTML'`). Хендлеры и задача публикации в канал строят текст только здесь.
Шаблоны из админки (5.4) тоже должны проходить через `esc()`.
"""
from html import escape


def esc(value) -> str:
    """Экранирует `<`, `>`, `&` и кавычки: значение показывается буквально, разметку не меняет."""
    return escape(str(value), quote=True)


def listing_card_html(title_parts, price, currency, status=None, *, prefix='', url=None) -> str:
    """Карточка объявления: заголовок, цена, статус (в боте) или ссылка (в канале).

    `prefix` - готовая доверенная разметка кода (например, плашка «терміновий викуп»),
    пользовательские данные сюда не передавать.
    """
    title = esc(' '.join(str(p) for p in title_parts if p not in (None, '')))
    lines = [f'{prefix}🚗 <b>{title}</b>', f'💵 {esc(price)} {esc(currency)}']
    if status:
        lines.append(f'📦 {esc(status)}')
    if url:
        lines.append(f'🔗 {esc(url)}')
    return '\n'.join(lines)
