"""Тексты Telegram-сообщений с экранированием (задача 5.1, 07-S3).

Единственная точка, где значения из БД и от пользователя попадают в HTML-разметку
(`parse_mode='HTML'`). Хендлеры и задача публикации в канал строят текст только здесь.
Шаблоны из админки (`BotText`, 5.4) подставляют значения через `esc()` (см. `texts.get_text`).
"""
from html import escape


def esc(value) -> str:
    """Экранирует `<`, `>`, `&` и кавычки: значение показывается буквально, разметку не меняет."""
    return escape(str(value), quote=True)


def listing_card_html(title_parts, price, currency, status=None, *, prefix='', url=None) -> str:
    """Карточка объявления: в боте (есть `status`) или в канале (есть `url`).

    Шаблоны берутся из `BotText` (`latest_item`, `channel_listing`), значения подставляются
    экранированными. `prefix` - готовая доверенная разметка (плашка «терміновий викуп» из `BotText`),
    пользовательские данные сюда не передавать.
    """
    from telegram_bot.texts import get_text

    title = ' '.join(str(p) for p in title_parts if p not in (None, ''))
    if url:
        body = get_text('channel_listing', title=title, price=price, currency=currency, url=url)
    else:
        body = get_text('latest_item', title=title, price=price, currency=currency, status=status or '')
    return prefix + body
