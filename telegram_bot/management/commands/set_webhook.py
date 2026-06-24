import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


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
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            raise CommandError('TELEGRAM_BOT_TOKEN не задан')

        webhook_url = options['webhook_url']
        secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '') or None
        delete = options['delete']

        asyncio.run(self._run(token, webhook_url, secret, delete))

    async def _run(self, token: str, webhook_url: str, secret, delete: bool) -> None:
        from aiogram import Bot

        bot = Bot(token=token)
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
