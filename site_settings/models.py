from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

PUBLIC_CACHE_KEY = 'site_settings:public'


class OwnerLegalForm(models.TextChoices):
    FOP = 'fop', 'ФОП'
    TOV = 'tov', 'ТОВ'
    OTHER = 'other', 'Інше'


owner_code_validator = RegexValidator(
    r'^(\d{8}|\d{10})$',
    'ЄДРПОУ — 8 цифр, РНОКПП — 10 цифр.',
)


class SiteSettings(models.Model):
    """Singleton (pk=1): реквізити власника ПДн, контакти, юридичні документи."""

    # Власник ПДн
    owner_legal_form = models.CharField(
        'Правова форма', max_length=10, choices=OwnerLegalForm.choices, blank=True, default='',
        help_text='ФОП / ТОВ / інше — з виписки ЄДР.',
    )
    owner_legal_name = models.CharField(
        'Юридична назва', max_length=255, blank=True, default='',
        help_text='Повна назва з виписки ЄДР (для ФОП — ПІБ).',
    )
    owner_code = models.CharField(
        'ЄДРПОУ / РНОКПП', max_length=10, blank=True, default='', validators=[owner_code_validator],
        help_text='8 цифр (ЄДРПОУ) або 10 цифр (РНОКПП). Ті самі реквізити, що для мерчанта LiqPay.',
    )
    owner_address = models.TextField(
        'Адреса', blank=True, default='', help_text='Юридична адреса з виписки ЄДР.',
    )

    # Контакти
    support_email = models.EmailField('Email підтримки', blank=True, default='')
    privacy_email = models.EmailField(
        'Email для звернень щодо ПДн', blank=True, default='',
        help_text='Сюди суб\'єкти ПДн надсилають запити (доступ, видалення).',
    )
    phone = models.CharField('Телефон', max_length=32, blank=True, default='')
    manager_contact = models.CharField(
        'Контакт менеджера', max_length=255, blank=True, default='',
        help_text='Показується клієнтам у кабінеті відстеження доставки.',
    )
    telegram_channel_url = models.URLField('Посилання на Telegram-канал', blank=True, default='')

    # Партнер
    partner_name = models.CharField(
        'Назва партнера', max_length=255, blank=True, default='',
        help_text='Заповнити після підписання договору. Поки порожньо — згода на передачу даних партнеру неактивна.',
    )
    partner_legal_name = models.CharField(
        'Юрособа партнера', max_length=255, blank=True, default='',
        help_text='Для політики конфіденційності (отримувач даних).',
    )

    # ПДн і документи
    data_retention_years = models.PositiveSmallIntegerField(
        'Строк зберігання платіжних документів, років', null=True, blank=True,
        validators=[MinValueValidator(1)],
        help_text='Платіжні документи й знеособлені угоди. Цифру надає бухгалтер; до відповіді — порожньо.',
    )
    log_retention_days = models.PositiveIntegerField(
        'Строк зберігання журналів з IP, днів', default=90, validators=[MinValueValidator(1)],
    )
    account_deletion_grace_days = models.PositiveIntegerField(
        'Період скасування видалення акаунта, днів', default=14, validators=[MinValueValidator(1)],
    )
    legal_docs_approved = models.BooleanField(
        'Юридичні документи перевірено юристом', default=False,
        help_text='Поки не відмічено, на сторінках показується плашка «Шаблон».',
    )
    legal_docs_updated_at = models.DateField(
        'Дата редакції документів', null=True, blank=True, help_text='Одна дата для всіх документів.',
    )
    legal_docs_version = models.CharField(
        'Версія документів', max_length=32, blank=True, default='',
        help_text='Наприклад 2026-10-01. Змінюйте при кожній правці тексту.',
    )
    legal_docs_reconsent_required = models.BooleanField(
        'Потрібна повторна згода', default=False,
        help_text='Тільки якщо змінились категорії даних, цілі, отримувачі або строки зберігання.',
    )

    updated_at = models.DateTimeField('Оновлено', auto_now=True)

    class Meta:
        verbose_name = 'Налаштування сайту'
        verbose_name_plural = 'Налаштування сайту'

    def __str__(self):
        return 'Налаштування сайту'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def owner_configured(self) -> bool:
        return all([self.owner_legal_form, self.owner_legal_name, self.owner_code, self.owner_address])
