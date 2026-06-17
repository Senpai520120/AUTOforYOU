from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class CustomUserManager(BaseUserManager):
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
        ADMIN = 'admin', 'Администратор'

    objects = CustomUserManager()

    username = None
    email = models.EmailField(unique=True, verbose_name='Email')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.BUYER, verbose_name='Роль')
    is_verified_dealer = models.BooleanField(default=False, verbose_name='Верифицированный дилер')
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.email


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
