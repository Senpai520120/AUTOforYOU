import logging

from celery import shared_task
from django.conf import settings

from core.tasks import ResilientTask
from integrations.base import RETRYABLE_EXCEPTIONS

logger = logging.getLogger(__name__)

# ─── Письма (задача 3.4a) ────────────────────────────────────────────────────

# Паузы 60, 120, 240, 480, 900, 900 с (до ~45 мин): минутный сбой SMTP не должен терять письмо.
# Значения - в settings (EMAIL_RETRY_BACKOFF, EMAIL_RETRY_BACKOFF_MAX, EMAIL_MAX_RETRIES), здесь читаются при импорте.
EMAIL_RETRY_BACKOFF = settings.EMAIL_RETRY_BACKOFF
EMAIL_RETRY_BACKOFF_MAX = settings.EMAIL_RETRY_BACKOFF_MAX
EMAIL_MAX_RETRIES = settings.EMAIL_MAX_RETRIES


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

# Паузы повторов уведомлений: 60, 120, 240 с (как у писем, 3.4a); пауза flood control ограничена 10 минутами.
TELEGRAM_RETRY_BACKOFF = 60
TELEGRAM_RETRY_BACKOFF_MAX = 900
RETRY_AFTER_MAX_COUNTDOWN = 600


@shared_task(
    base=ResilientTask,
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=TELEGRAM_RETRY_BACKOFF,
    retry_backoff_max=TELEGRAM_RETRY_BACKOFF_MAX,
    name='integrations.tasks.send_notification',
)
def send_notification(self, user_id: int, text: str, buttons=None):
    """
    Отправляет Telegram-уведомление привязанному пользователю через адаптер `telegram_bot.provider`.
    Telegram не налаштовано -> {'sent': False, 'reason': 'not_configured'}; пропуск виден в статусе интеграций.

    Сетевой сбой (провайдер превращает TelegramNetworkError в ConnectionError) повторяется базой ResilientTask
    с растущей паузой; TelegramRetryAfter - `self.retry(countdown=retry_after)`. После исчерпания повторов
    задача падает, а сигнал task_failure пишет FailedTask (8.9). Аргументы (текст) в учёте сводятся к длине.

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
    from aiogram.exceptions import TelegramRetryAfter

    from integrations.base import record_error

    retry_after = None
    try:
        result = provider.send_message(telegram_id, text, buttons=buttons)
    except TelegramRetryAfter as exc:
        # Только пауза: в тексте исключения бывает chat_id (telegram_id), а у MaxRetriesExceededError - args (текст).
        retry_after = exc.retry_after
    if retry_after is not None:
        # Вне блока except: у нового исключения нет __context__ с исходным TelegramRetryAfter.
        record_error('telegram', RuntimeError('TelegramRetryAfter'))
        logger.warning('send_notification: user pk=%s flood control, повтор через %ss', user_id, retry_after)
        if self.request.retries >= self.max_retries:
            raise ConnectionError('TelegramRetryAfter') from None
        raise self.retry(exc=ConnectionError('TelegramRetryAfter'),
                         countdown=min(int(retry_after) + 1, RETRY_AFTER_MAX_COUNTDOWN))
    logger.info('send_notification: user pk=%s → sent=%s', user_id, result.ok)
    if not result.ok:
        if result.reason == 'TelegramForbiddenError':
            # Пользователь заблокировал бота: привязка мертва, дальше слать некуда (5.4, 07-Q13).
            from telegram_bot.models import unlink_telegram
            unlink_telegram(user.pk, only_telegram_id=telegram_id)
            logger.info('send_notification: user pk=%s заблокировал бота, Telegram отвязан', user_id)
            return {'sent': False, 'reason': 'blocked'}
        # Прочие ошибки API (в т.ч. TelegramBadRequest) не повторяются: привязка не трогается.
        return {'sent': False, 'reason': result.reason}
    return {'sent': True}
