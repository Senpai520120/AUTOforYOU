from django.conf import settings
from django.db import models


class Car(models.Model):
    STATUS_CHOICES = [
        ('IN_USA', 'На аукционе в США'),
        ('IN_TRANSIT', 'Плывет в Украину'),
        ('IN_UKRAINE', 'В Украине / На ремонте / Готов'),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='Продавец (Перекуп)')
    title = models.CharField(max_length=100, verbose_name='Марка и модель авто')
    vin = models.CharField(max_length=17, unique=True, verbose_name='VIN код')
    year = models.PositiveIntegerField(verbose_name='Год выпуска')
    price_in_usa = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена на аукционе ($)')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена под ключ в Украине ($)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_USA', verbose_name='Статус доставки')
    lot_number = models.CharField(max_length=50, blank=True, null=True, verbose_name='Номер лота Copart/IAAI')
    description = models.TextField(blank=True, null=True, verbose_name='Описание ремонта или состояния')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата добавления')

    def __str__(self):
        return f'{self.title} ({self.year}) — {self.vin}'


class CarImage(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='cars_photos/')
