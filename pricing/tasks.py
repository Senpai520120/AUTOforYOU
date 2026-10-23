import logging
from urllib.error import URLError

from celery import shared_task

from pricing import cache as pricing_cache
from pricing.nbu import fetch_and_save_rates

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(URLError,),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    name='pricing.tasks.fetch_nbu_rates_task',
)
def fetch_nbu_rates_task(self):
    """Получить курсы НБУ и сбросить кэш курсов валют."""
    try:
        updated = fetch_and_save_rates()
    except URLError as exc:
        logger.error('NBU fetch failed: %s', exc)
        raise  # celery autoretry_for поймает и повторит

    pricing_cache.invalidate('exchange')
    logger.info('NBU rates updated: %s', ', '.join(updated) if updated else 'none')
    return updated


@shared_task(name='pricing.tasks.purge_anonymous_calculations')
def purge_anonymous_calculations():
    """Удаляет анонимные расчёты старше ANON_CALCULATION_TTL_DAYS (02-S2).

    Не трогает расчёты пользователей и те, на которые ссылается заявка (Lead) или объявление (Listing).
    Счётчик расчётов (pricing.hooks, 8.7) пишется при создании и от таблицы Calculation не зависит:
    очистка его не читает и не уменьшает.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from pricing.models import Calculation

    cutoff = timezone.now() - timedelta(days=settings.ANON_CALCULATION_TTL_DAYS)
    deleted, _ = (
        Calculation.objects.filter(user__isnull=True, created_at__lt=cutoff)
        .filter(leads__isnull=True, listings__isnull=True)
        .delete()
    )
    logger.info('Anonymous calculations purged: %s', deleted)
    return deleted
