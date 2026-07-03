from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class Deal(models.Model):
    class Status(models.TextChoices):
        PROPOSED = 'proposed', 'Запропоновано'
        CONFIRMED = 'confirmed', 'Підтверджено'
        CANCELLED = 'cancelled', 'Скасовано'

    listing = models.ForeignKey(
        'local_listings.LocalListing',
        on_delete=models.CASCADE,
        related_name='deals',
        verbose_name='Оголошення',
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deals_as_seller',
        verbose_name='Продавець',
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deals_as_buyer',
        verbose_name='Покупець',
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROPOSED, verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='Підтверджено о')

    class Meta:
        verbose_name = 'Угода'
        verbose_name_plural = 'Угоди'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['listing', 'buyer'],
                name='unique_deal_listing_buyer',
            ),
        ]

    def __str__(self):
        return f'Угода #{self.pk}: {self.seller.email} → {self.buyer.email} [{self.status}]'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.seller_id and self.buyer_id and self.seller_id == self.buyer_id:
            raise ValidationError('Продавець і покупець не можуть бути однією особою.')


class Review(models.Model):
    deal = models.OneToOneField(
        Deal,
        on_delete=models.CASCADE,
        related_name='review',
        verbose_name='Угода',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_written',
        verbose_name='Автор',
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received',
        verbose_name='Про кого',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Оцінка (1-5)',
    )
    text = models.TextField(blank=True, verbose_name='Відгук')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Відгук'
        verbose_name_plural = 'Відгуки'
        ordering = ['-created_at']

    def __str__(self):
        return f'Відгук #{self.pk}: {self.rating}★ від {self.author.email} про {self.target.email}'
