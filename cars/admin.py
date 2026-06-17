from django.contrib import admin
from .models import Car, CarImage

class CarImageInline(admin.TabularInline):
    model = CarImage
    extra = 3

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ('title', 'year', 'status', 'total_price', 'owner')
    list_filter = ('status', 'year')
    search_fields = ('title', 'vin', 'lot_number')
    inlines = [CarImageInline]
