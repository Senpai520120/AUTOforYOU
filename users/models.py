from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ConsentDocument(models.TextChoices):
    TERMS = 'terms', 'Умови використання'
    PRIVACY = 'privacy', 'Політика конфіденційності'
    DEALER_PROCESSING = 'dealer_processing', 'Обробка даних (заявка дилера)'
    LEAD_PROCESSING = 'lead_processing', 'Обробка даних (заявка на підбір)'
    AGE_18 = 'age_18', 'Підтвердження 18+'
    PARTNER_TRANSFER = 'partner_transfer', 'Передача контактів партнеру'


class ConsentMethod(models.TextChoices):
    REGISTER = 'register', 'Реєстрація'
    DEALER_FORM = 'dealer_form', 'Заявка дилера'
    LEAD_FORM = 'lead_form', 'Заявка на підбір'


class CustomUserManager(BaseUserManager):
    def brokers_and_admins(self):
        """Брокеры и администраторы (роль), включая суперпользователей."""
        return self.filter(
            models.Q(role=CustomUser.Role.BROKER)
            | models.Q(role=CustomUser.Role.ADMIN, is_staff=True)
            | models.Q(is_superuser=True)
        )

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        BUYER = 'buyer', 'Покупатель'
        DEALER = 'dealer', 'Перекупщик'
        BROKER = 'broker', 'Брокер'
        MODERATOR = 'moderator', 'Модератор'
        ADMIN = 'admin', 'Администратор'

    objects = CustomUserManager()

    username = None
    email = models.EmailField(unique=True, verbose_name='Email')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.BUYER, verbose_name='Роль')
    is_verified_dealer = models.BooleanField(default=False, verbose_name='Верифицированный дилер')
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, verbose_name='Telegram ID')
    agreed_to_terms_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата згоди з умовами')
    is_banned = models.BooleanField(default=False, verbose_name='Забанений')
    is_email_verified = models.BooleanField(default=False, verbose_name='Email підтверджено')
    # Версия сессий (1.7): claim `sv` в JWT. revoke_all_sessions увеличивает её, токены со старой
    # версией (и без claim, как версия 0) отклоняются сразу - и access, и refresh.
    session_version = models.PositiveIntegerField(default=0, verbose_name='Версія сесій')
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.email

    @property
    def is_admin_role(self):
        # Голое поле role прав не даёт: admin подтверждается is_staff (его ставит только админка).
        return self.is_superuser or (self.role == self.Role.ADMIN and self.is_staff)

    @property
    def is_broker(self):
        return self.role == self.Role.BROKER

    @property
    def is_moderator(self):
        return self.role == self.Role.MODERATOR


class TrustedShop(models.Model):
    class ShopType(models.TextChoices):
        SERVICE = 'service', 'СТО'
        PAINTER = 'painter', 'Маляр/кузовщик'
        PARTS = 'parts', 'Запчасти'
        OTHER = 'other', 'Другое'

    owner = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE,
        related_name='trusted_shops', verbose_name='Владелец'
    )
    name = models.CharField(max_length=200, verbose_name='Название')
    type = models.CharField(max_length=10, choices=ShopType.choices, default=ShopType.SERVICE, verbose_name='Тип')
    contacts = models.TextField(blank=True, verbose_name='Контакты')
    rating = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Рейтинг (1-5)'
    )
    notes = models.TextField(blank=True, verbose_name='Заметки')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Проверенный партнёр'
        verbose_name_plural = 'Проверенные партнёры'
        ordering = ['-rating', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_type_display()}) — {self.owner.email}'


class DealerApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'На рассмотрении'
        APPROVED = 'approved', 'Одобрено'
        REJECTED = 'rejected', 'Отклонено'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='dealer_applications',
        verbose_name='Пользователь',
    )
    company_name = models.CharField(max_length=200, verbose_name='Название компании')
    full_name = models.CharField(max_length=200, verbose_name='ФИО')
    contact_phone = models.CharField(max_length=30, verbose_name='Контактный телефон')
    documents = models.URLField(blank=True, verbose_name='Ссылка на документы')
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, verbose_name='Статус'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_applications',
        verbose_name='Рассмотрел',
    )
    review_notes = models.TextField(blank=True, verbose_name='Заметки рассмотрения')
    # Согласие на обработку ПД. Хранится метка времени, а не булев флаг:
    # доказывать нужно не только факт, но и момент — форма собирает ПІБ,
    # телефон и ссылку на выписку ЄДР.
    agreed_to_processing_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Дата згоди на обробку даних',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Заявка дилера'
        verbose_name_plural = 'Заявки дилеров'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} — {self.company_name} [{self.get_status_display()}]'


class ImmutableError(Exception):
    """Попытка изменить или удалить запись журнала согласий."""


class ConsentRecordQuerySet(models.QuerySet):
    """Журнал только дополняется. SET_NULL при удалении пользователя/заявки идёт через
    Collector (sql.UpdateQuery), а не через QuerySet.update, поэтому продолжает работать."""

    def update(self, **kwargs):
        raise ImmutableError('Журнал згод не змінюється.')

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableError('Журнал згод не змінюється.')

    def delete(self):
        raise ImmutableError('Записи журналу згод не видаляються.')


class ConsentRecord(models.Model):
    """
    Журнал згод: що, коли, якої версії документів і яким способом. Тільки створюється.
    IP, user-agent і текст чекбокса не зберігаються (мінімум ПДн). Запис переживає
    видалення акаунта (user -> NULL) як доказ згоди; строк зберігання визначає юрист.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consent_records', verbose_name='Користувач',
    )
    lead = models.ForeignKey(
        'leads.Lead', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consent_records', verbose_name='Заявка',
    )
    document = models.CharField('Документ', max_length=20, choices=ConsentDocument.choices)
    doc_version = models.CharField('Версія документів', max_length=32, blank=True, default='')
    partner_name = models.CharField(
        'Назва партнера на момент згоди', max_length=255, blank=True, default='',
        help_text='Заповнюється лише для передачі контактів партнеру.',
    )
    given_at = models.DateTimeField('Дата згоди', default=timezone.now, editable=False)
    method = models.CharField('Спосіб', max_length=12, choices=ConsentMethod.choices)
    lead_public_id = models.CharField(
        'Номер заявки (копія)', max_length=20, blank=True, default='',
        help_text='AFY-ГГГГ-NNNN, не ПДн: лишається, коли заявку обезличено або видалено.',
    )

    objects = ConsentRecordQuerySet.as_manager()

    class Meta:
        verbose_name = 'Згода'
        verbose_name_plural = 'Журнал згод'
        ordering = ['-given_at', '-id']
        indexes = [
            models.Index(fields=['user', 'document'], name='consent_user_doc_idx'),
            models.Index(fields=['document', 'doc_version'], name='consent_doc_ver_idx'),
        ]

    def __str__(self):
        return f'{self.document} v{self.doc_version or "-"} {self.given_at:%Y-%m-%d}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableError('Запис журналу згод не змінюється.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableError('Записи журналу згод не видаляються.')
