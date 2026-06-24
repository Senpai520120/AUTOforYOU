import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# ─── Импорт лотов аукционов (Apify) ──────────────────────────────────────────


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError),
    retry_kwargs={'max_retries': 3, 'countdown': 120},
    name='integrations.tasks.import_lot_task',
)
def import_lot_task(self, lot_data: dict, seller_id: int):
    """
    Импортирует один нормализованный лот в Vehicle + Listing.

    Идемпотентен: повторный вызов с тем же VIN обновляет Vehicle, не плодит дублей.

    Args:
        lot_data: нормализованный dict от AuctionLotProvider.
        seller_id: PK пользователя — владельца листинга.
    """
    from django.contrib.auth import get_user_model
    from integrations.importer import import_lot

    User = get_user_model()
    try:
        seller = User.objects.get(pk=seller_id)
    except User.DoesNotExist:
        logger.error('import_lot_task: seller pk=%s не найден', seller_id)
        return {'error': f'seller {seller_id} not found'}

    vehicle, listing, created = import_lot(lot_data, seller)
    logger.info(
        'import_lot_task: VIN=%s listing=%s %s',
        vehicle.vin, listing.pk, 'created' if created else 'updated',
    )
    return {'vehicle_id': vehicle.pk, 'listing_id': listing.pk, 'created': created}


# ─── Уведомления (реализация промта 11) ──────────────────────────────────────

@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    name='integrations.tasks.send_notification',
)
def send_notification(self, user_id: int, text: str, buttons=None):
    """
    Отправляет Telegram-уведомление привязанному пользователю.
    Если пользователь не привязан или TELEGRAM_BOT_TOKEN не задан → молча пропускает.

    Args:
        user_id: PK CustomUser.
        text: текст сообщения.
        buttons: список dict {text, url} для inline-кнопок (необязательно).
    """
    import asyncio
    from django.conf import settings
    from django.contrib.auth import get_user_model

    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        logger.info('send_notification: TELEGRAM_BOT_TOKEN не задан, пропуск')
        return {'sent': False, 'reason': 'no token'}

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error('send_notification: user pk=%s не найден', user_id)
        return {'sent': False, 'reason': 'user not found'}

    telegram_id = getattr(user, 'telegram_id', None)
    if not telegram_id:
        logger.info('send_notification: user pk=%s не привязан к Telegram, пропуск', user_id)
        return {'sent': False, 'reason': 'not linked'}

    async def _send() -> bool:
        from aiogram import Bot
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        bot = Bot(token=token)
        kb = None
        if buttons:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=b['text'], url=b['url'])]
                for b in buttons
            ])
        try:
            await bot.send_message(chat_id=telegram_id, text=text, reply_markup=kb)
            return True
        finally:
            await bot.session.close()

    sent = asyncio.run(_send())
    logger.info('send_notification: user pk=%s (telegram_id=%s) → sent=%s', user_id, telegram_id, sent)
    return {'sent': sent}
