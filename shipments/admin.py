import posixpath

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import Shipment, TrackingEvent


class _ProtectedPhotoLink:
    """Значение для шаблона ClearableFileInput: ссылка на защищённый URL вместо storage.url."""

    def __init__(self, fieldfile):
        self.url = fieldfile.instance.get_photo_url()
        self._label = posixpath.basename(fieldfile.name)

    def __str__(self):
        return self._label


class ProtectedPhotoInput(forms.ClearableFileInput):
    # Фото трекинга лежат в приватном хранилище: ссылка ведёт на /api/v1/shipments/…/photo/.
    def format_value(self, value):
        if self.is_initial(value) and getattr(value, 'instance', None) is not None:
            return _ProtectedPhotoLink(value)
        return super().format_value(value)


class TrackingEventForm(forms.ModelForm):
    class Meta:
        model = TrackingEvent
        fields = '__all__'
        widgets = {'photo': ProtectedPhotoInput}


class TrackingEventInline(admin.TabularInline):
    model = TrackingEvent
    form = TrackingEventForm
    extra = 1
    fields = ('status', 'note', 'photo', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('container_no', 'vessel', 'status', 'arrival_port_eu', 'eta', 'vehicle_count')
    list_filter = ('status', 'arrival_port_eu')
    search_fields = ('container_no', 'vessel')
    filter_horizontal = ('vehicles', 'watchers')
    inlines = [TrackingEventInline]

    def vehicle_count(self, obj):
        return obj.vehicles.count()
    vehicle_count.short_description = 'Авто'

    def save_model(self, request, obj, form, change):
        old_status = Shipment.objects.filter(pk=obj.pk).values_list('status', flat=True).first()
        super().save_model(request, obj, form, change)
        if change and old_status and old_status != obj.status:
            TrackingEvent.objects.create(
                shipment=obj, status=obj.status,
                note=f'Статус изменён через Admin ({old_status} → {obj.status})'
            )


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    form = TrackingEventForm
    list_display = ('shipment', 'status', 'note_short', 'photo_thumb', 'created_at')
    list_filter = ('status',)
    date_hierarchy = 'created_at'

    def note_short(self, obj):
        return obj.note[:60] + '...' if len(obj.note) > 60 else obj.note
    note_short.short_description = 'Комментарий'

    def photo_thumb(self, obj):
        if obj.photo:
            return format_html('<img src="{}" height="40"/>', obj.get_photo_url())
        return '—'
    photo_thumb.short_description = 'Фото'
