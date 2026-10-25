import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from telegram_bot.provider import get_telegram_provider, telegram_real_ready


class Command(BaseCommand):
    help = 'Устанавливает Telegram webhook (для прод. деплоя)'

    def add_arguments(self, parser):
        parser.add_argument(
            'webhook_url',
            help='Полный HTTPS-URL webhook, например: https://yourdomain.com/api/v1/telegram/webhook/',
        )
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Удалить webhook (перейти в polling-режим)',
        )

    def handle(self, *args, **options):
        if not telegram_real_ready():
            raise CommandError('TELEGRAM_BOT_TOKEN не задан')

        webhook_url = options['webhook_url']
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '') or None
        delete = options['delete']

        asyncio.run(self._run(webhook_url, secret, delete))

    async def _run(self, webhook_url: str, secret, delete: bool) -> None:
        bot = get_telegram_provider().bot()
        try:
            if delete:
                await bot.delete_webhook()
                self.stdout.write(self.style.SUCCESS('Webhook удалён. Теперь используйте polling (run_bot).'))
            else:
                await bot.set_webhook(webhook_url, secret_token=secret)
                info = await bot.get_webhook_info()
                self.stdout.write(self.style.SUCCESS(f'Webhook установлен: {info.url}'))
        finally:
            await bot.session.close()
