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
