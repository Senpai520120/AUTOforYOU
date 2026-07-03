from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        NEW_MESSAGE = 'new_message', 'Нове повідомлення'
        LISTING_APPROVED = 'listing_approved', 'Оголошення опубліковано'
        LISTING_REJECTED = 'listing_rejected', 'Оголошення відхилено'
        LISTING_EXPIRING = 'listing_expiring', 'Оголошення скоро закінчується'  # stub, C2C-промт 5
        SAVED_SEARCH_MATCH = 'saved_search_match', 'Нове авто за збереженим пошуком'
        DEAL_PROPOSED = 'deal_proposed', 'Пропозиція угоди'
        DEAL_CONFIRMED = 'deal_confirmed', 'Угода підтверджена'
        DEAL_CANCELLED = 'deal_cancelled', 'Угода скасована'
        REVIEW_RECEIVED = 'review_received', 'Новий відгук'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    type = models.CharField(max_length=30, choices=Type.choices, db_index=True)
    title = models.CharField(max_length=255)
    text = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.type}] {self.title} → {self.user_id}'
