from django.contrib import admin, messages
from django.utils.html import format_html

from content.admin import AdminOnlyMixin

from .models import LandingSettings, ModelLandingPage
from .services import build_landing_calculation, publication_warning


@admin.register(ModelLandingPage)
class ModelLandingPageAdmin(AdminOnlyMixin, admin.ModelAdmin):
    list_display = ('title_display', 'slug', 'is_published', 'calculation_total', 'sort_order')
    list_editable = ('sort_order',)
    list_filter = ('is_published',)
    search_fields = ('slug', 'make', 'model')
    readonly_fields = ('calculation_preview', 'created_at', 'updated_at')
    actions = ['publish_selected']
    fieldsets = (
        (None, {'fields': ('slug', 'make', 'model', 'year_from', 'year_to', 'is_published', 'sort_order')}),
        ('Вхідні дані розрахунку', {'fields': (
            'calc_year', 'auction_price_usd', 'fuel_type', 'engine_cc', 'battery_capacity_kwh', 'auction',
            'auction_location', 'us_port', 'eu_port', 'calculation_preview')}),
        ('Тексти', {'fields': ('h1', 'intro', 'description', 'included_text', 'typical_term_text',
                               'meta_title', 'meta_description')}),
        ('Службове', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Модель', ordering='make')
    def title_display(self, obj):
        return obj.title

    @admin.display(description='Розрахунок')
    def calculation_total(self, obj):
        calc = build_landing_calculation(obj)
        if calc is None:
            # Опублікована сторінка без розрахунку на сайті не показується (404) - це видно одразу.
            return 'немає розрахунку' + (' (сторінка прихована)' if obj.is_published else '')
        return f'${calc["total_usd"]} / {calc["total_uah"]} грн'

    @admin.display(description='Попередній перегляд розрахунку')
    def calculation_preview(self, obj):
        if obj is None or obj.pk is None:
            return 'Збережіть сторінку, щоб побачити розрахунок.'
        calc = build_landing_calculation(obj)
        if calc is None:
            return 'Розрахунок не виконується: заповніть вхідні дані та перевірте, що діють усі ставки.'
        return format_html('Разом: ${} / {} грн. Ставки від {}. Орієнтовний розрахунок.',
                           calc['total_usd'], calc['total_uah'], calc['rates_valid_from'])

    def _warn(self, request):
        warning = publication_warning()
        if warning:
            self.message_user(request, warning, messages.WARNING)

    def changelist_view(self, request, extra_context=None):
        if request.method == 'GET':
            self._warn(request)
        return super().changelist_view(request, extra_context)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._warn(request)

    @admin.action(description='Опублікувати вибрані')
    def publish_selected(self, request, queryset):
        published = 0
        for page in queryset.filter(is_published=False):
            if page.has_draft_marker():
                self.message_user(request, f'{page}: у текстах лишилась позначка «перевірити».', messages.WARNING)
            elif build_landing_calculation(page) is None:
                self.message_user(request, f'{page}: немає розрахунку (вхідні дані або ставки).', messages.WARNING)
            else:
                page.is_published = True
                page.save(update_fields=['is_published', 'updated_at'])
                published += 1
        self.message_user(request, f'Опубліковано: {published}.', messages.SUCCESS)
        self._warn(request)


@admin.register(LandingSettings)
class LandingSettingsAdmin(AdminOnlyMixin, admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not LandingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
