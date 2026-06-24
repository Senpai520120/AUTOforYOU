import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        'Снимает Telegram webhook, оставленный предыдущим ботом.\n'
        'Используйте перед запуском run_bot (polling), '
        'если старый бот работал в webhook-режиме.'
    )

    def handle(self, *args, **options):
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            raise CommandError(
                'TELEGRAM_BOT_TOKEN не задан. Добавьте его в .env и повторите.'
            )
        asyncio.run(self._run(token))

    async def _run(self, token: str) -> None:
        from aiogram import Bot

        bot = Bot(token=token)
        try:
            info_before = await bot.get_webhook_info()
            if info_before.url:
                self.stdout.write(f'Текущий webhook: {info_before.url}')
            else:
                self.stdout.write('Webhook не был установлен.')

            await bot.delete_webhook(drop_pending_updates=True)

            info_after = await bot.get_webhook_info()
            if not info_after.url:
                self.stdout.write(
                    self.style.SUCCESS('✅ Webhook снят. Теперь можно запускать: python manage.py run_bot')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Webhook всё ещё активен: {info_after.url}')
                )
        finally:
            await bot.session.close()
