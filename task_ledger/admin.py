from django.contrib import admin

from .models import FailedTask


@admin.register(FailedTask)
class FailedTaskAdmin(admin.ModelAdmin):
    """Только просмотр, только admin-роль. Действие «повторить» - задача 9.35."""
    list_display = ('failed_at', 'task_name', 'exception_class', 'retries', 'queue')
    list_filter = ('task_name', 'failed_at')
    search_fields = ('task_name',)
    date_hierarchy = 'failed_at'
    readonly_fields = ('task_name', 'task_id', 'failed_at', 'retries', 'exception_class', 'error', 'args',
                       'kwargs', 'queue')
    actions = None

    def _is_admin(self, request):
        return bool(request.user.is_active and request.user.is_admin_role)

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
