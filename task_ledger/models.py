from django.db import models


class FailedTask(models.Model):
    """Окончательно упавшая Celery-задача (после всех повторов), задача 8.9.

    Аргументы - только в безопасном виде (sanitize.safe_repr): без email, телефонов и текстов сообщений.
    """
    task_name = models.CharField('Завдання', max_length=200)
    task_id = models.CharField('ID завдання', max_length=64, blank=True)
    failed_at = models.DateTimeField('Час', auto_now_add=True, db_index=True)
    retries = models.PositiveIntegerField('Повторів', default=0)
    exception_class = models.CharField('Клас помилки', max_length=200, blank=True)
    error = models.TextField('Помилка (без ПДн)', blank=True)
    args = models.JSONField('Аргументи (безпечно)', default=list, blank=True)
    kwargs = models.JSONField('Іменовані аргументи (безпечно)', default=dict, blank=True)
    queue = models.CharField('Черга', max_length=100, blank=True)

    class Meta:
        verbose_name = 'Невдале завдання'
        verbose_name_plural = 'Невдалі завдання'
        ordering = ['-failed_at', '-id']
        indexes = [models.Index(fields=['task_name', 'failed_at'], name='failedtask_name_time_idx')]

    def __str__(self):
        return f'{self.task_name} {self.failed_at:%Y-%m-%d %H:%M}'
