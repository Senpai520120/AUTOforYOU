from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import path

from . import registry
from .models import IntegrationHealth, RegistryReport, VinReport


@admin.register(VinReport)
class VinReportAdmin(admin.ModelAdmin):
    list_display = ('vin', 'provider', 'demo', 'created_at')
    list_filter = ('provider', 'demo')
    search_fields = ('vin',)
    readonly_fields = ('vin', 'provider', 'report_data', 'demo', 'created_at')


@admin.register(RegistryReport)
class RegistryReportAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'provider', 'vin', 'plate', 'demo', 'created_at')
    list_filter = ('provider', 'demo')
    search_fields = ('vin', 'plate')
    readonly_fields = ('vin', 'plate', 'provider', 'payload', 'demo', 'created_at')


# ─── Статус интеграций (задача 3.1) ──────────────────────────────────────────

STATUS_PERM = 'integrations.view_integrationhealth'


@admin.register(IntegrationHealth)
class IntegrationHealthAdmin(admin.ModelAdmin):
    """Журнал здоровья провайдеров: только чтение."""
    list_display = ('provider_key', 'last_success_at', 'last_error_at', 'error_count')
    readonly_fields = ('provider_key', 'last_success_at', 'last_error_at', 'last_error', 'error_count')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def status_view(request):
    """/admin/integrations/status/: таблица провайдеров. Значения ключей не выводятся."""
    if not request.user.has_perm(STATUS_PERM):
        raise PermissionDenied
    context = {
        **admin.site.each_context(request),
        'title': 'Статус інтеграцій',
        'statuses': registry.get_statuses(),
    }
    return TemplateResponse(request, 'admin/integrations/status.html', context)


_original_get_urls = admin.site.get_urls
_original_index = admin.site.index


def _get_urls():
    custom = [path('integrations/status/', admin.site.admin_view(status_view), name='integrations_status')]
    return custom + _original_get_urls()


def _index(request, extra_context=None):
    extra = dict(extra_context or {})
    if request.user.has_perm(STATUS_PERM):
        extra['integrations_status_link'] = True
        extra['integrations_attention'] = registry.attention_needed()
    return _original_index(request, extra)


admin.site.get_urls = _get_urls
admin.site.index = _index
admin.site.index_template = 'admin/integrations/index.html'
