from django.apps import AppConfig


class LocalListingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'local_listings'
    verbose_name = 'Місцеві оголошення'

    def ready(self):
        from . import signals  # noqa: F401  8.4: удаление файлов фото
