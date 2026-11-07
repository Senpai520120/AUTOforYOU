from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    name = 'integrations'

    def ready(self):
        from . import checks  # noqa: F401 - регистрирует system checks
        from .registry import register_builtin_providers

        register_builtin_providers()
