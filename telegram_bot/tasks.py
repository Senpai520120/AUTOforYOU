import asyncio
import logging
import time

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

    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        logger.warning('post_listing_to_channel: TELEGRAM_BOT_TOKEN не задан, пропуск')
        return {'posted': False, 'reason': 'no token'}

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
    prefix = '⚡ <b>ТЕРМІНОВИЙ ВИКУП</b>\n' if is_express else ''
    text = (
        f'{prefix}'
        f'🚗 <b>{v.make} {v.model} {v.year}</b>\n'
        f'💵 {listing.price} {listing.currency}\n'
        f'🔗 {site_url}/listings/{listing_id}'
    )
    img = v.images.filter(is_primary=True).first() or v.images.first()
    photo_url = (img.source_url or '') if img else ''

    async def _post() -> bool:
        from aiogram import Bot
        from aiogram.exceptions import TelegramRetryAfter
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        bot = Bot(token=token)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text='Переглянути оголошення',
                url=f'{site_url}/listings/{listing_id}',
            )
        ]])
        try:
            if photo_url:
                try:
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=photo_url,
                        caption=text,
                        reply_markup=kb,
                        parse_mode='HTML',
                    )
                    return True
                except Exception:
                    pass  # fallback to text
            await bot.send_message(
                chat_id=channel_id,
                text=text,
                reply_markup=kb,
                parse_mode='HTML',
            )
            return True
        except TelegramRetryAfter as exc:
            raise self.retry(countdown=exc.retry_after + 1) from exc
        finally:
            await bot.session.close()

    asyncio.run(_post())
    time.sleep(_CHANNEL_THROTTLE_SECONDS)
    logger.info('post_listing_to_channel: листинг %s опубликован в %s', listing_id, channel_id)
    return {'posted': True, 'listing_id': listing_id}
