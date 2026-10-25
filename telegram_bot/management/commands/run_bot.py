import asyncio
import logging

from django.core.management.base import BaseCommand

from telegram_bot.provider import get_telegram_provider, telegram_real_ready

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Запускает Telegram-бота.\n'
        'Требует TELEGRAM_BOT_TOKEN в .env.\n'
        'Без токена завершается с сообщением; сайт продолжает работать.'
    )

    def handle(self, *args, **options):
        if not telegram_real_ready():
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

        from core.monitoring import init_monitoring
        init_monitoring('bot')  # мониторинг ошибок (7.6); пустой SENTRY_DSN - выключен
        self.stdout.write(self.style.SUCCESS('🤖 Запуск Telegram-бота (polling)...'))
        asyncio.run(self._run())

    @staticmethod
    async def _run() -> None:
        from telegram_bot.dispatcher import get_dispatcher

        bot = get_telegram_provider().bot()

        # Idempotent: снимаем webhook перед polling, чтобы не было конфликта
        # если предыдущий бот работал в webhook-режиме.
        await bot.delete_webhook(drop_pending_updates=True)

        dp = get_dispatcher()

        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()
