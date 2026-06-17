from django.contrib import admin
from .models import VinReport


@admin.register(VinReport)
class VinReportAdmin(admin.ModelAdmin):
    list_display = ('vin', 'provider', 'demo', 'created_at')
    list_filter = ('provider', 'demo')
    search_fields = ('vin',)
    readonly_fields = ('vin', 'provider', 'report_data', 'demo', 'created_at')
