from django.contrib import admin
from .models import Vehicle, VehicleImage


class VehicleImageInline(admin.TabularInline):
    model = VehicleImage
    extra = 2
    fields = ('image', 'is_primary')


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'year', 'vin', 'fuel_type', 'engine_cc', 'source_auction')
    list_filter = ('fuel_type', 'source_auction', 'year')
    search_fields = ('vin', 'make', 'model', 'lot_number')
    inlines = [VehicleImageInline]
