"""
WSGI config for core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_wsgi_application()

# Мониторинг ошибок (7.6): только в серверном процессе (не в manage.py-командах и тестах), после
# настройки Django - чтобы строка «мониторинг выключен» попала в лог. Пустой SENTRY_DSN - выключен.
from core.monitoring import init_monitoring  # noqa: E402

init_monitoring('web')
