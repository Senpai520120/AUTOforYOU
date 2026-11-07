import os

from celery import Celery
from celery.signals import beat_init, worker_process_init

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('autoforyou')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


# Мониторинг ошибок (7.6): в каждом процессе воркера и в beat. Пустой SENTRY_DSN - выключен.
@worker_process_init.connect
def _init_monitoring_worker(**kwargs):
    from core.monitoring import init_monitoring
    init_monitoring('celery')


@beat_init.connect
def _init_monitoring_beat(**kwargs):
    from core.monitoring import init_monitoring
    init_monitoring('celery')
