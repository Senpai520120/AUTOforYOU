import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name='saved_searches.tasks.check_saved_searches')
def check_saved_searches():
    """
    Daily task: for each SavedSearch with notify=True, find LocalListings created
    after last_notified_at, create in-app Notification + send_notification.
    Idempotent: last_notified_at is updated after processing.
    """
    from django.utils import timezone

    from local_listings.models import LocalListing
    from notifications.models import Notification as NotifModel
    from notifications.services import create_notification

    from .models import SavedSearch

    now = timezone.now()
    processed = 0

    for ss in SavedSearch.objects.filter(notify=True).select_related('user'):
        since = ss.last_notified_at or ss.created_at
        qs = _apply_filters(LocalListing.objects.filter(
            status=LocalListing.Status.ACTIVE,
            created_at__gt=since,
        ), ss.filters)

        listings = list(qs[:10])
        if not listings:
            continue

        for listing in listings:
            title = f'Нове авто за пошуком «{ss.name}»'
            text = f'{listing.make} {listing.model} {listing.year}, {listing.price} {listing.currency}'
            link = f'/local/{listing.pk}'
            create_notification(ss.user_id, NotifModel.Type.SAVED_SEARCH_MATCH, title, text, link)

        ss.last_notified_at = now
        ss.save(update_fields=['last_notified_at'])

        # Telegram notification (summary)
        try:
            from integrations.tasks import send_notification
            summary = f'🔔 За пошуком «{ss.name}» знайдено {len(listings)} нових авто!'
            send_notification.delay(ss.user_id, summary)
        except Exception:
            pass

        processed += 1

    logger.info('check_saved_searches: оброблено %d saved searches', processed)
    return {'processed': processed}


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
