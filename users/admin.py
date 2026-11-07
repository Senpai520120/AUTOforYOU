from django import forms
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import ConsentRecord, CustomUser, DealerApplication, TrustedShop, UserBlock
from .services import (
    BLOCK_REASON_REQUIRED,
    UNBLOCK_REASON_REQUIRED,
    AccountDeletionError,
    anonymize_user,
    approve_application,
    assign_role,
    block_user,
    reject_application,
    revoke_all_sessions,
    revoke_role,
    unblock_user,
)


class ReasonForm(forms.Form):
    reason = forms.CharField(
        label='Причина', required=False, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 3, 'cols': 60}),
    )


def ask_reason(modeladmin, request, queryset, *, title, prompt, required_error):
    """Промежуточная страница причины для действия админки (1.13).

    Возвращает (reason, None), когда причина введена, иначе (None, TemplateResponse с формой).
    Пустая причина - форма снова с ошибкой, действие ничего не делает.
    """
    error = ''
    if 'apply' in request.POST:
        form = ReasonForm(request.POST)
        if form.is_valid() and form.cleaned_data['reason'].strip():
            return form.cleaned_data['reason'].strip(), None
        error = required_error
    else:
        form = ReasonForm()
    context = {
        **modeladmin.admin_site.each_context(request),
        'title': title,
        'prompt': prompt,
        'form': form,
        'error': error,
        'objects': list(queryset),
        'action': request.POST.get('action', ''),
        'opts': modeladmin.model._meta,
        'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
    }
    return None, TemplateResponse(request, 'admin/action_reason.html', context)


@admin.action(permissions=['change'], description='Заблокувати вибраних користувачів (з причиною)')
def ban_users(modeladmin, request, queryset):
    reason, response = ask_reason(
        modeladmin, request, queryset, title='Блокування користувачів',
        prompt='Вкажіть причину блокування', required_error=BLOCK_REASON_REQUIRED,
    )
    if response is not None:
        return response
    done = skipped = 0
    for user in queryset:
        try:
            done += bool(block_user(user, request.user, reason, request=request))
        except ValidationError:
            skipped += 1  # staff, суперкористувач або сам себе
    modeladmin.message_user(
        request, f'Заблоковано: {done}. Пропущено (співробітники або ви самі): {skipped}.', messages.WARNING,
    )


@admin.action(permissions=['change'], description='Розблокувати вибраних користувачів (з причиною)')
def unban_users(modeladmin, request, queryset):
    reason, response = ask_reason(
        modeladmin, request, queryset, title='Розблокування користувачів',
        prompt='Вкажіть причину розблокування', required_error=UNBLOCK_REASON_REQUIRED,
    )
    if response is not None:
        return response
    count = sum(unblock_user(user, request.user, reason, request=request) for user in queryset)
    modeladmin.message_user(request, f'Розблоковано: {count}.', messages.SUCCESS)


class DeletedFilter(admin.SimpleListFilter):
    title = 'видалений'
    parameter_name = 'deleted'

    def lookups(self, request, model_admin):
        return (('yes', 'Видалений (знеособлено)'), ('scheduled', 'Видалення заплановано'), ('no', 'Ні'))

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(deleted_at__isnull=False)
        if self.value() == 'scheduled':
            return queryset.filter(deletion_scheduled_at__isnull=False, deleted_at__isnull=True)
        if self.value() == 'no':
            return queryset.filter(deleted_at__isnull=True)
        return queryset


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'role', 'is_verified_dealer', 'is_banned', 'is_email_verified', 'is_staff', 'created_at')
    list_filter = ('role', 'is_verified_dealer', 'is_banned', 'is_email_verified', 'is_staff', DeletedFilter)
    search_fields = ('email', 'phone')
    ordering = ('-created_at',)
    actions = [
        ban_users, unban_users, 'assign_broker', 'revoke_broker', 'assign_moderator', 'revoke_moderator',
        'anonymize',
    ]
    # role и is_verified_dealer меняются только actions/сервисом, не формой.
    # is_banned - только через actions/block_user (UserBlock, журнал, отзыв сессий, скрытие объявлений).
    readonly_fields = ('role', 'is_verified_dealer', 'is_banned', 'block_history', 'deletion_scheduled_at', 'deleted_at')

    PRIVILEGE_FIELDS = ('is_superuser', 'is_staff', 'groups', 'user_permissions')
    ATTRIBUTION_FIELDS = ('first_touch_utm', 'first_touch_referrer', 'first_touch_entry_url')

    def _can_see_attribution(self, request):
        user = request.user
        # Только право: доступ можно отозвать и у admin-роли (группа «Адміністратори» получает его в миграции).
        return bool(user.is_active and user.has_perm('users.view_attribution'))

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if obj is not None and self._can_see_attribution(request):
            # Источник визита (2.14): только чтение и только admin; модератор и брокер его не видят.
            fieldsets = (*fieldsets, ('Джерело візиту', {'fields': self.ATTRIBUTION_FIELDS, 'classes': ('collapse',)}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            # D6 (1.17): права правит только superuser; иначе staff с change_customuser повышает себя.
            fields += [f for f in self.PRIVILEGE_FIELDS if f not in fields]
        if self._can_see_attribution(request):
            fields += [f for f in self.ATTRIBUTION_FIELDS if f not in fields]
        return fields

    def has_change_permission(self, request, obj=None):
        # Сотрудников (и superuser) правит только superuser: иначе staff с change_customuser меняет
        # им пароль/email и захватывает аккаунт. user_change_password проверяет этот метод.
        if obj is not None and obj.is_staff and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj)

    @admin.display(description='Історія блокувань')
    def block_history(self, obj):
        # Только чтение (1.13): причина видна лишь staff в админке. Не inline - формсет ломал бы POST формы.
        blocks = list(UserBlock.objects.filter(user=obj).select_related('blocked_by', 'unblocked_by')) if obj else []
        if not blocks:
            return '—'
        return format_html_join(
            '', '<p>{} · {} · «{}»{}</p>',
            (
                (
                    timezone.localtime(b.blocked_at).strftime('%Y-%m-%d %H:%M'),
                    b.blocked_by or 'система',
                    b.reason,
                    format_html(' — розблоковано {} ({}): «{}»',
                                timezone.localtime(b.unblocked_at).strftime('%Y-%m-%d %H:%M'),
                                b.unblocked_by or 'система', b.unblock_reason) if b.unblocked_at else '',
                )
                for b in blocks
            ),
        )

    def has_delete_permission(self, request, obj=None):
        # Удаление каскадом стёрло бы сделки, переписку и отзывы второй стороны (06-S11):
        # вместо него - действие «Анонімізувати» (тот же сервис, что у API).
        return False

    @admin.action(permissions=['change'], description='Анонімізувати (видалити акаунт)')
    def anonymize(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, 'Анонімізує лише суперкористувач.', messages.ERROR)
            return
        done = skipped = 0
        for user in queryset.exclude(pk=request.user.pk):
            try:
                done += anonymize_user(user)
            except AccountDeletionError:
                skipped += 1
        self.message_user(request, f'Анонімізовано: {done}. Пропущено (суперкористувачі): {skipped}.', messages.WARNING)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Отключение аккаунта вручную (is_active) тоже обрывает все сессии (01-S12).
        if change and 'is_active' in form.changed_data and not obj.is_active:
            revoke_all_sessions(obj)

    def _role_action(self, request, queryset, func, role, text, level):
        # Роли назначает только superuser: view-only staff с чужим правом actions не получает.
        if not request.user.is_superuser:
            self.message_user(request, 'Ролі призначає лише суперкористувач.', messages.ERROR)
            return
        n = sum(func(u, role, request.user, request=request) for u in queryset)
        self.message_user(request, f'{text}: {n}.', level)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Роль и статус', {'fields': ('role', 'is_verified_dealer', 'is_banned', 'block_history', 'is_email_verified')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Даты', {'fields': ('last_login', 'deletion_scheduled_at', 'deleted_at')}),
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


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    """Журнал згод: лише читання, лише admin/superuser (Q10). Moderator/broker не бачать."""
    list_display = ('given_at', 'document', 'doc_version', 'method', 'user', 'lead', 'partner_name')
    list_filter = ('document', 'doc_version', 'method', 'given_at')
    search_fields = ('user__email',)
    date_hierarchy = 'given_at'
    list_select_related = ('user', 'lead')
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
