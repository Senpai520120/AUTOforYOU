import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from core.c2c import c2c_public_posting_enabled
from core.tasks import ResilientTask

logger = logging.getLogger(__name__)


# ResilientTask (8.9): повторы при сетевых ошибках, окончательная неудача - в FailedTask и мониторинг.
# Пакетная задача: глобальный лимит 120/180 с (CELERY_TASK_SOFT_TIME_LIMIT) мал для большого объёма, поэтому свой лимит.
@shared_task(name='saved_searches.tasks.check_saved_searches', base=ResilientTask, soft_time_limit=900, time_limit=960)
def check_saved_searches():
    """
    Daily task: for each SavedSearch with notify=True, find LocalListings created
    after last_notified_at, create in-app Notification + send_notification.
    Idempotent: last_notified_at is updated after processing.
    """
    # 6.7: сохранённые поиски закрыты и при выключенном разделе, и в «засеве» (middleware закрывает saved-searches/).
    if not c2c_public_posting_enabled():
        return {'skipped': 'c2c_disabled'}
    from django.utils import timezone

    from .models import SavedSearch

    now = timezone.now()
    processed = 0

    for ss_id in list(SavedSearch.objects.filter(notify=True).values_list('pk', flat=True)):
        # Сбой одного поиска (в т.ч. битые filters) не обрывает остальные; его транзакция откатана.
        try:
            if _process_search(ss_id, now):
                processed += 1
        except SoftTimeLimitExceeded:
            # Мягкий лимит Celery не глотаем: задача должна завершиться (и уйти в ResilientTask/FailedTask).
            raise
        except Exception:
            logger.exception('check_saved_searches: сбой обработки поиска id=%s', ss_id)

    logger.info('check_saved_searches: оброблено %d saved searches', processed)
    return {'processed': processed}


def _process_search(ss_id, now) -> bool:
    """Один поиск в одной транзакции: уведомления и last_notified_at фиксируются вместе.

    При повторе задачи (acks_late) после успешного коммита last_notified_at уже сдвинут - дублей нет;
    после отката - не создано ни уведомлений, ни сдвига, повтор безопасен.
    """
    from django.db import transaction

    from local_listings.models import LocalListing
    from notifications.models import Notification as NotifModel
    from notifications.services import create_notification

    from .models import SavedSearch

    with transaction.atomic():
        # Блокировка строки: параллельный запуск ждёт и увидит уже сдвинутый last_notified_at.
        ss = SavedSearch.objects.select_for_update().filter(pk=ss_id, notify=True).first()
        if ss is None:
            return False
        since = ss.last_notified_at or ss.created_at
        qs = _apply_filters(LocalListing.objects.filter(
            status=LocalListing.Status.ACTIVE,
            created_at__gt=since,
        ), ss.filters)

        listings = list(qs[:10])
        if not listings:
            return False

        for listing in listings:
            title = f'Нове авто за пошуком «{ss.name}»'
            text = f'{listing.make} {listing.model} {listing.year}, {listing.price} {listing.currency}'
            link = f'/local/{listing.pk}'
            create_notification(ss.user_id, NotifModel.Type.SAVED_SEARCH_MATCH, title, text, link)

        ss.last_notified_at = now
        ss.save(update_fields=['last_notified_at'])

        # Внешняя отправка (Telegram) - только после коммита, чтобы откат не оставил «призрачное» сообщение.
        summary = f'🔔 За пошуком «{ss.name}» знайдено {len(listings)} нових авто!'
        transaction.on_commit(lambda uid=ss.user_id, msg=summary: _send_summary(uid, msg))
    return True


def _send_summary(user_id, message):
    try:
        from integrations.tasks import send_notification
        send_notification.delay(user_id, message)
    except Exception:
        logger.exception('check_saved_searches: не удалось поставить Telegram-сводку user=%s', user_id)


def _apply_filters(qs, filters: dict):
    """Apply saved filter dict to LocalListing queryset."""
    if not filters:
        return qs
    if filters.get('make'):
        qs = qs.filter(make__icontains=filters['make'])
    if filters.get('model'):
        qs = qs.filter(model__icontains=filters['model'])
    if filters.get('year_min'):
        qs = qs.filter(year__gte=int(filters['year_min']))
    if filters.get('year_max'):
        qs = qs.filter(year__lte=int(filters['year_max']))
    if filters.get('price_min'):
        qs = qs.filter(price__gte=filters['price_min'])
    if filters.get('price_max'):
        qs = qs.filter(price__lte=filters['price_max'])
    if filters.get('fuel_type'):
        qs = qs.filter(fuel_type=filters['fuel_type'])
    if filters.get('transmission'):
        qs = qs.filter(transmission=filters['transmission'])
    if filters.get('body_type'):
        qs = qs.filter(body_type=filters['body_type'])
    if filters.get('region'):
        qs = qs.filter(region_id=filters['region'])
    if filters.get('city'):
        qs = qs.filter(city_id=filters['city'])
    if filters.get('mileage_max'):
        qs = qs.filter(mileage_km__lte=int(filters['mileage_max']))
    return qs
