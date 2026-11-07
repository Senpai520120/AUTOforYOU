from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction

from audit.models import AuditAction
from audit.services import log_action
from local_listings.models import LocalListing
from users.admin import ask_reason
from users.services import BLOCK_REASON_REQUIRED, block_user

from .models import Report


def _close_report(report, actor, request, new_status, action):
    """Статус жалобы + запись журнала в одной транзакции с действием (1.13)."""
    before = {'status': report.status}
    report.status = new_status
    report.save(update_fields=['status'])
    log_action(actor, action, report, request=request, before=before, after={'status': new_status})


@admin.action(permissions=['change'], description='Сховати оголошення + закрити скаргу')
def hide_listing(modeladmin, request, queryset):
    """Сховати оголошення (скарга розглянута → listing hidden)."""
    count = 0
    for report in queryset.select_related('listing'):
        with transaction.atomic():
            listing = report.listing
            if listing and listing.status == LocalListing.Status.ACTIVE:
                listing.status = LocalListing.Status.HIDDEN
                listing.save(update_fields=['status'])
                log_action(
                    request.user, AuditAction.LISTING_HIDE, listing, request=request,
                    reason=f'Скарга report#{report.pk}: {report.get_reason_display()}',
                    before={'status': LocalListing.Status.ACTIVE}, after={'status': LocalListing.Status.HIDDEN},
                )
            _close_report(report, request.user, request, Report.Status.REVIEWED, AuditAction.REPORT_REVIEW)
        count += 1
    modeladmin.message_user(request, f'Оголошення сховано, скарги закриті: {count}.', messages.SUCCESS)


@admin.action(permissions=['change'], description='Заблокувати користувача + закрити скаргу (з причиною)')
def ban_reported_user(modeladmin, request, queryset):
    """Блокування через users.services.block_user (UserBlock, журнал, сесії, оголошення → hidden)."""
    reason, response = ask_reason(
        modeladmin, request, queryset, title='Блокування користувача за скаргою',
        prompt='Вкажіть причину блокування', required_error=BLOCK_REASON_REQUIRED,
    )
    if response is not None:
        return response
    count = skipped = 0
    for report in queryset.select_related('reported_user', 'listing__owner'):
        target = report.reported_user or (report.listing.owner if report.listing else None)
        if not target:
            continue
        with transaction.atomic():
            try:
                block_user(target, request.user, reason, request=request)
            except ValidationError:
                skipped += 1  # співробітника або себе не блокуємо; скарга лишається відкритою
                continue
            _close_report(report, request.user, request, Report.Status.REVIEWED, AuditAction.REPORT_REVIEW)
        count += 1
    modeladmin.message_user(
        request, f'Заблоковано користувачів, скарги закриті: {count}. Пропущено: {skipped}.', messages.WARNING,
    )


@admin.action(permissions=['change'], description='Відхилити скарги')
def dismiss_report(modeladmin, request, queryset):
    count = 0
    for report in queryset.exclude(status=Report.Status.DISMISSED):
        with transaction.atomic():
            _close_report(report, request.user, request, Report.Status.DISMISSED, AuditAction.REPORT_DISMISS)
        count += 1
    modeladmin.message_user(request, f'Скарги відхилено: {count}.', messages.INFO)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'reporter', 'listing', 'reported_user', 'reason', 'status', 'created_at']
    list_filter = ['status', 'reason']
    search_fields = ['reporter__email', 'listing__make', 'reported_user__email']
    raw_id_fields = ['reporter', 'listing', 'reported_user']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    actions = [hide_listing, ban_reported_user, dismiss_report]

    fieldsets = (
        ('Скарга', {
            'fields': ('reporter', 'listing', 'reported_user', 'reason', 'comment', 'status'),
        }),
        ('Дата', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('reporter', 'listing', 'reported_user')
