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
        NEW_LEAD = 'new_lead', 'Нова заявка брокеру'
        LEAD_UNDELIVERED = 'lead_undelivered', 'Заявку не доставлено брокеру'

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
        # Счётчик непрочитанных и список без полного скана (4.7, 06-Q13).
        indexes = [models.Index(fields=['user', 'is_read'], name='notif_user_is_read_idx')]

    def __str__(self):
        return f'[{self.type}] {self.title} → {self.user_id}'


class NotificationTemplate(models.Model):
    """Текст уведомления, редактируемый в админке (4.7, 06-C5). Плейсхолдеры - в notifications/defaults.py."""
    code = models.CharField(max_length=30, choices=Notification.Type.choices, unique=True, verbose_name='Тип')
    title = models.CharField(max_length=255, verbose_name='Заголовок',
                             help_text='Плейсхолдери: {listing}, {sender}, {preview}, {rating}')
    text = models.TextField(blank=True, verbose_name='Текст',
                            help_text='Плейсхолдери: {listing}, {sender}, {preview}, {rating}')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Шаблон сповіщення'
        verbose_name_plural = 'Шаблони сповіщень'

    def __str__(self):
        return self.get_code_display()
