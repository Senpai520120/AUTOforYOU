import logging

from celery import shared_task

from core.tasks import ResilientTask
from integrations.base import RETRYABLE_EXCEPTIONS

logger = logging.getLogger(__name__)

# ─── Письма (задача 3.4a) ────────────────────────────────────────────────────

# Паузы 60, 120, 240, 480, 900, 900 с (до ~45 мин): минутный сбой SMTP не должен терять письмо.
EMAIL_RETRY_BACKOFF = 60
EMAIL_RETRY_BACKOFF_MAX = 900
EMAIL_MAX_RETRIES = 6


@shared_task(
    base=ResilientTask,
    retry_backoff=EMAIL_RETRY_BACKOFF,
    retry_backoff_max=EMAIL_RETRY_BACKOFF_MAX,
    max_retries=EMAIL_MAX_RETRIES,
    name='integrations.tasks.send_email_task',
)
def send_email_task(to, subject, body):
    """Асинхронная отправка письма через адаптер почты (Н-28).

    Сбой SMTP повторяется базой ResilientTask; окончательная неудача попадает в FailedTask (8.9).
    Аргументы (адрес, текст) в учёте упавших задач сводятся к длине строки.
    """
    from integrations.email import deliver_email

    return deliver_email(to, subject, body)


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
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    name='integrations.tasks.send_notification',
)
def send_notification(self, user_id: int, text: str, buttons=None):
    """
    Отправляет Telegram-уведомление привязанному пользователю через адаптер `telegram_bot.provider`.
    Telegram не налаштовано -> {'sent': False, 'reason': 'not_configured'}; пропуск виден в статусе интеграций.

    Args:
        user_id: PK CustomUser.
        text: текст сообщения.
        buttons: список dict {text, url} для inline-кнопок (необязательно).
    """
    from django.contrib.auth import get_user_model

    from integrations.base import record_skip
    from telegram_bot.provider import NOT_CONFIGURED, get_telegram_provider

    provider = get_telegram_provider()
    if not provider.is_configured():
        # Явный отказ вместо «тихого» пропуска: счётчик пропусков покажет это в статусе (3.4b).
        record_skip('telegram')
        logger.info('send_notification: Telegram не налаштовано, пропуск')
        return {'sent': False, 'reason': NOT_CONFIGURED}

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

    # В лог идёт только pk пользователя, telegram_id не пишем (03-S4 / 07-S9).
    result = provider.send_message(telegram_id, text, buttons=buttons)
    logger.info('send_notification: user pk=%s → sent=%s', user_id, result.ok)
    if not result.ok:
        return {'sent': False, 'reason': result.reason}
    return {'sent': True}
