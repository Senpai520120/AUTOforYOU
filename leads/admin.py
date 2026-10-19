from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.html import format_html

from .models import Lead, LeadStatusChange
from .services import ALLOWED_TRANSITIONS, change_status

DIRECT = 'пряме'


class UtmSourceFilter(admin.SimpleListFilter):
    title = 'UTM source'
    parameter_name = 'utm_source'

    def lookups(self, request, model_admin):
        values = (
            Lead.objects.exclude(utm__source__isnull=True)
            .values_list('utm__source', flat=True).distinct()
        )
        return [(v, v) for v in sorted({v for v in values if v})]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(utm__source=self.value())
        return queryset


class LeadStatusChangeInline(admin.TabularInline):
    model = LeadStatusChange
    extra = 0
    can_delete = False
    fields = ('created_at', 'from_status', 'to_status', 'changed_by', 'note')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


def can_reopen(user) -> bool:
    return bool(user.is_superuser or getattr(user, 'is_admin_role', False))


class LeadAdminForm(forms.ModelForm):
    reopen = forms.BooleanField(
        required=False, label='Перевідкрити (обійти порядок статусів)',
        help_text='Лише адміністратор. Без галочки діє звичайний порядок переходів.',
    )
    request_user = None  # выставляет LeadAdmin.get_form

    class Meta:
        model = Lead
        fields = ('status', 'partner_status', 'assigned_to')

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get('status')
        old = self.instance.status
        if new and new != old:
            if cleaned.get('reopen') and not can_reopen(self.request_user):
                raise forms.ValidationError('Перевідкривати заявки може лише адміністратор.')
            if not cleaned.get('reopen') and new not in ALLOWED_TRANSITIONS.get(old, set()):
                raise forms.ValidationError(f'Перехід {old} -> {new} неприпустимий.')
        return cleaned


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('public_id', 'created_at', 'name', 'phone', 'contact_method', 'source_display',
                    'status', 'total_uah')
    list_filter = ('status', 'source', UtmSourceFilter)
    search_fields = ('public_id', 'name', 'phone')
    date_hierarchy = 'created_at'
    inlines = [LeadStatusChangeInline]
    form = LeadAdminForm
    # Редактируются только status, partner_status, assigned_to, internal-поля брокера.
    readonly_fields = (
        'public_id', 'user', 'name', 'phone', 'email', 'contact_method', 'contact_handle', 'comment',
        'source', 'landing_slug', 'budget_usd', 'needed_when', 'city', 'vehicle_label',
        'utm', 'referrer', 'entry_page_url', 'page_url', 'first_response_at',
        'calculation', 'listing', 'snapshot_summary', 'calculation_snapshot', 'total_usd', 'total_uah',
        'consent_at', 'partner_name', 'partner_consent_at', 'partner_consent_text',
        'created_at', 'updated_at',
    )
    fields = (
        'public_id', 'status', 'reopen', 'partner_status', 'assigned_to', 'first_response_at',
        'name', 'phone', 'email', 'contact_method', 'contact_handle', 'comment', 'user',
        'source', 'landing_slug', 'vehicle_label', 'budget_usd', 'needed_when', 'city',
        'utm', 'referrer', 'entry_page_url', 'page_url',
        'calculation', 'listing', 'snapshot_summary', 'calculation_snapshot', 'total_usd', 'total_uah',
        'consent_at', 'partner_name', 'partner_consent_at', 'partner_consent_text',
        'created_at', 'updated_at',
    )

    @admin.display(description='Джерело')
    def source_display(self, obj):
        return (obj.utm or {}).get('source') or DIRECT

    @admin.display(description='Підсумок розрахунку')
    def snapshot_summary(self, obj):
        snap = obj.calculation_snapshot or {}
        if not snap:
            return '—'
        inputs = snap.get('inputs_snapshot') or {}
        parts = [f'{k}: {inputs[k]}' for k in ('make', 'year', 'fuel_type', 'auction_price') if k in inputs]
        return format_html('Разом: ${} / {} грн. {}', snap.get('total_usd'), snap.get('total_uah'),
                           '; '.join(parts))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request_user = request.user
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'assigned_to':
            kwargs['queryset'] = get_user_model().objects.filter(is_staff=True).filter(
                Q(role='broker') | Q(role='admin') | Q(is_superuser=True)
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            return super().save_model(request, obj, form, change)
        new_status = obj.status
        obj.status = Lead.objects.values_list('status', flat=True).get(pk=obj.pk)
        super().save_model(request, obj, form, change)
        if new_status != obj.status:
            change_status(obj, new_status, by=request.user, force=bool(form.cleaned_data.get('reopen')))
