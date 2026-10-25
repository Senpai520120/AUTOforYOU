import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from telegram_bot.provider import get_telegram_provider, telegram_real_ready
from telegram_bot.webhook_setup import WebhookConfigError, build_webhook_config, install_webhook

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

        mode = str(getattr(settings, 'TELEGRAM_UPDATES_MODE', 'polling') or 'polling').strip().lower()
        if mode not in ('polling', 'webhook'):
            raise CommandError(f'TELEGRAM_UPDATES_MODE={mode!r}: допустимо polling или webhook.')
        if mode == 'webhook':
            # Конфигурацию проверяем до сети: при ошибке webhook не трогаем.
            try:
                url, secret = build_webhook_config()
            except WebhookConfigError as exc:
                raise CommandError(str(exc)) from None

        from core.monitoring import init_monitoring
        init_monitoring('bot')  # мониторинг ошибок (7.6); пустой SENTRY_DSN - выключен
        if mode == 'webhook':
            asyncio.run(self._run_webhook(url, secret))
            self.stdout.write(self.style.SUCCESS('Webhook установлен: ' + url))
            return
        self.stdout.write(self.style.SUCCESS('🤖 Запуск Telegram-бота (polling)...'))
        asyncio.run(self._run())

    @staticmethod
    async def _run_webhook(url: str, secret: str) -> None:
        # Без delete_webhook и без polling: рестарт контейнера webhook не снимает.
        bot = get_telegram_provider().bot()
        try:
            await install_webhook(bot, url, secret)
        finally:
            await bot.session.close()

    @staticmethod
    async def _run() -> None:
        from telegram_bot.dispatcher import get_dispatcher

        bot = get_telegram_provider().bot()

        # Idempotent: снимаем webhook перед polling, чтобы не было конфликта, если
        # предыдущий запуск был в webhook-режиме. Накопленные апдейты не выбрасываем (07-Q9).
        await bot.delete_webhook(drop_pending_updates=False)

        dp = get_dispatcher()

        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()
