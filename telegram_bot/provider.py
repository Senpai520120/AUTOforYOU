"""Telegram как адаптер (задача 3.4b, 07-C3, 07-C5).

Единственное место проекта, где создаётся `aiogram.Bot`. Режим - `TELEGRAM_MODE`:
- auto: real, если задан `TELEGRAM_BOT_TOKEN` (не плейсхолдер), иначе «не налаштовано»;
- real: токен обязателен;
- demo: ничего не отправляется, сообщение пишется в лог (без текста) и в `OutboxMessage`;
- off: Telegram выключен.

Токен и тексты ошибок API наружу не уходят: в лог и `IntegrationHealth` попадает класс исключения.
"""
import asyncio
import logging
from dataclasses import dataclass

from django.conf import settings

from integrations.base import (
    MODE_DEMO,
    MODE_REAL,
    BaseProvider,
    env_state,
    is_placeholder,
    mask_secrets,
    record_error,
    record_skip,
    record_success,
)

logger = logging.getLogger(__name__)

NOT_CONFIGURED = 'not_configured'


@dataclass
class SendResult:
    ok: bool
    reason: str = ''
    message_id: int | None = None


def _keyboard(buttons):
    if not buttons:
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b['text'], url=b['url'])] for b in buttons
    ])


class TelegramProvider(BaseProvider):
    """Интерфейс и общий статус. Реализации: Real, Demo, Disabled."""
    key = 'telegram'
    title = 'Telegram'
    env_vars = (
        'TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME', 'TELEGRAM_CHANNEL_ID',
        'TELEGRAM_B2B_CHANNEL_ID', 'TELEGRAM_WEBHOOK_SECRET',
    )
    checklist_anchor = '2.7'

    @staticmethod
    def token() -> str:
        return str(getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or '').strip()

    def has_credentials(self) -> bool:
        return not is_placeholder(self.token())

    def send_message(self, chat_id, text, buttons=None, parse_mode=None, demo_body=None) -> SendResult:
        raise NotImplementedError

    def send_photo(self, chat_id, photo, caption='', buttons=None, parse_mode=None) -> SendResult:
        raise NotImplementedError

    def bot(self):
        """Фабрика `aiogram.Bot` для webhook и команд. Закрывать `await bot.session.close()`."""
        raise NotImplementedError

    def status(self):
        st = super().status()
        webhook = env_state('TELEGRAM_WEBHOOK_SECRET') == 'задано'
        st.notes.append(f'Режим бота: {"webhook" if webhook else "polling"} '
                        f'({"секрет webhook задано" if webhook else "секрет webhook не задано"})')
        return st


class RealTelegramProvider(TelegramProvider):
    def bot(self):
        from aiogram import Bot

        return Bot(token=self.token())

    # --- отправка ---------------------------------------------------------------
    async def _send(self, method, **kwargs) -> int:
        bot = self.bot()
        try:
            msg = await getattr(bot, method)(**kwargs)
            return msg.message_id
        finally:
            await bot.session.close()

    def _call(self, method, **kwargs) -> SendResult:
        """Сетевая ошибка -> ConnectionError (ретрай задачи), TelegramRetryAfter пробрасывается,
        прочие ошибки API -> SendResult(ok=False, reason=<класс>). Токен и текст исключения наружу не идут."""
        from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramRetryAfter

        try:
            message_id = asyncio.run(self._send(method, **kwargs))
        except TelegramRetryAfter:
            raise
        except TelegramNetworkError as exc:
            record_error(self.key, ConnectionError(type(exc).__name__))
            raise ConnectionError(type(exc).__name__) from None
        except TelegramAPIError as exc:
            record_error(self.key, RuntimeError(type(exc).__name__))
            logger.warning('telegram.send_failed error=%s', type(exc).__name__)
            return SendResult(ok=False, reason=type(exc).__name__)
        record_success(self.key)
        return SendResult(ok=True, message_id=message_id)

    def send_message(self, chat_id, text, buttons=None, parse_mode=None, demo_body=None) -> SendResult:
        if not chat_id:
            return SendResult(ok=False, reason=NOT_CONFIGURED)
        return self._call('send_message', chat_id=chat_id, text=text, reply_markup=_keyboard(buttons),
                          parse_mode=parse_mode)

    def send_photo(self, chat_id, photo, caption='', buttons=None, parse_mode=None) -> SendResult:
        if not chat_id:
            return SendResult(ok=False, reason=NOT_CONFIGURED)
        return self._call('send_photo', chat_id=chat_id, photo=photo, caption=caption,
                          reply_markup=_keyboard(buttons), parse_mode=parse_mode)

    # --- проверка (кнопка «Перевірити бота») ------------------------------------
    def check(self) -> dict:
        """getMe + getWebhookInfo. Токен в ответ не попадает, платной квоты нет."""
        async def _check():
            bot = self.bot()
            try:
                me = await bot.get_me()
                info = await bot.get_webhook_info()
                return {'username': me.username, 'webhook_url': info.url or ''}
            finally:
                await bot.session.close()

        try:
            result = asyncio.run(_check())
        except Exception as exc:  # noqa: BLE001 - причина показывается админу, токен маскируется
            record_error(self.key, RuntimeError(type(exc).__name__))
            raise RuntimeError(mask_secrets(type(exc).__name__)) from None
        record_success(self.key)
        result['webhook_url'] = mask_secrets(result['webhook_url'])
        return result


class DemoTelegramProvider(TelegramProvider):
    """Ничего не отправляет: пишет в OutboxMessage (superuser видит в админке) и в лог без текста."""

    def _record(self, chat_id, text, photo='') -> SendResult:
        from integrations.models import write_outbox

        body = f'[фото: {photo}]\n{text}' if photo else text
        row = write_outbox('telegram', recipient=chat_id, subject='', body=body)
        logger.info('Telegram (demo): сообщение записано в Outbox, текст в лог не выводится')
        return SendResult(ok=True, message_id=row.pk)

    def send_message(self, chat_id, text, buttons=None, parse_mode=None, demo_body=None) -> SendResult:
        if not chat_id:
            return SendResult(ok=False, reason=NOT_CONFIGURED)
        # demo_body: безличный маркер вместо текста (заявки: имя и телефон клиента в Outbox не пишем).
        return self._record(chat_id, text if demo_body is None else demo_body)

    def send_photo(self, chat_id, photo, caption='', buttons=None, parse_mode=None) -> SendResult:
        if not chat_id:
            return SendResult(ok=False, reason=NOT_CONFIGURED)
        return self._record(chat_id, caption, photo=photo)

    def bot(self):
        raise RuntimeError('В демо-режиме aiogram.Bot не создаётся (TELEGRAM_MODE=demo)')


class DisabledTelegramProvider(TelegramProvider):
    """«Не налаштовано» или off: отправка явно отклоняется, пропуск считается в статусе."""

    def _skip(self) -> SendResult:
        record_skip(self.key)
        logger.info('Telegram: отправка пропущена (%s)', self.resolution().reason)
        return SendResult(ok=False, reason=NOT_CONFIGURED)

    def send_message(self, chat_id, text, buttons=None, parse_mode=None, demo_body=None) -> SendResult:
        return self._skip()

    def send_photo(self, chat_id, photo, caption='', buttons=None, parse_mode=None) -> SendResult:
        return self._skip()

    def bot(self):
        raise RuntimeError('Telegram не налаштовано: бот недоступен')


def get_telegram_provider() -> TelegramProvider:
    """Реализация по `TELEGRAM_MODE`."""
    res = TelegramProvider().resolution()
    if not res.configured:
        return DisabledTelegramProvider()
    return DemoTelegramProvider() if res.mode == MODE_DEMO else RealTelegramProvider()


def telegram_configured() -> bool:
    """Можно ли слать сообщения (real с токеном или demo)."""
    return TelegramProvider().is_configured()


def telegram_real_ready() -> bool:
    """Настоящий бот (webhook, polling, команды): real и токен задан."""
    res = TelegramProvider().resolution()
    return res.configured and res.mode == MODE_REAL
