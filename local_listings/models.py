from django.conf import settings
from django.db import models


class Region(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='Область')
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name = 'Область'
        verbose_name_plural = 'Області'
        ordering = ['name']

    def __str__(self):
        return self.name


class City(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='cities', verbose_name='Область')
    name = models.CharField(max_length=100, verbose_name='Місто')
    slug = models.SlugField(max_length=100)

    class Meta:
        verbose_name = 'Місто'
        verbose_name_plural = 'Міста'
        ordering = ['name']
        unique_together = [('region', 'slug')]

    def __str__(self):
        return f'{self.name} ({self.region.name})'


class LocalListing(models.Model):
    class FuelType(models.TextChoices):
        PETROL = 'petrol', 'Бензин'
        DIESEL = 'diesel', 'Дизель'
        ELECTRIC = 'electric', 'Електро'
        HYBRID = 'hybrid', 'Гібрид'
        GAS = 'gas', 'Газ'

    class Transmission(models.TextChoices):
        AUTO = 'auto', 'Автомат'
        MANUAL = 'manual', 'Механіка'
        CVT = 'cvt', 'Варіатор'
        ROBOT = 'robot', 'Робот'

    class BodyType(models.TextChoices):
        SEDAN = 'sedan', 'Седан'
        SUV = 'suv', 'Позашляховик'
        HATCHBACK = 'hatchback', 'Хетчбек'
        WAGON = 'wagon', 'Універсал'
        COUPE = 'coupe', 'Купе'
        MINIVAN = 'minivan', 'Мінівен'
        PICKUP = 'pickup', 'Пікап'
        CONVERTIBLE = 'convertible', 'Кабріолет'
        OTHER = 'other', 'Інше'

    class Condition(models.TextChoices):
        NEW = 'new', 'Новий'
        USED = 'used', 'Вживаний'
        DAMAGED = 'damaged', 'Пошкоджений'

    class Currency(models.TextChoices):
        UAH = 'UAH', 'UAH'
        USD = 'USD', 'USD'
        EUR = 'EUR', 'EUR'

    class PriceType(models.TextChoices):
        FIXED = 'fixed', 'Фіксована'
        NEGOTIABLE = 'negotiable', 'Торг'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Чернетка'
        ACTIVE = 'active', 'Активне'
        # TODO: C2C-промт 2 — реалізувати модерацію (pending → active/rejected)
        PENDING = 'pending', 'На модерації'
        REJECTED = 'rejected', 'Відхилено'
        # TODO: C2C-промт 5 — термін дії оголошення, автоматичне переведення в expired
        EXPIRED = 'expired', 'Закінчилося'
        SOLD = 'sold', 'Продано'
        HIDDEN = 'hidden', 'Приховане'

    class SellerType(models.TextChoices):
        PRIVATE = 'private', 'Приватна особа'
        # TODO: верифікація дилерів буде в C2C-промтах 3/4
        DEALER = 'dealer', 'Дилер'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='local_listings',
        verbose_name='Власник',
    )
    make = models.CharField(max_length=100, verbose_name='Марка')
    model = models.CharField(max_length=100, verbose_name='Модель')
    year = models.PositiveSmallIntegerField(verbose_name='Рік')
    mileage_km = models.PositiveIntegerField(verbose_name='Пробіг, км')
    engine_cc = models.PositiveIntegerField(null=True, blank=True, verbose_name="Об'єм двигуна, куб.см")
    fuel_type = models.CharField(max_length=20, choices=FuelType.choices, verbose_name='Тип палива')
    transmission = models.CharField(max_length=20, choices=Transmission.choices, verbose_name='КПП')
    body_type = models.CharField(max_length=20, choices=BodyType.choices, verbose_name='Тип кузова')
    condition = models.CharField(
        max_length=20, choices=Condition.choices, default=Condition.USED, verbose_name='Стан'
    )
    price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Ціна')
    currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.UAH, verbose_name='Валюта'
    )
    price_type = models.CharField(
        max_length=20, choices=PriceType.choices, default=PriceType.FIXED, verbose_name='Тип ціни'
    )
    region = models.ForeignKey(Region, on_delete=models.PROTECT, verbose_name='Область')
    city = models.ForeignKey(City, on_delete=models.PROTECT, verbose_name='Місто')
    description = models.TextField(blank=True, verbose_name='Опис')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name='Статус'
    )
    seller_type = models.CharField(
        max_length=20, choices=SellerType.choices, default=SellerType.PRIVATE, verbose_name='Тип продавця'
    )
    # Телефон — не повертається в публічному списку (захист контактів — C2C-промт 6)
    contact_phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Місцеве оголошення'
        verbose_name_plural = 'Місцеві оголошення'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='ll_status_idx'),
            models.Index(fields=['make'], name='ll_make_idx'),
            models.Index(fields=['year'], name='ll_year_idx'),
            models.Index(fields=['price'], name='ll_price_idx'),
            models.Index(fields=['region'], name='ll_region_idx'),
            models.Index(fields=['fuel_type'], name='ll_fuel_idx'),
        ]

    def __str__(self):
        return f'{self.make} {self.model} {self.year} — {self.price} {self.currency} [{self.status}]'


class LocalListingImage(models.Model):
    listing = models.ForeignKey(
        LocalListing, on_delete=models.CASCADE, related_name='images', verbose_name='Оголошення'
    )
    image = models.ImageField(upload_to='local_listings/', null=True, blank=True, verbose_name='Фото')
    source_url = models.CharField(max_length=500, blank=True, verbose_name='URL фото')
    is_primary = models.BooleanField(default=False, verbose_name='Головне фото')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Фото оголошення'
        verbose_name_plural = 'Фото оголошень'
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f'Фото #{self.pk} для {self.listing}'
