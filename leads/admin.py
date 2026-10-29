from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from rest_framework.throttling import ScopedRateThrottle

from . import exports, funnel
from .models import (
    Lead,
    LeadExportLog,
    LeadJournalSettings,
    LeadNotificationSettings,
    LeadPartnerStatusChange,
    LeadStatusChange,
)
from .services import ALLOWED_TRANSITIONS, Q_FIELDS, change_status, qualify_lead, set_partner_status

DIRECT = 'пряме'
RESEND_ACTION_LIMIT = 20  # защита от случайного «выбрать все»: каждая заявка - Telegram и письмо


class _ExportScope:
    throttle_scope = 'lead_export'  # общий счётчик с API-экспортом


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


class LeadPartnerStatusChangeInline(admin.TabularInline):
    model = LeadPartnerStatusChange
    extra = 0
    can_delete = False
    fields = ('created_at', 'from_status', 'to_status', 'changed_by')
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
        fields = ('status', 'partner_status', 'assigned_to', *Q_FIELDS)

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get('status')
        old = self.instance.status
        if new and new != old:
            if cleaned.get('reopen') and not can_reopen(self.request_user):
                raise forms.ValidationError('Перевідкривати заявки може лише адміністратор.')
            if not cleaned.get('reopen') and new not in ALLOWED_TRANSITIONS.get(old, set()):
                raise forms.ValidationError(f'Перехід {old} -> {new} неприпустимий.')
        owner = self.instance.assigned_to_id
        user = self.request_user
        if (self.changed_data and owner not in (None, getattr(user, 'pk', None))
                and not can_reopen(user)):
            raise forms.ValidationError('Заявку вже взяв інший брокер: змінювати її може лише він або адміністратор.')
        return cleaned


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('public_id', 'created_at', 'name', 'phone', 'contact_method', 'source_display',
                    'status', 'partner_status', 'qualification', 'total_uah', 'telegram_status', 'email_status', 'telegram_sent_at')
    list_filter = ('status', 'partner_status', 'qualification', 'source', 'telegram_status', 'email_status',
                   UtmSourceFilter)
    actions = ['resend_to_broker', 'export_csv']
    search_fields = ('public_id', 'name', 'phone')
    date_hierarchy = 'created_at'
    inlines = [LeadStatusChangeInline, LeadPartnerStatusChangeInline]
    form = LeadAdminForm
    # Редактируются только status, partner_status, assigned_to, internal-поля брокера.
    readonly_fields = (
        'public_id', 'user', 'name', 'phone', 'email', 'contact_method', 'contact_handle', 'comment',
        'source', 'landing_slug', 'budget_usd', 'needed_when', 'city', 'vehicle_label',
        'utm', 'referrer', 'entry_page_url', 'page_url', 'first_response_at',
        'qualification', 'attribution_until', 'journal_message_id', 'journal_sent_at',
        'telegram_status', 'telegram_sent_at', 'telegram_error',
        'email_status', 'email_sent_at', 'email_error', 'notify_attempts', 'last_notify_attempt_at',
        'undelivered_alerted_at',
        'calculation', 'listing', 'snapshot_summary', 'calculation_snapshot', 'total_usd', 'total_uah',
        'consent_at', 'partner_name', 'partner_consent_at', 'partner_consent_text',
        'created_at', 'updated_at',
    )
    fields = (
        'public_id', 'status', 'reopen', 'partner_status', 'assigned_to', 'first_response_at',
        'qualification', *Q_FIELDS, 'attribution_until', 'journal_message_id', 'journal_sent_at',
        'name', 'phone', 'email', 'contact_method', 'contact_handle', 'comment', 'user',
        'source', 'landing_slug', 'vehicle_label', 'budget_usd', 'needed_when', 'city',
        'utm', 'referrer', 'entry_page_url', 'page_url',
        'telegram_status', 'telegram_sent_at', 'telegram_error',
        'email_status', 'email_sent_at', 'email_error', 'notify_attempts', 'last_notify_attempt_at',
        'undelivered_alerted_at',
        'calculation', 'listing', 'snapshot_summary', 'calculation_snapshot', 'total_usd', 'total_uah',
        'consent_at', 'partner_name', 'partner_consent_at', 'partner_consent_text',
        'created_at', 'updated_at',
    )

    @admin.action(description='Надіслати брокеру повторно', permissions=['change'])
    def resend_to_broker(self, request, queryset):
        # force=True повторяє Telegram, а затем резервный email (оба канала).
        from .tasks import notify_broker_new_lead
        ids = list(queryset.values_list('pk', flat=True)[:RESEND_ACTION_LIMIT + 1])
        if len(ids) > RESEND_ACTION_LIMIT:
            self.message_user(
                request, f'Забагато заявок: повторно можна надіслати не більше {RESEND_ACTION_LIMIT} за раз.',
                messages.ERROR)
            return
        count = 0
        for lead_id in ids:
            notify_broker_new_lead.delay(lead_id, force=True)
            count += 1
        self.message_user(request, f'Поставлено в чергу: {count}', messages.SUCCESS)

    @admin.action(description='Завантажити CSV (без персональних даних)', permissions=['view'])
    def export_csv(self, request, queryset):
        if not ScopedRateThrottle().allow_request(request, _ExportScope()):
            self.message_user(request, 'Забагато експортів, спробуйте пізніше.', messages.ERROR)
            return None
        ids = list(queryset.values_list('pk', flat=True))
        qs = Lead.objects.filter(pk__in=ids).order_by('created_at', 'pk')
        # Пошуковий запит q не пишемо: це може бути імʼя або телефон.
        filters = {k: v for k, v in request.GET.dict().items() if k != 'q'}
        filters['selected'] = len(ids)
        return exports.csv_response(qs, user=request.user, channel='admin', filters=filters)

    def get_urls(self):
        custom = [path('funnel/', self.admin_site.admin_view(self.funnel_view), name='leads_lead_funnel')]
        return custom + super().get_urls()

    def funnel_view(self, request):
        user = request.user
        if not (user.is_superuser or user.has_perm('leads.view_funnel')):
            raise PermissionDenied
        year, month = funnel.parse_month(request.GET.get('month'))
        context = {
            **self.admin_site.each_context(request),
            'title': 'Воронка за місяць',
            'opts': self.model._meta,
            'data': funnel.funnel(year, month),
        }
        return TemplateResponse(request, 'admin/leads/funnel.html', context)

    def changelist_view(self, request, extra_context=None):
        from telegram_bot.provider import telegram_configured

        from .notify import broker_chat_id, email_channel_configured
        cfg = LeadNotificationSettings.get_solo()
        tg_ok = bool(cfg.telegram_enabled and broker_chat_id() and telegram_configured())
        if not tg_ok:
            messages.warning(request, 'Telegram для заявок не налаштовано')
        if not tg_ok and not email_channel_configured():
            messages.warning(request, 'Жоден канал сповіщення брокера не налаштовано')
        return super().changelist_view(request, extra_context)

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
        new_status, new_partner = obj.status, obj.partner_status
        obj.status, old_partner = Lead.objects.values_list('status', 'partner_status').get(pk=obj.pk)
        obj.partner_status = old_partner
        super().save_model(request, obj, form, change)
        if new_status != obj.status:
            change_status(obj, new_status, by=request.user, force=bool(form.cleaned_data.get('reopen')))
        if new_partner != old_partner:
            set_partner_status(obj, new_partner, by=request.user, is_admin=can_reopen(request.user))
        if any(f in form.changed_data for f in Q_FIELDS):
            qualify_lead(obj, {f: getattr(obj, f) for f in Q_FIELDS}, by=request.user,
                         is_admin=can_reopen(request.user))


@admin.register(LeadNotificationSettings)
class LeadNotificationSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not LeadNotificationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LeadJournalSettings)
class LeadJournalSettingsAdmin(admin.ModelAdmin):
    # Пороги влияют на квалификацию и сверку с партнёром: только superuser.
    def has_add_permission(self, request):
        return request.user.is_superuser and not LeadJournalSettings.objects.exists()

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LeadExportLog)
class LeadExportLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'channel', 'row_count', 'filters')
    readonly_fields = ('created_at', 'user', 'channel', 'row_count', 'filters')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
