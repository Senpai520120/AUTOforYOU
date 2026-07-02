from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.contrib.admin import helpers

from .models import Region, City, LocalListing, LocalListingImage, PromotionTariff
from .services import approve_listing, reject_listing


# ─── Тарифи просування ────────────────────────────────────────────────────────

@admin.register(PromotionTariff)
class PromotionTariffAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'type', 'price', 'currency', 'duration_days', 'active']
    list_filter = ['type', 'active', 'currency']
    list_editable = ['price', 'active']
    search_fields = ['code', 'name']
    ordering = ['type', 'price']


# ─── Регіони / Міста ──────────────────────────────────────────────────────────

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


class CityInline(admin.TabularInline):
    model = City
    extra = 1
    prepopulated_fields = {'slug': ('name',)}


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ['name', 'region', 'slug']
    list_filter = ['region']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'region__name']


# ─── Дії модерації ────────────────────────────────────────────────────────────

def approve_listings(modeladmin, request, queryset):
    """Масово одобрити вибрані оголошення (тільки pending)."""
    count = 0
    for listing in queryset.filter(status=LocalListing.Status.PENDING):
        approve_listing(listing, request.user)
        count += 1
    modeladmin.message_user(request, f'Опубліковано оголошень: {count}.', messages.SUCCESS)


approve_listings.short_description = 'Одобрити (→ active)'


def reject_with_reason(modeladmin, request, queryset):
    """Відхилити вибрані оголошення з вказанням причини — проміжна форма."""
    if 'confirm' in request.POST:
        reason = request.POST.get('reason', '').strip() or 'Не відповідає правилам розміщення.'
        count = 0
        for listing in queryset.filter(status=LocalListing.Status.PENDING):
            reject_listing(listing, request.user, reason)
            count += 1
        modeladmin.message_user(request, f'Відхилено оголошень: {count}.', messages.WARNING)
        return HttpResponseRedirect(request.get_full_path())

    return TemplateResponse(
        request,
        'admin/local_listings/reject_reason.html',
        {
            'queryset': queryset,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
            'title': 'Відхилити оголошення — вказати причину',
            'opts': modeladmin.model._meta,
        },
    )


reject_with_reason.short_description = 'Відхилити (з причиною)'


# ─── Список оголошень (усі) ───────────────────────────────────────────────────

class LocalListingImageInline(admin.TabularInline):
    model = LocalListingImage
    extra = 1
    readonly_fields = ['created_at']


@admin.register(LocalListing)
class LocalListingAdmin(admin.ModelAdmin):
    list_display = [
        'short_title', 'owner', 'status', 'region', 'city',
        'seller_type', 'agreed_to_rules', 'moderated_by', 'created_at',
    ]
    list_filter = ['status', 'fuel_type', 'body_type', 'transmission', 'seller_type', 'region']
    search_fields = ['make', 'model', 'owner__email', 'contact_phone']
    readonly_fields = ['created_at', 'updated_at', 'moderated_at', 'agreed_to_rules_at', 'expiry_warned', 'bumped_at']
    inlines = [LocalListingImageInline]
    raw_id_fields = ['owner', 'region', 'city', 'moderated_by']
    actions = [approve_listings, reject_with_reason]

    fieldsets = (
        ('Оголошення', {
            'fields': (
                'owner', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
                'fuel_type', 'transmission', 'body_type', 'condition',
                'price', 'currency', 'price_type',
                'region', 'city', 'description', 'contact_phone', 'seller_type',
            ),
        }),
        ('Статус і модерація', {
            'fields': (
                'status', 'rejection_reason',
                'moderated_by', 'moderated_at',
            ),
        }),
        ('Згода з правилами', {
            'fields': ('agreed_to_rules', 'agreed_to_rules_at'),
            'classes': ('collapse',),
        }),
        ('Термін дії і просування', {
            'fields': ('expires_at', 'expiry_warned', 'promoted_until', 'bumped_at'),
            'classes': ('collapse',),
        }),
        ('Дати', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Оголошення')
    def short_title(self, obj):
        return f'{obj.make} {obj.model} {obj.year}'


# ─── Черга модерації (тільки pending) ────────────────────────────────────────

class PendingLocalListingProxy(LocalListing):
    """Проксі-модель для окремої секції «На модерації» в Django Admin."""
    class Meta:
        proxy = True
        verbose_name = 'Оголошення на модерації'
        verbose_name_plural = 'Черга модерації'


@admin.register(PendingLocalListingProxy)
class ModerationQueueAdmin(admin.ModelAdmin):
    list_display = ['short_title', 'owner_email', 'region', 'price', 'currency', 'created_at']
    list_filter = ['region', 'fuel_type']
    search_fields = ['make', 'model', 'owner__email']
    readonly_fields = [
        'owner', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
        'fuel_type', 'transmission', 'body_type', 'condition',
        'price', 'currency', 'price_type', 'region', 'city',
        'description', 'contact_phone', 'seller_type',
        'agreed_to_rules', 'agreed_to_rules_at',
        'created_at', 'updated_at',
    ]
    actions = [approve_listings, reject_with_reason]
    inlines = [LocalListingImageInline]

    fieldsets = (
        ('Оголошення', {
            'fields': (
                'owner', 'make', 'model', 'year', 'mileage_km', 'engine_cc',
                'fuel_type', 'transmission', 'body_type', 'condition',
                'price', 'currency', 'price_type',
                'region', 'city', 'description', 'contact_phone', 'seller_type',
            ),
        }),
        ('Дата подачі', {'fields': ('created_at',)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            status=LocalListing.Status.PENDING
        ).select_related('owner', 'region', 'city').order_by('created_at')

    def has_add_permission(self, request):
        return False

    @admin.display(description='Оголошення')
    def short_title(self, obj):
        return f'{obj.make} {obj.model} {obj.year}'

    @admin.display(description='Власник')
    def owner_email(self, obj):
        return obj.owner.email
