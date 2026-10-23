"""Единая точка отправки сообщений в Telegram (адаптер поверх неё - задача 3.4)."""
import asyncio
import logging
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    reason: str = ''
    message_id: int | None = None


async def _send(token, chat_id, text, buttons, parse_mode) -> int:
    from aiogram import Bot
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = None
    if buttons:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons
        ])
    bot = Bot(token=token)
    try:
        msg = await bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode=parse_mode)
        return msg.message_id
    finally:
        await bot.session.close()


def send_message(chat_id, text, buttons=None, parse_mode='HTML') -> SendResult:
    """Шлёт сообщение. Без токена -> not_configured. Сетевая ошибка -> ConnectionError (для ретрая),
    TelegramRetryAfter пробрасывается; прочие ошибки API -> SendResult(ok=False, reason=<класс>)."""
    from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramRetryAfter

    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token or not chat_id:
        return SendResult(ok=False, reason='not_configured')
    try:
        message_id = asyncio.run(_send(token, chat_id, text, buttons, parse_mode))
    except TelegramRetryAfter:
        raise
    except TelegramNetworkError as exc:
        # В тексте исключения может быть URL с токеном - наружу только класс.
        raise ConnectionError(type(exc).__name__) from None
    except TelegramAPIError as exc:
        logger.warning('telegram.send_failed error=%s', type(exc).__name__)
        return SendResult(ok=False, reason=type(exc).__name__)
    return SendResult(ok=True, message_id=message_id)
