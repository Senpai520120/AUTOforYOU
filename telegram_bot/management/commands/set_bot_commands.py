import asyncio

from django.core.management.base import BaseCommand, CommandError

from telegram_bot.bot_commands import BOT_COMMANDS, install_bot_commands
from telegram_bot.provider import get_telegram_provider, telegram_real_ready


class Command(BaseCommand):
    help = 'Устанавливает меню команд бота (описания берутся из админки: «Тексти Telegram-бота», ключи cmd_*).'

    def handle(self, *args, **options):
        if not telegram_real_ready():
            raise CommandError('TELEGRAM_BOT_TOKEN не задан. Добавьте его в .env и повторите.')
        asyncio.run(self._run())
        self.stdout.write(self.style.SUCCESS('Меню команд установлено: ' + ', '.join('/' + c for c in BOT_COMMANDS)))

    @staticmethod
    async def _run() -> None:
        bot = get_telegram_provider().bot()
        try:
            await install_bot_commands(bot)
        finally:
            await bot.session.close()
