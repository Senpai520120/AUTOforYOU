from django.conf import settings
from django.db import models

from vehicles.models import Vehicle


class Shipment(models.Model):
    class Status(models.TextChoices):
        AT_US_WAREHOUSE = 'at_us_warehouse', 'На складе в США'
        LOADING = 'loading', 'Погрузка'
        IN_OCEAN = 'in_ocean', 'В море'
        AT_EU_PORT = 'at_eu_port', 'В порту ЕС'
        ON_TRUCK_TO_UA = 'on_truck_to_ua', 'Автовоз → Украина'
        CLEARED = 'cleared', 'Растаможен'
        DELIVERED = 'delivered', 'Доставлен'

    VALID_TRANSITIONS = {
        Status.AT_US_WAREHOUSE: [Status.LOADING],
        Status.LOADING: [Status.IN_OCEAN],
        Status.IN_OCEAN: [Status.AT_EU_PORT],
        Status.AT_EU_PORT: [Status.ON_TRUCK_TO_UA],
        Status.ON_TRUCK_TO_UA: [Status.CLEARED],
        Status.CLEARED: [Status.DELIVERED],
        Status.DELIVERED: [],
    }

    class EuPort(models.TextChoices):
        KLAIPEDA = 'klaipeda', 'Клайпеда'
        GDANSK = 'gdansk', 'Гданьск'

    container_no = models.CharField(max_length=20, unique=True, verbose_name='Номер контейнера')
    vessel = models.CharField(max_length=100, blank=True, verbose_name='Судно')
    us_warehouse = models.CharField(max_length=100, blank=True, verbose_name='Склад США')
    departure_port_us = models.CharField(max_length=50, blank=True, verbose_name='Порт отправки (США)')
    arrival_port_eu = models.CharField(
        max_length=20, choices=EuPort.choices, default=EuPort.KLAIPEDA,
        verbose_name='Порт прибытия (ЕС)'
    )
    eta = models.DateField(null=True, blank=True, verbose_name='Ожидаемая дата прибытия')
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.AT_US_WAREHOUSE, verbose_name='Статус'
    )
    vehicles = models.ManyToManyField(
        Vehicle, blank=True, related_name='shipments', verbose_name='Автомобили'
    )
    watchers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name='watched_shipments', verbose_name='Отслеживают'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Контейнер/Шипмент'
        verbose_name_plural = 'Контейнеры/Шипменты'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.container_no} [{self.get_status_display()}]'

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])

    def advance_status(self, new_status: str, note: str = '', photo=None) -> 'TrackingEvent':
        if not self.can_transition_to(new_status):
            raise ValueError(
                f'Переход {self.status} → {new_status} недопустим. '
                f'Возможные: {self.VALID_TRANSITIONS.get(self.status, [])}'
            )
        self.status = new_status
        self.save(update_fields=['status', 'updated_at'])
        return TrackingEvent.objects.create(
            shipment=self, status=new_status, note=note, photo=photo or None
        )


class TrackingEvent(models.Model):
    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE,
        related_name='events', verbose_name='Контейнер'
    )
    status = models.CharField(
        max_length=20, choices=Shipment.Status.choices, verbose_name='Статус'
    )
    note = models.TextField(blank=True, verbose_name='Комментарий')
    photo = models.ImageField(upload_to='tracking_photos/', null=True, blank=True, verbose_name='Фото')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Событие трекинга'
        verbose_name_plural = 'События трекинга'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.shipment.container_no} → {self.get_status_display()} ({self.created_at:%Y-%m-%d})'
