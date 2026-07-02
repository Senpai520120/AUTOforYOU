from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'type', 'title', 'is_read', 'created_at']
    list_filter = ['type', 'is_read', 'created_at']
    search_fields = ['user__email', 'title', 'text']
    readonly_fields = ['created_at']
    actions = ['mark_all_read']

    @admin.action(description='Позначити прочитаними')
    def mark_all_read(self, request, queryset):
        queryset.update(is_read=True)
