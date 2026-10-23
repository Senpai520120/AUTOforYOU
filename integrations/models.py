from django.db import models


class RegistryReport(models.Model):
    """Кэш отчётов из украинских реестров (Opendatabot и будущих провайдеров)."""
    vin = models.CharField(max_length=17, blank=True, null=True, verbose_name='VIN')
    plate = models.CharField(max_length=20, blank=True, null=True, verbose_name='Госномер')
    provider = models.CharField(max_length=50, verbose_name='Провайдер')
    payload = models.JSONField(verbose_name='Данные отчёта')
    demo = models.BooleanField(default=False, verbose_name='Демо-данные')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Отчёт реестра UA'
        verbose_name_plural = 'Отчёты реестра UA'
        ordering = ['-created_at']

    def __str__(self):
        key = self.vin or self.plate or '—'
        flag = ' [ДЕМО]' if self.demo else ''
        return f'{self.provider}: {key}{flag}'


class VinReport(models.Model):
    """Кэш VIN-отчётов — не повторяем запрос к провайдеру по тому же VIN."""
    vin = models.CharField(max_length=17, verbose_name='VIN')
    provider = models.CharField(max_length=50, verbose_name='Провайдер')
    report_data = models.JSONField(verbose_name='Данные отчёта')
    demo = models.BooleanField(default=False, verbose_name='Демо-данные')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'VIN-отчёт'
        verbose_name_plural = 'VIN-отчёты'
        unique_together = [('vin', 'provider')]
        ordering = ['-created_at']

    def __str__(self):
        flag = ' [ДЕМО]' if self.demo else ''
        return f'{self.vin} / {self.provider}{flag}'


class IntegrationHealth(models.Model):
    """Журнал здоровья внешнего провайдера: последний успех и последняя ошибка (задача 3.1).

    Без него админ не увидит сбои: логи он не читает. Текст ошибки хранится без секретов.
    """
    provider_key = models.CharField(max_length=50, unique=True, verbose_name='Ключ провайдера')
    last_success_at = models.DateTimeField(null=True, blank=True, verbose_name='Последний успех')
    last_error_at = models.DateTimeField(null=True, blank=True, verbose_name='Последняя ошибка')
    last_error = models.CharField(max_length=500, blank=True, verbose_name='Текст последней ошибки')
    error_count = models.PositiveIntegerField(default=0, verbose_name='Число ошибок')

    class Meta:
        verbose_name = 'Здоровье интеграции'
        verbose_name_plural = 'Здоровье интеграций'
        ordering = ['provider_key']

    def __str__(self):
        return self.provider_key
