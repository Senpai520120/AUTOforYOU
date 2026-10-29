"""System checks интеграций (задача 3.1). Не обращаются к БД."""
from django.conf import settings
from django.core.checks import Error, Warning, register

from .base import MODE_DEMO, MODE_REAL, allowed_modes, configured_mode, mode_setting_name
from .registry import get_providers, get_statuses


@register()
def check_integration_modes(app_configs=None, **kwargs):
    messages = []
    for provider in get_providers():
        setting = mode_setting_name(provider.key)
        value = configured_mode(provider.key)
        if value not in allowed_modes(provider.key):
            messages.append(Error(
                f'{setting}={value!r}: недопустиме значення.',
                hint=f'Допустимо: {", ".join(allowed_modes(provider.key))}. Виправте опечатку в .env.',
                id='integrations.E001',
            ))
    for status in get_statuses(with_health=False):
        if status.mode == MODE_REAL and not status.configured:
            messages.append(Warning(
                f'{status.title}: режим real, але ключі не налаштовані ({status.reason}).',
                hint=f'Задайте змінні {", ".join(status.env_vars)} або поставте {status.mode_setting}=auto.',
                id='integrations.W001',
            ))
        if not settings.DEBUG and status.mode == MODE_DEMO and status.key in ('email', 'telegram'):
            messages.append(Error(
                f'{status.title}: {status.mode_setting}=demo при DEBUG=False - тексти повідомлень '
                '(листи зі посиланнями, Telegram) зберігаються в Outbox.',
                hint=f'На проді поставте {status.mode_setting}=auto або real.',
                id='integrations.E002',
            ))
        elif not settings.DEBUG and status.mode == MODE_DEMO and status.key == 'liqpay':
            messages.append(Warning(
                f'{status.title}: sandbox при DEBUG=False - реальні гроші не списуються.',
                hint=f'Для бойових платежів поставте {status.mode_setting}=real і бойові ключі.',
                id='integrations.W002',
            ))
        elif not settings.DEBUG and status.mode == MODE_DEMO:
            messages.append(Warning(
                f'{status.title}: режим demo при DEBUG=False.',
                hint=f'На проді поставте {status.mode_setting}=auto або real.',
                id='integrations.W002',
            ))
    return messages
