"""System checks интеграций (задача 3.1). Не обращаются к БД."""
from django.conf import settings
from django.core.checks import Error, Warning, register

from .base import MODE_DEMO, MODE_REAL, MODES, configured_mode, mode_setting_name
from .registry import get_providers, get_statuses


@register()
def check_integration_modes(app_configs=None, **kwargs):
    messages = []
    for provider in get_providers():
        setting = mode_setting_name(provider.key)
        value = configured_mode(provider.key)
        if value not in MODES:
            messages.append(Error(
                f'{setting}={value!r}: недопустиме значення.',
                hint='Допустимо: auto, real, demo, off. Виправте опечатку в .env.',
                id='integrations.E001',
            ))
    for status in get_statuses(with_health=False):
        if status.mode == MODE_REAL and not status.configured:
            messages.append(Warning(
                f'{status.title}: режим real, але ключі не налаштовані ({status.reason}).',
                hint=f'Задайте змінні {", ".join(status.env_vars)} або поставте {status.mode_setting}=auto.',
                id='integrations.W001',
            ))
        if not settings.DEBUG and status.mode == MODE_DEMO:
            messages.append(Warning(
                f'{status.title}: режим demo при DEBUG=False.',
                hint=f'На проді поставте {status.mode_setting}=auto або real.',
                id='integrations.W002',
            ))
    return messages
