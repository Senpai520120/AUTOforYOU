from django.contrib import admin, messages

from local_listings.models import LocalListing

from .models import Report


def hide_listing(modeladmin, request, queryset):
    """Сховати оголошення (скарга розглянута → listing hidden)."""
    count = 0
    for report in queryset.select_related('listing'):
        if report.listing and report.listing.status == LocalListing.Status.ACTIVE:
            report.listing.status = LocalListing.Status.HIDDEN
            report.listing.save(update_fields=['status'])
        report.status = Report.Status.REVIEWED
        report.save(update_fields=['status'])
        count += 1
    modeladmin.message_user(request, f'Оголошення сховано, скарги закриті: {count}.', messages.SUCCESS)

hide_listing.short_description = 'Сховати оголошення + закрити скаргу'


def ban_reported_user(modeladmin, request, queryset):
    """Забанити користувача: is_banned=True, is_active=False, активні оголошення → hidden."""
    count = 0
    for report in queryset.select_related('reported_user', 'listing__owner'):
        target = report.reported_user or (report.listing.owner if report.listing else None)
        if not target:
            continue
        if not target.is_banned:
            target.is_banned = True
            target.is_active = False
            target.save(update_fields=['is_banned', 'is_active'])
            LocalListing.objects.filter(
                owner=target,
                status__in=[LocalListing.Status.ACTIVE, LocalListing.Status.PENDING],
            ).update(status=LocalListing.Status.HIDDEN)
        report.status = Report.Status.REVIEWED
        report.save(update_fields=['status'])
        count += 1
    modeladmin.message_user(request, f'Забанено користувачів, скарги закриті: {count}.', messages.WARNING)

ban_reported_user.short_description = 'Забанити користувача + закрити скаргу'


def dismiss_report(modeladmin, request, queryset):
    queryset.update(status=Report.Status.DISMISSED)
    modeladmin.message_user(request, 'Скарги відхилено.', messages.INFO)

dismiss_report.short_description = 'Відхилити скарги'


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
