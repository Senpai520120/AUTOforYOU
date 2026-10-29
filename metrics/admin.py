from django.contrib import admin

from .models import DailyMetric


@admin.register(DailyMetric)
class DailyMetricAdmin(admin.ModelAdmin):
    """Только просмотр, только admin-роль и superuser. Дашборд - задача 9.32."""
    list_display = ('date', 'key', 'value')
    list_filter = ('key', 'date')
    date_hierarchy = 'date'
    actions = None

    def _is_admin(self, request):
        return bool(request.user.is_active and (request.user.is_superuser or request.user.is_admin_role))

    def has_module_permission(self, request):
        return self._is_admin(request)

    def has_view_permission(self, request, obj=None):
        return self._is_admin(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
