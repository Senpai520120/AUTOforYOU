from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, DealerApplication, TrustedShop
from .services import approve_application, reject_application


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'role', 'is_verified_dealer', 'is_staff', 'created_at')
    list_filter = ('role', 'is_verified_dealer', 'is_staff')
    search_fields = ('email', 'phone')
    ordering = ('-created_at',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Роль и статус', {'fields': ('role', 'is_verified_dealer')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Даты', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role'),
        }),
    )


@admin.register(TrustedShop)
class TrustedShopAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'rating', 'owner', 'created_at')
    list_filter = ('type', 'rating')
    search_fields = ('name', 'owner__email')
    raw_id_fields = ('owner',)


def _approve(modeladmin, request, queryset):
    count = 0
    for app in queryset.filter(status=DealerApplication.Status.PENDING):
        approve_application(app, request.user)
        count += 1
    modeladmin.message_user(request, f'Одобрено заявок: {count}.', messages.SUCCESS)


_approve.short_description = 'Одобрить выбранные заявки'


def _reject(modeladmin, request, queryset):
    count = 0
    for app in queryset.filter(status=DealerApplication.Status.PENDING):
        reject_application(app, request.user, notes='Отклонено администратором.')
        count += 1
    modeladmin.message_user(request, f'Отклонено заявок: {count}.', messages.WARNING)


_reject.short_description = 'Отклонить выбранные заявки'


@admin.register(DealerApplication)
class DealerApplicationAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'status', 'reviewed_by', 'created_at', 'reviewed_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'company_name', 'full_name')
    raw_id_fields = ('user', 'reviewed_by')
    readonly_fields = ('created_at', 'reviewed_at', 'reviewed_by')
    actions = [_approve, _reject]

    fieldsets = (
        (None, {'fields': ('user', 'company_name', 'full_name', 'contact_phone', 'documents')}),
        ('Рассмотрение', {'fields': ('status', 'reviewed_by', 'review_notes', 'created_at', 'reviewed_at')}),
    )
