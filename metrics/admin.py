from django.contrib import admin

from .models import DailyMetric


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    """Только просмотр (8.7); видят admin-роль и superuser, модератор и брокер - нет."""
    list_display = ('date', 'key', 'value')
    list_filter = ('key', 'date')
    date_hierarchy = 'date'

    def _allowed(self, request):
        return bool(request.user.is_active and request.user.is_admin_role)

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
