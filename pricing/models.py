from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class DateRangeModel(models.Model):
    """Тариф с периодом действия (02-Q4).

    valid_to >= valid_from проверяет и clean(), и CheckConstraint в БД. Периоды записей одного ключа
    (overlap_key_fields) не пересекаются - проверка в clean() (админка). Если пересечение всё же
    есть (данные в обход clean), калькулятор берёт запись с самым поздним valid_from.
    """
    valid_from = models.DateField(verbose_name='Действует с')
    valid_to = models.DateField(null=True, blank=True, verbose_name='Действует по')
    # 2.6 (02-C2): пока среди применённых ставок есть непроверенные, сайт показывает демо-баннер.
    is_verified = models.BooleanField(default=False, verbose_name='Перевірено власником')

    overlap_key_fields: tuple = ()

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F('valid_from')),
                name='%(app_label)s_%(class)s_valid_range',
            ),
        ]

    def clean(self):
        super().clean()
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({'valid_to': 'Дата «по» не може бути раніше дати «з».'})
        if self.valid_from is None or self.overlap_key_fields is None:
            return
        same_key = type(self)._default_manager.filter(
            **{f: getattr(self, f) for f in self.overlap_key_fields}
        ).exclude(pk=self.pk)
        # Пересечение [from, to] и [other.from, other.to]; None = без конца.
        same_key = same_key.filter(models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=self.valid_from))
        if self.valid_to is not None:
            same_key = same_key.filter(valid_from__lte=self.valid_to)
        clash = same_key.order_by('valid_from').first()
        if clash is not None:
            raise ValidationError(
                f'Період перетинається з іншим записом (id={clash.pk}, з {clash.valid_from}'
                f'{f" по {clash.valid_to}" if clash.valid_to else ""}). Закрийте старий запис датою «по».'
            )


class AuctionFeeTier(DateRangeModel):
    """
    Тиерный buyer fee аукциона.
    # baseline — сверить с офиц. сеткой и тарифом брокера
    """
    class Auction(models.TextChoices):
        COPART = 'copart', 'Copart'
        IAAI = 'iaai', 'IAAI'

    class MemberType(models.TextChoices):
        PUBLIC = 'public', 'Публичный'
        LICENSED = 'licensed', 'Лицензированный дилер'
        BROKER = 'broker', 'Брокер'

    class PaymentType(models.TextChoices):
        SECURED = 'secured', 'Обеспечённый'
        UNSECURED = 'unsecured', 'Необеспечённый'

    class TitleType(models.TextChoices):
        CLEAN = 'clean', 'Чистый (clean)'
        SALVAGE = 'salvage', 'Salvage / Rebuildable'
        ANY = 'any', 'Любой (не различается)'

    auction = models.CharField(max_length=10, choices=Auction.choices, verbose_name='Аукцион')
    member_type = models.CharField(max_length=10, choices=MemberType.choices, default=MemberType.PUBLIC, verbose_name='Тип участника')
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, default=PaymentType.SECURED, verbose_name='Тип оплаты')
    title_type = models.CharField(max_length=10, choices=TitleType.choices, default=TitleType.ANY, verbose_name='Тип титула')
    bid_min = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Ставка от ($)')
    bid_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Ставка до ($, пусто=без лимита)')
    # Ровно одно из двух:
    fee_flat = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name='Фикс. сбор ($)')
    fee_percent = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True, verbose_name='% от ставки (напр. 0.0600 = 6%)')

    overlap_key_fields = ('auction', 'member_type', 'payment_type', 'title_type', 'bid_min')

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Тиер buyer fee'
        verbose_name_plural = 'Тиеры buyer fee'
        ordering = ['auction', 'member_type', 'bid_min']

    def clean(self):
        super().clean()
        flat_set = self.fee_flat is not None
        pct_set = self.fee_percent is not None
        if flat_set == pct_set:
            raise ValidationError('Задайте ровно одно из fee_flat / fee_percent (не оба и не ни одного).')

    def __str__(self):
        fee_str = f'${self.fee_flat}' if self.fee_flat is not None else f'{(self.fee_percent * 100).normalize()}%'
        return (
            f'{self.auction} [{self.member_type}/{self.payment_type}/{self.title_type}] '
            f'${self.bid_min}–{self.bid_max or "∞"} → {fee_str}'
        )


class AuctionFixedFee(DateRangeModel):
    """
    Фиксированные сборы аукциона (gate, environmental, virtual bid).
    # baseline — сверить с офиц. сеткой и тарифом брокера
    """
    class FeeType(models.TextChoices):
        GATE = 'gate', 'Gate / Service fee'
        ENVIRONMENTAL = 'environmental', 'Environmental fee'
        VIRTUAL_BID = 'virtual_bid', 'Virtual bid fee'

    class TitleType(models.TextChoices):
        CLEAN = 'clean', 'Чистый (clean)'
        SALVAGE = 'salvage', 'Salvage / Rebuildable'
        ANY = 'any', 'Любой'

    auction = models.CharField(max_length=10, choices=AuctionFeeTier.Auction.choices, verbose_name='Аукцион')
    fee_type = models.CharField(max_length=20, choices=FeeType.choices, verbose_name='Тип сбора')
    title_type = models.CharField(
        max_length=10, choices=TitleType.choices, default=TitleType.ANY,
        verbose_name='Тип титула (актуально для gate fee)',
    )
    amount = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Сумма ($)')

    overlap_key_fields = ('auction', 'fee_type', 'title_type')

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Фиксированный сбор аукциона'
        verbose_name_plural = 'Фиксированные сборы аукциона'
        ordering = ['auction', 'fee_type']

    def __str__(self):
        return f'{self.auction} {self.fee_type} [{self.title_type}]: ${self.amount} ({self.valid_from})'


class UsLandRoute(DateRangeModel):
    auction_location = models.CharField(max_length=100, verbose_name='Локация аукциона')
    us_port = models.CharField(max_length=50, verbose_name='Порт США')
    cost_usd = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Стоимость ($)')

    overlap_key_fields = ('auction_location', 'us_port')

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Сухопутная логистика США'
        verbose_name_plural = 'Сухопутная логистика США'

    def __str__(self):
        return f'{self.auction_location} → {self.us_port}: ${self.cost_usd}'


class OceanFreightRate(DateRangeModel):
    # Порт ЕС - данные (02-C4): новый порт добавляется маршрутом в админке, без правки кода.
    us_port = models.CharField(max_length=50, verbose_name='Порт США')
    eu_port = models.CharField(max_length=20, verbose_name='Порт ЕС', help_text='Наприклад: klaipeda, gdansk')
    cost_usd = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Стоимость ($)')

    overlap_key_fields = ('us_port', 'eu_port')

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Морской фрахт'
        verbose_name_plural = 'Морской фрахт'

    def __str__(self):
        return f'{self.us_port} → {self.eu_port}: ${self.cost_usd}'


class EuToUaDeliveryRate(DateRangeModel):
    eu_port = models.CharField(max_length=20, verbose_name='Порт ЕС', help_text='Наприклад: klaipeda, gdansk')
    cost_usd = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Стоимость ($)')

    overlap_key_fields = ('eu_port',)

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Доставка ЕС → Украина'
        verbose_name_plural = 'Доставка ЕС → Украина'

    def __str__(self):
        return f'{self.eu_port} → UA: ${self.cost_usd}'


class RateSource(models.TextChoices):
    """Происхождение курса (2.6): курс `demo` из сида включает демо-баннер."""
    NBU = 'nbu', 'НБУ'
    MANUAL = 'manual', 'Вручну'
    DEMO = 'demo', 'Демо (сид)'


class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=3, verbose_name='Из валюты')
    to_currency = models.CharField(max_length=3, verbose_name='В валюту')
    rate = models.DecimalField(max_digits=14, decimal_places=6, verbose_name='Курс')
    date = models.DateField(verbose_name='Дата')
    source = models.CharField(max_length=10, choices=RateSource.choices, default=RateSource.MANUAL,
                              verbose_name='Джерело')

    class Meta:
        verbose_name = 'Курс валют'
        verbose_name_plural = 'Курсы валют'
        ordering = ['-date']
        unique_together = [('from_currency', 'to_currency', 'date')]

    def __str__(self):
        return f'{self.from_currency}/{self.to_currency} = {self.rate} ({self.date})'


class CustomsExciseRate(DateRangeModel):
    class FuelType(models.TextChoices):
        PETROL = 'petrol', 'Бензин'
        DIESEL = 'diesel', 'Дизель'
        ELECTRIC = 'electric', 'Электро'
        HYBRID = 'hybrid', 'Гибрид (HEV)'
        PHEV = 'phev', 'Гибрид (PHEV, plug-in)'

    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, verbose_name='Тип топлива')
    # Диапазон объёма двигателя для разграничения ставок (напр. бензин ≤3000 vs >3000)
    engine_cc_min = models.IntegerField(default=0, verbose_name='Объём от (см³)')
    engine_cc_max = models.IntegerField(null=True, blank=True, verbose_name='Объём до (см³, пусто=без лимита)')
    # Ставка акциза для ДВС: EUR за каждые 100 см³ × (engine_cc/100) × age_coeff
    # Источник: ставки растаможки Украины, актуальны на янв–июнь 2026; финал подтверждает таможенный брокер
    eur_per_100cc = models.DecimalField(max_digits=8, decimal_places=4, default=0, verbose_name='EUR за каждые 100 см³ (ДВС)')
    # Ставка акциза для EV/PHEV: EUR за кВт·ч ёмкости батареи
    # Источник: ставки растаможки Украины, актуальны на янв–июнь 2026; финал подтверждает таможенный брокер
    ev_excise_eur_per_kwh = models.DecimalField(
        max_digits=8, decimal_places=4, default='1.0000', null=True, blank=True,
        verbose_name='EUR за кВт·ч (EV/PHEV, null=не применяется)',
    )
    duty_rate = models.DecimalField(max_digits=5, decimal_places=4, default='0.1000', verbose_name='Ставка пошлины (10%=0.1000)')
    vat_rate = models.DecimalField(max_digits=5, decimal_places=4, default='0.2000', verbose_name='НДС (20%=0.2000)')

    overlap_key_fields = ('fuel_type', 'engine_cc_min')

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Ставка акциза/пошлины'
        verbose_name_plural = 'Ставки акциза/пошлины'

    def __str__(self):
        cc_range = f'{self.engine_cc_min}–{self.engine_cc_max or "∞"} cc'
        return f'Акциз {self.fuel_type} [{cc_range}]: {self.eur_per_100cc} EUR/100cc ({self.valid_from})'


class PensionFundBracket(DateRangeModel):
    min_value_uah = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Стоимость от (грн)')
    max_value_uah = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                        verbose_name='Стоимость до (грн, пусто=без лимита)')
    # ПРОВЕРИТЬ по действующему законодательству Украины
    rate = models.DecimalField(max_digits=5, decimal_places=4, verbose_name='Ставка пенсионного сбора')

    overlap_key_fields = ('min_value_uah',)

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Брекет пенсионного сбора'
        verbose_name_plural = 'Брекеты пенсионного сбора'
        ordering = ['min_value_uah']

    def __str__(self):
        return f'Пенсионный: {self.min_value_uah}–{self.max_value_uah or "∞"} грн @ {self.rate}'


class PensionBase(models.TextChoices):
    """База для пенсионного сбора (Q5). Какая верна по закону - решает брокер в админке."""
    AUCTION_PRICE = 'auction_price', 'Ціна аукціону × курс'
    CUSTOMS_VALUE = 'customs_value', 'Митна вартість, грн'
    CUSTOMS_VALUE_WITH_TAXES = 'customs_value_with_taxes', 'Митна вартість + мито + акциз + ПДВ'
    TOTAL_BEFORE_PENSION = 'total_before_pension', 'Повна вартість до збору (логістика + податки)'


class CustomsCalcRule(DateRangeModel):
    """Правило растаможки (2.5, Q5): формулы, зависящие от законодательства, - данные, а не код.

    # ПРОВЕРИТЬ по действующему законодательству: значения по умолчанию воспроизводят прежние цифры
    калькулятора (временный вариант); брокер подтверждает или меняет их и ставит «Звірено з брокером».
    """
    pension_bracket_base = models.CharField(
        'База вибору брекету пенсійного збору', max_length=32, choices=PensionBase.choices,
        default=PensionBase.AUCTION_PRICE,
        help_text='За якою сумою обирається ставка (3/4/5%). За замовчуванням - ціна аукціону × курс.',
    )
    pension_rate_base = models.CharField(
        'База нарахування пенсійного збору', max_length=32, choices=PensionBase.choices,
        default=PensionBase.TOTAL_BEFORE_PENSION,
        help_text='Від якої суми рахується збір. За замовчуванням - повна вартість до збору.',
    )
    customs_value_includes_eu_to_ua = models.BooleanField(
        'Митна вартість включає доставку ЄС → Україна', default=False,
        help_text='Вимкнено: митна вартість = аукціон + США + фрахт до порту ЄС.',
    )
    age_coeff_min = models.PositiveSmallIntegerField(
        'Віковий коефіцієнт: мінімум', default=1, help_text='Коефіцієнт не менше цього числа.')
    age_coeff_max = models.PositiveSmallIntegerField(
        'Віковий коефіцієнт: максимум', default=15, help_text='Коефіцієнт не більше цього числа.')
    age_offset_years = models.PositiveSmallIntegerField(
        'Віковий коефіцієнт: зсув, років', default=0,
        help_text='Вік = рік розрахунку − рік випуску − зсув. Частина брокерів рахує зі зсувом 1.',
    )
    confirmed_by_broker = models.BooleanField(
        'Звірено з брокером', default=False,
        help_text='Поки не відмічено, сайт показує «орієнтовний розрахунок». Відмітити після звірки цифр.',
    )
    confirmed_at = models.DateField('Дата звірки', null=True, blank=True)
    note = models.TextField(
        'Примітка', blank=True,
        default='ПЕРЕВІРИТИ за чинним законодавством: значення за замовчуванням повторюють попередні цифри '
                'калькулятора, їх підтверджує митний брокер (питання Q5).',
    )

    overlap_key_fields = ()  # одно правило на дату

    class Meta(DateRangeModel.Meta):
        verbose_name = 'Правило розмитнення'
        verbose_name_plural = 'Правила розмитнення'
        ordering = ['-valid_from']

    def clean(self):
        super().clean()
        if self.age_coeff_min is not None and self.age_coeff_max is not None and self.age_coeff_min > self.age_coeff_max:
            raise ValidationError({'age_coeff_max': 'Максимум не може бути меншим за мінімум.'})

    def __str__(self):
        mark = '✓ звірено' if self.confirmed_by_broker else 'не звірено'
        return f'Правило розмитнення з {self.valid_from} ({mark})'


DEFAULT_RESULT_WARNING = (
    'Розрахунок є орієнтовним. Ставки аукціонних зборів і доставки звіряються з тарифом брокера. '
    'Фінальний розрахунок підтверджує митний брокер.'
)
DEFAULT_DEMO_BANNER_TITLE = 'Тестові тарифи — розрахунок демонстраційний'
DEFAULT_DEMO_BANNER_TEXT = (
    'Частина ставок ще не перевірена власником сайту. Не використовуйте ці цифри для реальних угод.'
)
DEFAULT_ESTIMATE_NOTE = 'Орієнтовний розрахунок.'


class CalculatorSettings(models.Model):
    """Тексты калькулятора (2.6, 02-C1, 09-C6, Q5). Одна запись pk=1, редактируется в админке."""
    result_warning = models.TextField('Попередження під результатом', default=DEFAULT_RESULT_WARNING)
    demo_banner_title = models.CharField('Заголовок демо-банера', max_length=200, default=DEFAULT_DEMO_BANNER_TITLE)
    demo_banner_text = models.TextField('Текст демо-банера', default=DEFAULT_DEMO_BANNER_TEXT)
    estimate_note = models.CharField(
        'Позначка «орієнтовний розрахунок»', max_length=200, default=DEFAULT_ESTIMATE_NOTE,
        help_text='Показується під підсумком, поки є неперевірені ставки або правило не звірене з брокером.',
    )

    class Meta:
        verbose_name = 'Налаштування калькулятора'
        verbose_name_plural = 'Налаштування калькулятора'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Налаштування калькулятора'


class Calculation(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='calculations',
        verbose_name='Пользователь'
    )
    inputs_snapshot = models.JSONField(verbose_name='Снимок входных данных')
    rates_snapshot = models.JSONField(verbose_name='Снимок применённых ставок')
    breakdown = models.JSONField(verbose_name='Детализация расчёта')
    total_usd = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Итого USD')
    total_uah = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Итого UAH')
    is_estimate = models.BooleanField(default=True, verbose_name='Ориентировочный расчёт')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Расчёт стоимости'
        verbose_name_plural = 'Расчёты стоимости'
        ordering = ['-created_at']

    def __str__(self):
        return f'Расчёт #{self.pk} — ${self.total_usd} / {self.total_uah} грн'
