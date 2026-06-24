import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TelegramLinkToken(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_link_tokens',
        verbose_name='Пользователь',
    )
    expires_at = models.DateTimeField(verbose_name='Истекает')
    used = models.BooleanField(default=False, verbose_name='Использован')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Токен привязки Telegram'
        verbose_name_plural = 'Токены привязки Telegram'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} — {"использован" if self.used else "активен"}'

    def is_valid(self) -> bool:
        return not self.used and self.expires_at > timezone.now()
