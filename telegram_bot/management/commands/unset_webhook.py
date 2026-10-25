import asyncio

from django.core.management.base import BaseCommand, CommandError

from telegram_bot.provider import get_telegram_provider, telegram_real_ready


class Command(BaseCommand):
    help = (
        'Снимает Telegram webhook, оставленный предыдущим ботом.\n'
        'Используйте перед запуском run_bot (polling), '
        'если старый бот работал в webhook-режиме.'
    )

    def handle(self, *args, **options):
        if not telegram_real_ready():
            raise CommandError(
                'TELEGRAM_BOT_TOKEN не задан. Добавьте его в .env и повторите.'
            )
        asyncio.run(self._run())

    async def _run(self) -> None:
        bot = get_telegram_provider().bot()
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
                    self.style.SUCCESS('OK: webhook снят. Теперь можно запускать: python manage.py run_bot')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'ВНИМАНИЕ: webhook всё ещё активен: {info_after.url}')
                )
        finally:
            await bot.session.close()
