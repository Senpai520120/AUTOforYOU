from django.contrib import admin
from .models import Region, City, LocalListing, LocalListingImage


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


class CityInline(admin.TabularInline):
    model = City
    extra = 1
    prepopulated_fields = {'slug': ('name',)}


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'region', 'slug']
    list_filter = ['region']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'region__name']


class LocalListingImageInline(admin.TabularInline):
    model = LocalListingImage
    extra = 1
    readonly_fields = ['created_at']


@admin.register(LocalListing)
class LocalListingAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'owner', 'status', 'region', 'city', 'seller_type', 'created_at']
    list_filter = ['status', 'fuel_type', 'body_type', 'transmission', 'seller_type', 'region']
    search_fields = ['make', 'model', 'owner__email', 'contact_phone']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [LocalListingImageInline]
    raw_id_fields = ['owner', 'region', 'city']
