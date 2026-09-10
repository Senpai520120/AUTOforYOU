from django.conf import settings
from django.db import models

from pricing.models import Calculation
from vehicles.models import Vehicle


# Вынесены на уровень модуля, чтобы их было видно из тела Meta: вложенные
# классы оттуда недоступны — тело Meta не видит область имён внешнего класса.
# Внутри Listing оставлены псевдонимы, поэтому Listing.Channel.RETAIL и
# прочие обращения по всему коду продолжают работать.
class ListingCurrency(models.TextChoices):
    USD = 'USD', 'USD'
    UAH = 'UAH', 'UAH'
    EUR = 'EUR', 'EUR'


class ListingChannel(models.TextChoices):
    RETAIL = 'retail', 'Розница'
    WHOLESALE = 'wholesale', 'Опт'


class ListingStatus(models.TextChoices):
    IN_TRANSIT = 'in_transit', 'В пути'
    IN_STOCK = 'in_stock', 'В наличии'
    SOLD = 'sold', 'Продан'


class Listing(models.Model):
    Currency = ListingCurrency
    Channel = ListingChannel
    ListingStatus = ListingStatus

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
        indexes = [
            models.Index(fields=['status'], name='listing_status_idx'),
            models.Index(fields=['channel'], name='listing_channel_idx'),
            models.Index(fields=['channel', 'status'], name='listing_channel_status_idx'),
            models.Index(fields=['price'], name='listing_price_idx'),
        ]
        # Django проверяет choices только при full_clean(), а .save() и
        # .update() пишут что угодно. В БД уже лежал status='active', которого
        # нет среди вариантов: карточка в каталоге показывала сырое значение
        # вместо перевода. Ограничение на уровне БД закрывает все пути записи.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[c[0] for c in ListingStatus.choices]),
                name='listing_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(channel__in=[c[0] for c in ListingChannel.choices]),
                name='listing_channel_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(currency__in=[c[0] for c in ListingCurrency.choices]),
                name='listing_currency_valid',
            ),
        ]

    def __str__(self):
        return f'{self.vehicle} — {self.price} {self.currency} [{self.status}]'

    @property
    def is_wholesale(self):
        return self.channel == self.Channel.WHOLESALE
