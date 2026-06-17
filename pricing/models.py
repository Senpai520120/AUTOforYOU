from django.conf import settings
from django.db import models


class DateRangeModel(models.Model):
    valid_from = models.DateField(verbose_name='Действует с')
    valid_to = models.DateField(null=True, blank=True, verbose_name='Действует по')

    class Meta:
        abstract = True


class AuctionFeeTier(DateRangeModel):
    class Auction(models.TextChoices):
        COPART = 'copart', 'Copart'
        IAAI = 'iaai', 'IAAI'

    auction = models.CharField(max_length=10, choices=Auction.choices, verbose_name='Аукцион')
    min_price_usd = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена от ($)')
    max_price_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Цена до ($, пусто=без лимита)')
    fee_fixed_usd = models.DecimalField(max_digits=8, decimal_places=2, default=0, verbose_name='Фиксированный сбор ($)')
    fee_pct = models.DecimalField(max_digits=5, decimal_places=4, default=0, verbose_name='% от цены (напр. 0.1000 = 10%)')

    class Meta:
        verbose_name = 'Тариф аукционного сбора'
        verbose_name_plural = 'Тарифы аукционных сборов'
        ordering = ['auction', 'min_price_usd']

    def __str__(self):
        return f'{self.auction} ${self.min_price_usd}–{self.max_price_usd or "∞"} ({self.valid_from})'


class UsLandRoute(DateRangeModel):
    auction_location = models.CharField(max_length=100, verbose_name='Локация аукциона')
    us_port = models.CharField(max_length=50, verbose_name='Порт США')
    cost_usd = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Стоимость ($)')

    class Meta:
        verbose_name = 'Сухопутная логистика США'
        verbose_name_plural = 'Сухопутная логистика США'

    def __str__(self):
        return f'{self.auction_location} → {self.us_port}: ${self.cost_usd}'


class OceanFreightRate(DateRangeModel):
    class EuPort(models.TextChoices):
        KLAIPEDA = 'klaipeda', 'Клайпеда'
        GDANSK = 'gdansk', 'Гданьск'

    us_port = models.CharField(max_length=50, verbose_name='Порт США')
    eu_port = models.CharField(max_length=20, choices=EuPort.choices, verbose_name='Порт ЕС')
    cost_usd = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Стоимость ($)')

    class Meta:
        verbose_name = 'Морской фрахт'
        verbose_name_plural = 'Морской фрахт'

    def __str__(self):
        return f'{self.us_port} → {self.eu_port}: ${self.cost_usd}'


class EuToUaDeliveryRate(DateRangeModel):
    class EuPort(models.TextChoices):
        KLAIPEDA = 'klaipeda', 'Клайпеда'
        GDANSK = 'gdansk', 'Гданьск'

    eu_port = models.CharField(max_length=20, choices=EuPort.choices, verbose_name='Порт ЕС')
    cost_usd = models.DecimalField(max_digits=8, decimal_places=2, verbose_name='Стоимость ($)')

    class Meta:
        verbose_name = 'Доставка ЕС → Украина'
        verbose_name_plural = 'Доставка ЕС → Украина'

    def __str__(self):
        return f'{self.eu_port} → UA: ${self.cost_usd}'


class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=3, verbose_name='Из валюты')
    to_currency = models.CharField(max_length=3, verbose_name='В валюту')
    rate = models.DecimalField(max_digits=14, decimal_places=6, verbose_name='Курс')
    date = models.DateField(verbose_name='Дата')

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
        HYBRID = 'hybrid', 'Гибрид'

    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, verbose_name='Тип топлива')
    # ПРОВЕРИТЬ по действующему законодательству Украины
    eur_per_100cc = models.DecimalField(max_digits=8, decimal_places=4, verbose_name='EUR за каждые 100 см³')
    # Коэффициенты возраста — ПРОВЕРИТЬ по действующему законодательству
    age_0_1_coeff = models.DecimalField(max_digits=6, decimal_places=4, default=1, verbose_name='Коэфф. 0–1 год')
    age_1_3_coeff = models.DecimalField(max_digits=6, decimal_places=4, default=1, verbose_name='Коэфф. 1–3 года')
    age_3_5_coeff = models.DecimalField(max_digits=6, decimal_places=4, default=1, verbose_name='Коэфф. 3–5 лет')
    age_5_7_coeff = models.DecimalField(max_digits=6, decimal_places=4, default=1, verbose_name='Коэфф. 5–7 лет')
    age_7_plus_coeff = models.DecimalField(max_digits=6, decimal_places=4, default=1, verbose_name='Коэфф. 7+ лет')
    duty_rate = models.DecimalField(max_digits=5, decimal_places=4, default='0.1000', verbose_name='Ставка пошлины (10%=0.1000)')
    vat_rate = models.DecimalField(max_digits=5, decimal_places=4, default='0.2000', verbose_name='НДС (20%=0.2000)')

    class Meta:
        verbose_name = 'Ставка акциза/пошлины'
        verbose_name_plural = 'Ставки акциза/пошлины'

    def __str__(self):
        return f'Акциз {self.fuel_type}: {self.eur_per_100cc} EUR/100cc ({self.valid_from})'


class PensionFundBracket(DateRangeModel):
    min_value_uah = models.DecimalField(max_digits=14, decimal_places=2, verbose_name='Стоимость от (грн)')
    max_value_uah = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
                                        verbose_name='Стоимость до (грн, пусто=без лимита)')
    # ПРОВЕРИТЬ по действующему законодательству Украины
    rate = models.DecimalField(max_digits=5, decimal_places=4, verbose_name='Ставка пенсионного сбора')

    class Meta:
        verbose_name = 'Брекет пенсионного сбора'
        verbose_name_plural = 'Брекеты пенсионного сбора'
        ordering = ['min_value_uah']

    def __str__(self):
        return f'Пенсионный: {self.min_value_uah}–{self.max_value_uah or "∞"} грн @ {self.rate}'


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
