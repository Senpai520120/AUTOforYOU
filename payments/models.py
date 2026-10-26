from django.conf import settings
from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Очікування'
        COMPLETED = 'completed', 'Виконано'
        FAILED = 'failed', 'Відхилено'
        REVERSED = 'reversed', 'Повернення'

    class Purpose(models.TextChoices):
        LISTING_VIP = 'listing_vip', 'VIP-оголошення'
        LISTING_UNLOCK = 'listing_unlock', 'Розблокування оголошення'
        LOCAL_LISTING_PROMOTE = 'local_listing_promote', 'Просування оголошення'
        OTHER = 'other', 'Інше'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payments',
        verbose_name='Користувач',
    )
    listing = models.ForeignKey(
        'listings.Listing',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payments',
        verbose_name='Оголошення',
    )
    local_listing = models.ForeignKey(
        'local_listings.LocalListing',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payments',
        verbose_name='Місцеве оголошення',
    )
    tariff = models.ForeignKey(
        'local_listings.PromotionTariff',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='payments',
        verbose_name='Тариф',
    )
    order_id = models.CharField(max_length=100, unique=True, verbose_name='Номер замовлення')
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сума')
    currency = models.CharField(max_length=3, default='USD', verbose_name='Валюта')
    description = models.CharField(max_length=255, blank=True, verbose_name='Опис')
    purpose = models.CharField(
        max_length=30,
        choices=Purpose.choices,
        default=Purpose.OTHER,
        verbose_name='Призначення платежу',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Статус',
    )
    liqpay_payment_id = models.CharField(max_length=100, blank=True, verbose_name='ID платежу LiqPay')
    liqpay_status = models.CharField(max_length=50, blank=True, verbose_name='Статус LiqPay')
    liqpay_raw = models.JSONField(null=True, blank=True, verbose_name='Сира відповідь LiqPay')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Платіж'
        verbose_name_plural = 'Платежі'
        ordering = ['-created_at']

    def __str__(self):
        return f'Платіж #{self.order_id} — {self.amount} {self.currency} [{self.status}]'

    def unlock_listing(self):
        if self.listing and self.status == self.Status.COMPLETED:
            self.listing.status = 'in_stock'
            self.listing.save(update_fields=['status'])
