from django.db import models


class Vehicle(models.Model):
    class FuelType(models.TextChoices):
        PETROL = 'petrol', 'Бензин'
        DIESEL = 'diesel', 'Дизель'
        ELECTRIC = 'electric', 'Электро'
        HYBRID = 'hybrid', 'Гибрид'

    class SourceAuction(models.TextChoices):
        COPART = 'copart', 'Copart'
        IAAI = 'iaai', 'IAAI'
        OTHER = 'other', 'Другой'

    vin = models.CharField(max_length=17, unique=True, verbose_name='VIN')
    make = models.CharField(max_length=50, verbose_name='Марка')
    model = models.CharField(max_length=50, verbose_name='Модель')
    year = models.PositiveSmallIntegerField(verbose_name='Год выпуска')
    engine_cc = models.PositiveIntegerField(verbose_name='Объём двигателя (см³)')
    fuel_type = models.CharField(max_length=10, choices=FuelType.choices, default=FuelType.PETROL, verbose_name='Тип топлива')
    mileage_km = models.PositiveIntegerField(default=0, verbose_name='Пробег (км)')
    damage_type = models.CharField(max_length=100, blank=True, verbose_name='Тип повреждения')
    source_auction = models.CharField(max_length=10, choices=SourceAuction.choices, default=SourceAuction.COPART, verbose_name='Аукцион')
    lot_number = models.CharField(max_length=50, blank=True, verbose_name='Номер лота')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Автомобиль'
        verbose_name_plural = 'Автомобили'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.year} {self.make} {self.model} ({self.vin})'


class VehicleImage(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='vehicle_photos/')
    is_primary = models.BooleanField(default=False, verbose_name='Главное фото')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Фото автомобиля'
        verbose_name_plural = 'Фото автомобилей'
