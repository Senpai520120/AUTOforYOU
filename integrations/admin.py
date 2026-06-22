from django.contrib import admin
from .models import VinReport, RegistryReport


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
