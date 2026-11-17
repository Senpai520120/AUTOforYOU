"""Конфиг Celery: срок жизни задач beat (expire_seconds) и лимиты времени."""
from django.conf import settings
from django.test import TestCase


class BeatScheduleExpiryTests(TestCase):
    def test_no_entry_uses_dropped_expires_key(self):
        # DatabaseScheduler (django-celery-beat 2.9) принимает только expire_seconds, expires отбрасывает молча.
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            self.assertNotIn('expires', entry.get('options', {}), name)

    def test_expiring_entries_use_expire_seconds(self):
        expected = {'celery-heartbeat': 240, 'failed-task-alert': 540, 'disk-usage-alert': 1500,
                    'weekly-funnel-report': 86400, 'cleanup-contact-views-daily': 86400}
        for name, seconds in expected.items():
            self.assertEqual(settings.CELERY_BEAT_SCHEDULE[name]['options'], {'expire_seconds': seconds}, name)

    def test_database_scheduler_stores_expire_seconds(self):
        from django_celery_beat.models import PeriodicTask
        from django_celery_beat.schedulers import ModelEntry

        from core.celery import app
        entry = dict(settings.CELERY_BEAT_SCHEDULE['celery-heartbeat'])
        model_entry = ModelEntry.from_entry('celery-heartbeat', app=app, **entry)
        task = PeriodicTask.objects.get(name='celery-heartbeat')
        self.assertEqual(task.expire_seconds, 240)
        self.assertIsNotNone(model_entry)


class TimeLimitTests(TestCase):
    def test_default_limits(self):
        self.assertEqual(settings.CELERY_TASK_SOFT_TIME_LIMIT, 120)
        self.assertEqual(settings.CELERY_TASK_TIME_LIMIT, 180)
        self.assertLess(settings.CELERY_TASK_SOFT_TIME_LIMIT, settings.CELERY_TASK_TIME_LIMIT)
