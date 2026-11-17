"""Установка webhook Telegram (задача 5.1). Общий код для `run_bot` и (в 5.4) `set_webhook`."""
import re

from django.conf import settings

WEBHOOK_PATH = '/api/v1/telegram/webhook/'
# Допустимые символы секрета по документации Bot API: A-Z a-z 0-9 _ -, длина 1-256; требуем 32+ (стойкость).
_SECRET_RE = re.compile(r'^[A-Za-z0-9_-]{32,256}$')


class WebhookConfigError(Exception):
    """Для webhook не хватает настроек; текст говорит, что задать в .env."""


def build_webhook_config(url: str | None = None) -> tuple[str, str]:
    """(url, secret) из settings или WebhookConfigError. Telegram принимает webhook только по HTTPS.

    `url` - явный адрес (аргумент `set_webhook`); без него адрес = SITE_URL + WEBHOOK_PATH.
    """
    secret = str(getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '') or '').strip()
    if not secret:
        raise WebhookConfigError(
            'TELEGRAM_WEBHOOK_SECRET не задан. Добавьте в .env случайную строку 32+ символа '
            '(только A-Z a-z 0-9 _ -).'
        )
    if not _SECRET_RE.match(secret):
        raise WebhookConfigError('TELEGRAM_WEBHOOK_SECRET должен быть длиной 32-256 символов из A-Z a-z 0-9 _ -.')
    if url is not None:
        url = url.strip()
        if not url.startswith('https://'):
            raise WebhookConfigError('Webhook-URL должен начинаться с https:// (Telegram не принимает HTTP).')
        return url, secret
    site_url = str(getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
    if not site_url.startswith('https://'):
        raise WebhookConfigError('SITE_URL должен начинаться с https:// (Telegram не принимает webhook по HTTP).')
    return site_url + WEBHOOK_PATH, secret


async def install_webhook(bot, url: str, secret: str) -> str:
    """Ставит webhook без сброса накопленных апдейтов, возвращает URL из getWebhookInfo."""
    await bot.set_webhook(url, secret_token=secret, drop_pending_updates=False)
    info = await bot.get_webhook_info()
    return info.url
