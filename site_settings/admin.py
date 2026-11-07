from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Власник ПДн', {
            'fields': ('owner_legal_form', 'owner_legal_name', 'owner_code', 'owner_address'),
            'description': 'Реквізити з виписки ЄДР. Показуються в політиці, оферті та підвалі.',
        }),
        ('Контакти', {
            'fields': ('support_email', 'privacy_email', 'phone', 'manager_contact', 'telegram_channel_url'),
        }),
        ('Партнер', {
            'fields': ('partner_name', 'partner_legal_name'),
            'description': 'Заповнити після підписання договору з партнером.',
        }),
        ('Юридичні документи', {
            'fields': ('legal_docs_approved', 'legal_docs_updated_at', 'legal_docs_version',
                       'legal_docs_reconsent_required', 'data_retention_years',
                       'log_retention_days', 'account_deletion_grace_days'),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        obj = SiteSettings.load()
        return redirect(reverse('admin:site_settings_sitesettings_change', args=[obj.pk]))
