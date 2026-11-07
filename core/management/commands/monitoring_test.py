"""Проверка подключения мониторинга ошибок (задача 7.6): отправляет тестовое событие."""
from django.core.management.base import BaseCommand

from core.monitoring import capture_message, init_monitoring


class Command(BaseCommand):
    help = 'Отправляет тестовое событие в мониторинг ошибок (SENTRY_DSN) и печатает, включён ли он.'

    def handle(self, *args, **options):
        if not init_monitoring('web'):
            self.stdout.write('Мониторинг ошибок выключен: SENTRY_DSN не задан или недействителен.')
            return
        capture_message('AUTOforYOU: тестовое событие monitoring_test', level='info', extra={'component': 'web'})
        import sentry_sdk
        sentry_sdk.flush(timeout=10)
        self.stdout.write(self.style.SUCCESS('Тестовое событие отправлено. Проверьте панель мониторинга.'))
