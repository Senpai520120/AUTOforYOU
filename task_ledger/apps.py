from django.apps import AppConfig


class TaskLedgerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'task_ledger'
    verbose_name = 'Невдалі завдання'

    def ready(self):
        from . import signals  # noqa: F401  подключает обработчик task_failure
