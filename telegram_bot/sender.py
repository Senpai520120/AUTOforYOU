"""Единая точка отправки сообщений в Telegram для заявок (тонкая обёртка над адаптером `provider.py`)."""
from .provider import SendResult, get_telegram_provider

__all__ = ['SendResult', 'send_message']


def send_message(chat_id, text, buttons=None, parse_mode='HTML', demo_body=None) -> SendResult:
    """Шлёт сообщение через адаптер. Не налаштовано/off -> SendResult(ok=False, reason='not_configured').
    Сетевая ошибка -> ConnectionError (для ретрая), TelegramRetryAfter пробрасывается;
    прочие ошибки API -> SendResult(ok=False, reason=<класс>)."""
    return get_telegram_provider().send_message(chat_id, text, buttons=buttons, parse_mode=parse_mode,
                                                 demo_body=demo_body)
