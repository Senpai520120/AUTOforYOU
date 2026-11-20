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


# Скільки оголошень показуємо окремими сповіщеннями за один запуск; решта - одним «і ще N» з посиланням на каталог.
MAX_LISTINGS_PER_RUN = 10


def _matching_listings(ss):
    """Нові активні оголошення за збереженим пошуком, з датою публікації (модерації).

    Дата публікації - moderated_at (коли схвалено), для оголошень без неї (автопублікація, старі) - created_at.
    Битий filters у старому записі - ValidationError (викликач пропускає запис).
    """
    from django.db.models.functions import Coalesce

    from local_listings.filters import apply_listing_filters, clean_filter_params
    from local_listings.models import LocalListing

    params = clean_filter_params(ss.filters or {})
    since = ss.last_notified_at or ss.created_at
    qs = LocalListing.objects.filter(status=LocalListing.Status.ACTIVE).annotate(
        published_at=Coalesce('moderated_at', 'created_at'),
    ).filter(published_at__gt=since)
    return apply_listing_filters(qs, params), params


def _process_search(ss_id, now) -> bool:
    """Один поиск в одной транзакции: уведомления и last_notified_at фиксируются вместе.

    При повторе задачи (acks_late) после успешного коммита last_notified_at уже сдвинут - дублей нет;
    после отката - не создано ни уведомлений, ни сдвига, повтор безопасен.
    Без потерь: окремо сповіщаємо перші MAX_LISTINGS_PER_RUN (за зростанням дати публікації), решту - одним
    сповіщенням «і ще N» з посиланням на каталог; курсор = дата публікації найновішого врахованого оголошення.
    """
    from urllib.parse import urlencode

    from django.db import transaction
    from django.db.models import Max
    from rest_framework.exceptions import ValidationError

    from notifications.models import Notification as NotifModel
    from notifications.services import create_notification

    from .models import SavedSearch

    with transaction.atomic():
        # Блокировка строки: параллельный запуск ждёт и увидит уже сдвинутый last_notified_at.
        ss = SavedSearch.objects.select_for_update().filter(pk=ss_id, notify=True).first()
        if ss is None:
            return False
        try:
            qs, params = _matching_listings(ss)
        except ValidationError:
            logger.warning('check_saved_searches: пропущено поиск id=%s - некорректные filters', ss_id)
            return False

        latest = qs.aggregate(m=Max('published_at'))['m']
        if latest is None:
            return False
        # Фиксируем верхнюю границу: объявления, опубликованные во время обработки, уйдут в следующий запуск.
        qs = qs.filter(published_at__lte=latest).order_by('published_at', 'pk')
        total = qs.count()
        listings = list(qs[:MAX_LISTINGS_PER_RUN])

        for listing in listings:
            title = f'Нове авто за пошуком «{ss.name}»'
            text = f'{listing.make} {listing.model} {listing.year}, {listing.price} {listing.currency}'
            link = f'/local/{listing.pk}'
            create_notification(ss.user_id, NotifModel.Type.SAVED_SEARCH_MATCH, title, text, link)

        rest = total - len(listings)
        if rest > 0:
            link = '/local' + (f'?{urlencode(params)}' if params else '')
            create_notification(
                ss.user_id, NotifModel.Type.SAVED_SEARCH_MATCH,
                f'Нові авто за пошуком «{ss.name}»', f'і ще {rest} нових оголошень', link,
            )

        ss.last_notified_at = latest
        ss.save(update_fields=['last_notified_at'])

        # Внешняя отправка (Telegram) - только после коммита, чтобы откат не оставил «призрачное» сообщение.
        summary = f'🔔 За пошуком «{ss.name}» знайдено {total} нових авто!'
        transaction.on_commit(lambda uid=ss.user_id, msg=summary: _send_summary(uid, msg))
    return True


def _send_summary(user_id, message):
    try:
        from integrations.tasks import send_notification
        send_notification.delay(user_id, message)
    except Exception:
        logger.exception('check_saved_searches: не удалось поставить Telegram-сводку user=%s', user_id)
