from django.contrib import admin

from .models import SavedSearch


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'name', 'notify', 'last_notified_at', 'created_at']
    list_filter = ['notify', 'created_at']
    search_fields = ['user__email', 'name']
    readonly_fields = ['created_at', 'last_notified_at']
