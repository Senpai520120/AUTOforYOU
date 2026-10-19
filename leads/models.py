from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class LeadStatus(models.TextChoices):
    NEW = 'new', 'Нова'
    IN_PROGRESS = 'in_progress', 'У роботі'
    CONTRACT = 'contract', 'Договір'
    CAR_BOUGHT = 'car_bought', 'Авто куплено'
    IN_TRANSIT = 'in_transit', 'В дорозі'
    CUSTOMS = 'customs', 'Розмитнення'
    DELIVERED = 'delivered', 'Видано'
    REJECTED = 'rejected', 'Відмова'
    SPAM = 'spam', 'Спам'


class PartnerStatus(models.TextChoices):
    """Статус со слов партнёра; брокер вносит вручную, не смешивать с LeadStatus."""
    NO_ANSWER = 'no_answer', 'Не додзвонились'
    THINKING = 'thinking', 'Думає'
    DEPOSIT = 'deposit', 'Депозит'
    BOUGHT = 'bought', 'Куплено'
    REJECTED = 'rejected', 'Відмова'


class LeadSource(models.TextChoices):
    CALCULATOR = 'calculator', 'Калькулятор'
    LISTING = 'listing', 'Лот'
    LANDING = 'landing', 'Лендінг'


class ContactMethod(models.TextChoices):
    PHONE = 'phone', 'Дзвінок'
    TELEGRAM = 'telegram', 'Telegram'
    VIBER = 'viber', 'Viber'


class NeededWhen(models.TextChoices):
    ASAP = 'asap', 'Якнайшвидше'
    MONTH = 'month', 'Протягом місяця'
    THREE_MONTHS = 'three_months', 'Протягом 3 місяців'
    LATER = 'later', 'Пізніше / поки придивляюсь'


class LeadCounter(models.Model):
    """Счётчик номеров заявок по году (читается под select_for_update)."""
    year = models.PositiveIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Лічильник заявок'
        verbose_name_plural = 'Лічильники заявок'

    def __str__(self):
        return f'{self.year}: {self.last_number}'


class Lead(models.Model):
    public_id = models.CharField('Номер', max_length=16, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='leads', verbose_name='Користувач',
    )
    name = models.CharField('Імʼя', max_length=100)
    phone = models.CharField('Телефон', max_length=16)
    email = models.EmailField('Email', blank=True)
    contact_method = models.CharField('Спосіб звʼязку', max_length=16, choices=ContactMethod.choices, blank=True)
    contact_handle = models.CharField('Нік / контакт', max_length=64, blank=True)
    comment = models.CharField('Коментар', max_length=1000, blank=True)
    source = models.CharField('Точка входу', max_length=16, choices=LeadSource.choices)
    landing_slug = models.CharField('Лендінг', max_length=100, blank=True)

    budget_usd = models.DecimalField('Бюджет, USD', max_digits=10, decimal_places=2, null=True, blank=True,
                                     validators=[MinValueValidator(0)])
    needed_when = models.CharField('Коли потрібне авто', max_length=16, choices=NeededWhen.choices, blank=True)
    city = models.CharField('Місто', max_length=100, blank=True)
    vehicle_label = models.CharField('Марка / модель', max_length=150, blank=True)

    utm = models.JSONField('UTM', default=dict, blank=True)
    referrer = models.CharField(max_length=500, blank=True)
    entry_page_url = models.CharField(max_length=500, blank=True)
    page_url = models.CharField(max_length=500, blank=True)

    calculation = models.ForeignKey(
        'pricing.Calculation', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='leads', verbose_name='Розрахунок',
    )
    listing = models.ForeignKey(
        'listings.Listing', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='leads', verbose_name='Лот',
    )
    calculation_snapshot = models.JSONField('Знімок розрахунку', default=dict, blank=True)
    total_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_uah = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    status = models.CharField('Статус', max_length=16, choices=LeadStatus.choices, default=LeadStatus.NEW)
    partner_status = models.CharField('Статус партнера', max_length=16, choices=PartnerStatus.choices, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assigned_leads', verbose_name='Відповідальний',
    )
    first_response_at = models.DateTimeField('Перша відповідь', null=True, blank=True)

    consent_at = models.DateTimeField('Згода на обробку ПДн')
    partner_name = models.CharField('Партнер (знімок)', max_length=255)
    partner_consent_at = models.DateTimeField('Згода на передачу партнеру')
    partner_consent_text = models.CharField('Текст згоди партнеру', max_length=500)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='lead_status_created_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[c[0] for c in LeadStatus.choices]),
                name='lead_status_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=[c[0] for c in LeadSource.choices]),
                name='lead_source_valid',
            ),
            models.CheckConstraint(
                condition=models.Q(budget_usd__isnull=True) | models.Q(budget_usd__gte=0),
                name='lead_budget_non_negative',
            ),
        ]

    def __str__(self):
        return self.public_id


class LeadStatusChange(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='status_changes')
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Зміна статусу заявки'
        verbose_name_plural = 'Зміни статусу заявок'
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.lead_id}: {self.from_status} -> {self.to_status}'
