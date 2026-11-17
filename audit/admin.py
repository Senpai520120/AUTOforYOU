from django.contrib import admin

from .models import AuditLog


def can_read_audit(request) -> bool:
    # Только admin-роль (с is_staff) или superuser (C7.2). Модератор журнал не видит, даже свои записи.
    user = request.user
    return bool(user.is_active and user.is_staff and getattr(user, 'is_admin_role', False))


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'target_repr', 'actor', 'actor_role_snapshot', 'short_reason')
    list_filter = ('action', 'actor_role_snapshot', 'created_at')
    search_fields = ('target_repr',)
    date_hierarchy = 'created_at'
    list_select_related = ('actor',)

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    @admin.display(description='Причина')
    def short_reason(self, obj):
        return (obj.reason[:60] + '…') if len(obj.reason) > 60 else obj.reason

    def has_module_permission(self, request):
        return can_read_audit(request)

    def has_view_permission(self, request, obj=None):
        return can_read_audit(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
