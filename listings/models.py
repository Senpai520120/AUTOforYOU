from django.conf import settings
from django.db import models

from vehicles.models import Vehicle
from pricing.models import Calculation


class Listing(models.Model):
    class Currency(models.TextChoices):
        USD = 'USD', 'USD'
        UAH = 'UAH', 'UAH'
        EUR = 'EUR', 'EUR'

    class Channel(models.TextChoices):
        RETAIL = 'retail', 'Розница'
        WHOLESALE = 'wholesale', 'Опт'

    class ListingStatus(models.TextChoices):
        IN_TRANSIT = 'in_transit', 'В пути'
        IN_STOCK = 'in_stock', 'В наличии'
        SOLD = 'sold', 'Продан'

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='listings', verbose_name='Автомобиль')
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='listings',
        verbose_name='Продавец',
    )
    calculation = models.ForeignKey(
        Calculation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='listings',
        verbose_name='Расчёт стоимости',
    )
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Цена')
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD, verbose_name='Валюта')
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.RETAIL, verbose_name='Канал')
    status = models.CharField(max_length=15, choices=ListingStatus.choices, default=ListingStatus.IN_TRANSIT, verbose_name='Статус')
    repair_description = models.TextField(blank=True, verbose_name='Описание ремонта')
    # B2B поля
    is_express_buyout = models.BooleanField(default=False, verbose_name='Срочный выкуп')
    express_buyout_until = models.DateTimeField(null=True, blank=True, verbose_name='Срочный выкуп до')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Объявление'
        verbose_name_plural = 'Объявления'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.vehicle} — {self.price} {self.currency} [{self.status}]'

    @property
    def is_wholesale(self):
        return self.channel == self.Channel.WHOLESALE
