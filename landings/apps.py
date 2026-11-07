from django.apps import AppConfig


class LandingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'landings'
    verbose_name = 'Сторінки моделей'

    def ready(self):
        from . import signals  # noqa: F401
