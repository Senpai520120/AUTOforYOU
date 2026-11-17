import asyncio

from django.core.management.base import BaseCommand, CommandError

from telegram_bot.provider import get_telegram_provider, telegram_real_ready
from telegram_bot.webhook_setup import WebhookConfigError, build_webhook_config, install_webhook


class Command(BaseCommand):
    help = (
        'Устанавливает Telegram webhook (для прод. деплоя). Адрес по умолчанию: SITE_URL + /api/v1/telegram/webhook/. '
        'Требует TELEGRAM_WEBHOOK_SECRET. Снять webhook: manage.py unset_webhook.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'webhook_url', nargs='?', default=None,
            help='Полный HTTPS-URL webhook; по умолчанию SITE_URL + /api/v1/telegram/webhook/',
        )

    def handle(self, *args, **options):
        if not telegram_real_ready():
            raise CommandError('TELEGRAM_BOT_TOKEN не задан')
        try:
            url, secret = build_webhook_config(options['webhook_url'])
        except WebhookConfigError as exc:
            raise CommandError(str(exc)) from None
        installed = asyncio.run(self._run(url, secret))
        self.stdout.write(self.style.SUCCESS(f'Webhook установлен: {installed}'))

    @staticmethod
    async def _run(url: str, secret: str) -> str:
        bot = get_telegram_provider().bot()
        try:
            return await install_webhook(bot, url, secret)
        finally:
            await bot.session.close()
