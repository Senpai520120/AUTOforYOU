from django.contrib import admin

from .models import FaqItem, ImportStep


class AdminOnlyMixin:
    """Тільки superuser або role=admin; модератор і брокер доступу не мають."""

    def _allowed(self, request):
        u = request.user
        return bool(u.is_active and u.is_staff and (u.is_superuser or getattr(u, 'is_admin_role', False)))

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return self._allowed(request)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request)

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request)


@admin.register(ImportStep)
class ImportStepAdmin(AdminOnlyMixin, admin.ModelAdmin):
    list_display = ('title', 'duration', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('title', 'description', 'duration')


@admin.register(FaqItem)
class FaqItemAdmin(AdminOnlyMixin, admin.ModelAdmin):
    list_display = ('question', 'order', 'is_active', 'show_on_calculator')
    list_editable = ('order', 'is_active', 'show_on_calculator')
    search_fields = ('question', 'answer')
