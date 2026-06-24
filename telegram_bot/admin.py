from django.contrib import admin

from .models import TelegramLinkToken


@admin.register(TelegramLinkToken)
class TelegramLinkTokenAdmin(admin.ModelAdmin):
    list_display = ['user', 'token', 'expires_at', 'used', 'created_at']
    list_filter = ['used']
    readonly_fields = ['token', 'created_at']
    search_fields = ['user__email']
