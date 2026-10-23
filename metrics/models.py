from django.db import models


class MetricKey(models.TextChoices):
    """Ключи счётчиков. Новый ключ - одной строкой (8.8 и этап 9 расширяют перечень)."""
    CALCULATOR_VISIT = 'calculator_visit', 'Візит калькулятора'
    CALCULATION = 'calculation', 'Розрахунок'
    LEAD = 'lead', 'Заявка'
    REGISTRATION = 'registration', 'Реєстрація'
    LISTING_SUBMITTED = 'listing_submitted', 'Подано оголошення'
    PHONE_VIEW = 'phone_view', 'Показ телефону'
    MOBILE_BAR_CLICK = 'mobile_bar_click', 'Клік по мобільній панелі'


class DailyMetric(models.Model):
    """Счётчик по дню и ключу. Ни user, ни IP, ни URL, ни иных идентификаторов (бриф §3)."""
    date = models.DateField('Дата', db_index=True)
    key = models.CharField('Ключ', max_length=40, choices=MetricKey.choices)
    value = models.BigIntegerField('Значення', default=0)

    class Meta:
        verbose_name = 'Щоденна метрика'
        verbose_name_plural = 'Щоденні метрики'
        ordering = ['-date', 'key']
        constraints = [
            models.UniqueConstraint(fields=['date', 'key'], name='uniq_dailymetric_date_key'),
        ]

    def __str__(self):
        return f'{self.date} {self.key}: {self.value}'
