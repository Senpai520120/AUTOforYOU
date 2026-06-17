from django.contrib import admin
from .models import Listing


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ('vehicle', 'seller', 'price', 'currency', 'channel', 'status', 'created_at')
    list_filter = ('status', 'channel', 'currency')
    search_fields = ('vehicle__vin', 'vehicle__make', 'vehicle__model', 'seller__email')
    raw_id_fields = ('vehicle', 'seller', 'calculation')
    date_hierarchy = 'created_at'
