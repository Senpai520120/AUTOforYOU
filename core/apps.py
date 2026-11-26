from django.apps import AppConfig
from django.core.checks import register


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from core.ssr import check_ssr_key

        register(check_ssr_key)
