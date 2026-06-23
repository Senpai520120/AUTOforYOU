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


# ─── Уведомления (заглушка — реализация в промте 11) ─────────────────────────

@shared_task(name='integrations.tasks.send_notification')
def send_notification(user_id: int, message: str, channel: str = 'telegram'):
    """
    Заглушка для отправки уведомлений пользователю.
    Промт 11: реализовать отправку через Telegram Bot API.
    """
    logger.info('send_notification [%s] → user=%s: %s', channel, user_id, message)
    return {'sent': False, 'reason': 'not implemented — see prompt 11'}
