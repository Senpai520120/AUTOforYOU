from django.conf import settings
from django.db import models
from django.db.models import Q, UniqueConstraint


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = 'spam', 'Спам або реклама'
        WRONG_INFO = 'wrong_info', 'Недостовірна інформація'
        INAPPROPRIATE = 'inappropriate', 'Неприпустимий контент'
        FRAUD = 'fraud', 'Шахрайство'
        DUPLICATE = 'duplicate', 'Дублікат оголошення'
        OTHER = 'other', 'Інше'

    class Status(models.TextChoices):
        NEW = 'new', 'Нова'
        REVIEWED = 'reviewed', 'Розглянута'
        DISMISSED = 'dismissed', 'Відхилена'

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reports_sent',
        verbose_name='Скаржник',
    )
    listing = models.ForeignKey(
        'local_listings.LocalListing',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='reports',
        verbose_name='Оголошення',
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='reports_received',
        verbose_name='Скаржимося на користувача',
    )
    reason = models.CharField(max_length=20, choices=Reason.choices, verbose_name='Причина')
    comment = models.TextField(blank=True, verbose_name='Коментар')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NEW, verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Скарга'
        verbose_name_plural = 'Скарги'
        ordering = ['-created_at']
        constraints = [
            UniqueConstraint(
                fields=['reporter', 'listing'],
                condition=Q(listing__isnull=False, status='new'),
                name='unique_active_report_listing',
            ),
            UniqueConstraint(
                fields=['reporter', 'reported_user'],
                condition=Q(reported_user__isnull=False, status='new'),
                name='unique_active_report_user',
            ),
        ]

    def __str__(self):
        target = f'оголошення #{self.listing_id}' if self.listing_id else f'користувач {self.reported_user_id}'
        return f'Скарга від {self.reporter.email} на {target} [{self.status}]'

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.listing_id and not self.reported_user_id:
            raise ValidationError('Вкажіть оголошення або користувача.')
        if self.listing_id and self.reported_user_id:
            raise ValidationError('Вкажіть тільки одне: або оголошення, або користувача.')
