from django.db import models


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
