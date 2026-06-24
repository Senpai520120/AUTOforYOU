import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Запускает Telegram-бота.\n'
        'Требует TELEGRAM_BOT_TOKEN в .env.\n'
        'Без токена завершается с сообщением; сайт продолжает работать.'
    )

    def handle(self, *args, **options):
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            self.stderr.write(
                self.style.ERROR(
                    '\n'
                    '❌  TELEGRAM_BOT_TOKEN не задан.\n'
                    '    Добавьте строку в .env:\n'
                    '    TELEGRAM_BOT_TOKEN=<токен от @BotFather>\n'
                    '\n'
                    '    Сайт и API работают как обычно — бот просто не будет запущен.\n'
                )
            )
            return

        self.stdout.write(self.style.SUCCESS('🤖 Запуск Telegram-бота (polling)...'))
        asyncio.run(self._run(token))

    @staticmethod
    async def _run(token: str) -> None:
        from aiogram import Bot, Dispatcher

        from telegram_bot.handlers import router
        from telegram_bot.middleware import UserBindingMiddleware

        bot = Bot(token=token)

        # Idempotent: снимаем webhook перед polling, чтобы не было конфликта
        # если предыдущий бот работал в webhook-режиме.
        await bot.delete_webhook(drop_pending_updates=True)

        dp = Dispatcher()
        dp.include_router(router)
        dp.message.middleware(UserBindingMiddleware())

        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()
