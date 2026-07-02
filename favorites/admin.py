from django.contrib import admin
from .models import Favorite


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'local_listing', 'imported_listing', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__email']
    readonly_fields = ['created_at']
