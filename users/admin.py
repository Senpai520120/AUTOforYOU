from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser, DealerApplication, TrustedShop
from .services import approve_application, assign_role, reject_application, revoke_role


def ban_users(modeladmin, request, queryset):
    from local_listings.models import LocalListing
    count = 0
    for user in queryset.exclude(is_superuser=True):
        if not user.is_banned:
            user.is_banned = True
            user.is_active = False
            user.save(update_fields=['is_banned', 'is_active'])
            LocalListing.objects.filter(
                owner=user,
                status__in=[LocalListing.Status.ACTIVE, LocalListing.Status.PENDING],
            ).update(status=LocalListing.Status.HIDDEN)
            count += 1
    modeladmin.message_user(request, f'Забанено: {count}.', messages.WARNING)

ban_users.short_description = 'Забанити вибраних користувачів'


def unban_users(modeladmin, request, queryset):
    count = queryset.filter(is_banned=True).update(is_banned=False, is_active=True)
    modeladmin.message_user(request, f'Розбанено: {count}.', messages.SUCCESS)

unban_users.short_description = 'Розбанити вибраних користувачів'


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'role', 'is_verified_dealer', 'is_banned', 'is_email_verified', 'is_staff', 'created_at')
    list_filter = ('role', 'is_verified_dealer', 'is_banned', 'is_email_verified', 'is_staff')
    search_fields = ('email', 'phone')
    ordering = ('-created_at',)
    actions = [ban_users, unban_users, 'assign_broker', 'revoke_broker', 'assign_moderator', 'revoke_moderator']
    # role и is_verified_dealer меняются только actions/сервисом, не формой.
    readonly_fields = ('role', 'is_verified_dealer')

    def _role_action(self, request, queryset, func, role, text, level):
        # Роли назначает только superuser: view-only staff с чужим правом actions не получает.
        if not request.user.is_superuser:
            self.message_user(request, 'Ролі призначає лише суперкористувач.', messages.ERROR)
            return
        n = sum(func(u, role, request.user) for u in queryset)
        self.message_user(request, f'{text}: {n}.', level)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Роль и статус', {'fields': ('role', 'is_verified_dealer', 'is_banned', 'is_email_verified')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Даты', {'fields': ('last_login',)}),
    )
    @admin.action(permissions=['change'], description='Призначити брокером')
    def assign_broker(self, request, queryset):
        self._role_action(request, queryset, assign_role, CustomUser.Role.BROKER, 'Призначено брокером', messages.SUCCESS)

    @admin.action(permissions=['change'], description='Зняти роль брокера')
    def revoke_broker(self, request, queryset):
        self._role_action(request, queryset, revoke_role, CustomUser.Role.BROKER, 'Знято роль брокера', messages.WARNING)

    @admin.action(permissions=['change'], description='Призначити модератором')
    def assign_moderator(self, request, queryset):
        self._role_action(request, queryset, assign_role, CustomUser.Role.MODERATOR, 'Призначено модератором', messages.SUCCESS)

    @admin.action(permissions=['change'], description='Зняти роль модератора')
    def revoke_moderator(self, request, queryset):
        self._role_action(request, queryset, revoke_role, CustomUser.Role.MODERATOR, 'Знято роль модератора', messages.WARNING)

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
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
    # status меняется только actions через сервис: правка в форме обходила бы
    # approve_application (is_verified_dealer, role, письмо) - 01-Q2.
    readonly_fields = ('status', 'agreed_to_processing_at', 'created_at', 'reviewed_at', 'reviewed_by')
    actions = [_approve, _reject]

    fieldsets = (
        (None, {'fields': (
            'user', 'company_name', 'full_name', 'contact_phone', 'documents',
            'agreed_to_processing_at',
        )}),
        ('Рассмотрение', {'fields': ('status', 'reviewed_by', 'review_notes', 'created_at', 'reviewed_at')}),
    )


# --- Вход в админку: тот же счётчик по аккаунту, что и на API (01-S16) ---

from django import forms  # noqa: E402
from django.contrib.admin.forms import AdminAuthenticationForm  # noqa: E402
from rest_framework.throttling import BaseThrottle  # noqa: E402

from . import lockout  # noqa: E402


class LockoutAdminAuthenticationForm(AdminAuthenticationForm):
    def clean(self):
        # cleaned_data: UsernameField уже привёл адрес к NFKC, как при проверке пароля.
        email = (self.cleaned_data.get('username') or '').strip()
        if email:
            retry_after = lockout.is_locked(email)
            if not retry_after:
                _, retry_after = lockout.reserve_attempt(email, BaseThrottle().get_ident(self.request))
            if retry_after:
                minutes = max(1, -(-retry_after // 60))
                raise forms.ValidationError(
                    f'Забагато спроб входу. Спробуйте через {minutes} хв.', code='locked',
                )
        cleaned = super().clean()
        if email:
            lockout.reset(email)
        return cleaned


admin.site.login_form = LockoutAdminAuthenticationForm
