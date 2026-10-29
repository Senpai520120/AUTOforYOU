import logging
import time

from aiogram.exceptions import TelegramRetryAfter
from celery import shared_task

logger = logging.getLogger(__name__)

# Пауза между постами в канал, чтобы уважать лимиты Bot API (~20 сообщений/мин)
_CHANNEL_THROTTLE_SECONDS = 3


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError),
    retry_kwargs={'max_retries': 5, 'countdown': _CHANNEL_THROTTLE_SECONDS},
    name='telegram_bot.tasks.post_listing_to_channel',
)
def post_listing_to_channel(self, listing_id: int) -> dict:
    """
    Постит листинг в Telegram-канал.
    Retail → TELEGRAM_CHANNEL_ID.
    is_express_buyout (wholesale) → TELEGRAM_B2B_CHANNEL_ID (или основной, если не задан).
    Ретрай на TelegramRetryAfter/FloodWait; пауза между постами.
    """
    from django.conf import settings

    from core.modules import module_enabled
    if not module_enabled('lots'):
        # Задача могла встать в очередь до выключения модуля.
        return {'posted': False, 'reason': 'lots disabled'}

    from integrations.base import record_skip
    from telegram_bot.formatting import listing_card_html
    from telegram_bot.provider import get_telegram_provider
    from telegram_bot.texts import get_text

    provider = get_telegram_provider()
    if not provider.is_configured():
        record_skip('telegram')  # пропуск виден в статусе интеграций
        logger.warning('post_listing_to_channel: Telegram не налаштовано, пропуск')
        return {'posted': False, 'reason': 'not_configured'}

    from listings.models import Listing
    try:
        listing = (
            Listing.objects
            .select_related('vehicle')
            .prefetch_related('vehicle__images')
            .get(pk=listing_id)
        )
    except Listing.DoesNotExist:
        logger.error('post_listing_to_channel: листинг %s не найден', listing_id)
        return {'posted': False, 'reason': 'listing not found'}

    is_express = listing.is_express_buyout
    channel_id = (
        getattr(settings, 'TELEGRAM_B2B_CHANNEL_ID', '') or
        getattr(settings, 'TELEGRAM_CHANNEL_ID', '')
    ) if is_express else getattr(settings, 'TELEGRAM_CHANNEL_ID', '')

    if not channel_id:
        logger.warning('post_listing_to_channel: channel_id не задан, пропуск')
        return {'posted': False, 'reason': 'no channel_id'}

    v = listing.vehicle
    site_url = getattr(settings, 'SITE_URL', 'https://autoforyou.ua')
    prefix = get_text('channel_express_prefix') if is_express else ''
    text = listing_card_html(
        (v.make, v.model, v.year), listing.price, listing.currency,
        prefix=prefix, url=f'{site_url}/listings/{listing_id}',
    )
    img = v.images.filter(is_primary=True).first() or v.images.first()
    photo_url = (img.source_url or '') if img else ''

    buttons = [{'text': get_text('btn_view_listing'), 'url': f'{site_url}/listings/{listing_id}'}]
    try:
        result = None
        if photo_url:
            try:
                result = provider.send_photo(channel_id, photo_url, caption=text, buttons=buttons,
                                             parse_mode='HTML')
            except TelegramRetryAfter:
                raise
            except Exception:
                result = None  # fallback to text
            if result is not None and not result.ok:
                result = None
        if result is None:
            result = provider.send_message(channel_id, text, buttons=buttons, parse_mode='HTML')
        posted = result.ok
    except TelegramRetryAfter as exc:
        raise self.retry(countdown=exc.retry_after + 1) from exc
    except Exception as exc:
        # Bad URL (localhost dev), invalid chat_id, network - log and skip, never crash listing creation.
        logger.warning('post_listing_to_channel: skipped listing %s: %s', listing_id, type(exc).__name__)
        return {'posted': False, 'reason': type(exc).__name__}
    if not posted:
        return {'posted': False, 'reason': 'telegram_error'}
    time.sleep(_CHANNEL_THROTTLE_SECONDS)
    logger.info('post_listing_to_channel: листинг %s опубликован в %s', listing_id, channel_id)
    return {'posted': True, 'listing_id': listing_id}
