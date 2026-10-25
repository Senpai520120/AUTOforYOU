import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
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

    @classmethod
    def revoke_unused(cls, user) -> int:
        """Гасит все неиспользованные токены пользователя: старая ссылка больше не привяжет аккаунт."""
        return cls.objects.filter(user=user, used=False).update(used=True)


def unlink_telegram(user_id: int, only_telegram_id: int | None = None) -> bool:
    """Отвязывает Telegram от аккаунта и аннулирует его неиспользованные токены.

    Общий код для сайта, команды /unlink и заблокированного бота. True, если привязка была.
    `only_telegram_id`: отвязать, только если привязан именно этот id (гонка: пользователь мог
    успеть привязать другой Telegram, новую привязку и токены не трогаем).
    """
    from django.contrib.auth import get_user_model

    qs = get_user_model().objects.filter(pk=user_id, telegram_id__isnull=False)
    if only_telegram_id is not None:
        qs = qs.filter(telegram_id=only_telegram_id)
    with transaction.atomic():
        changed = qs.update(telegram_id=None)
        if changed or only_telegram_id is None:
            TelegramLinkToken.objects.filter(user_id=user_id, used=False).update(used=True)
    return bool(changed)


class BotText(models.Model):
    """Текст бота или шаблон поста, редактируется в админке. Реестр ключей и дефолты - `texts.REGISTRY`."""
    key = models.CharField('Ключ', max_length=64, unique=True)
    text = models.TextField('Текст')
    updated_at = models.DateTimeField('Изменён', auto_now=True)

    class Meta:
        verbose_name = 'Текст Telegram-бота'
        verbose_name_plural = 'Тексти Telegram-бота'
        ordering = ['key']

    def __str__(self):
        return self.key

    def clean(self):
        from telegram_bot.texts import validate_text

        errors = validate_text(self.key, self.text or '')
        if errors:
            raise ValidationError({'text': errors})


@receiver([post_save, post_delete], sender=BotText)
def _invalidate_bot_text(sender, instance, **kwargs):
    from telegram_bot.texts import invalidate

    invalidate(instance.key)
