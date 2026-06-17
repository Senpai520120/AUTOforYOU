from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, TrustedShop


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
