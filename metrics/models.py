from django.db import models


class MetricKey(models.TextChoices):
    """Ключи дневных счётчиков (8.7). Новый ключ - одна строка (8.8 и этап 9 расширяют перечень)."""
    CALCULATOR_VISIT = 'calculator_visit', 'Візит калькулятора'
    CALCULATION = 'calculation', 'Розрахунок'
    LEAD = 'lead', 'Заявка'
    REGISTRATION = 'registration', 'Реєстрація'
    LISTING_SUBMITTED = 'listing_submitted', 'Подане оголошення'
    PHONE_VIEW = 'phone_view', 'Показ телефону'
    MOBILE_BAR_CLICK = 'mobile_bar_click', 'Клік мобільної панелі'


class DailyMetric(models.Model):
    """Агрегат за день по ключу. Без user, IP, URL и любых идентификаторов (бриф §3): согласие не нужно."""
    date = models.DateField('Дата')
    key = models.CharField('Метрика', max_length=40, choices=MetricKey.choices)
    value = models.BigIntegerField('Значення', default=0)

    class Meta:
        verbose_name = 'Щоденна метрика'
        verbose_name_plural = 'Щоденні метрики'
        ordering = ['-date', 'key']
        constraints = [models.UniqueConstraint(fields=['date', 'key'], name='metrics_dailymetric_date_key_uniq')]

    def __str__(self):
        return f'{self.date} {self.key}: {self.value}'
