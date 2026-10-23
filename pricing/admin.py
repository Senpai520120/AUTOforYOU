from django.contrib import admin, messages
from django.utils import timezone

from . import cache as pricing_cache
from .models import (
    AuctionFeeTier,
    AuctionFixedFee,
    BrokerServiceFee,
    Calculation,
    CalculatorSettings,
    CustomsCalcRule,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UaDeliveryRate,
    UsLandRoute,
)

TARIFF_MODELS = (AuctionFeeTier, AuctionFixedFee, UsLandRoute, OceanFreightRate, EuToUaDeliveryRate,
                 CustomsExciseRate, PensionFundBracket, CustomsCalcRule, UaDeliveryRate, BrokerServiceFee)


def unverified_active_count(today=None) -> int:
    """Сколько действующих тарифов ещё не проверено владельцем (пока > 0 - сайт показывает демо-баннер)."""
    today = today or timezone.localdate()
    total = 0
    for model in TARIFF_MODELS:
        total += model.objects.filter(is_verified=False, valid_from__lte=today).exclude(valid_to__lt=today).count()
    return total


class TariffAdmin(admin.ModelAdmin):
    """Общее для тарифов (2.6): отметка «Перевірено власником» прямо в списке и action."""
    actions = ['mark_verified']
    list_editable = ('is_verified',)

    def get_list_filter(self, request):
        return (*super().get_list_filter(request), 'is_verified')

    @admin.action(permissions=['change'], description='Позначити перевіреними')
    def mark_verified(self, request, queryset):
        updated = queryset.update(is_verified=True)
        pricing_cache.invalidate_all()  # update() не шлёт post_save - кэш сбрасываем явно
        self.message_user(request, f'Позначено перевіреними: {updated}.', messages.SUCCESS)

    def changelist_view(self, request, extra_context=None):
        pending = unverified_active_count()
        if pending:
            messages.info(request, f'Неперевірених діючих тарифів: {pending}. Поки вони є, сайт показує демо-банер.')
        return super().changelist_view(request, extra_context)


@admin.register(AuctionFeeTier)
class AuctionFeeTierAdmin(TariffAdmin):
    list_display = (
        'auction', 'member_type', 'payment_type', 'title_type',
        'bid_min', 'bid_max', 'fee_flat', 'fee_percent',
        'valid_from', 'valid_to', 'is_verified',
    )
    list_filter = ('auction', 'member_type', 'payment_type', 'title_type')
    ordering = ('auction', 'member_type', 'bid_min')


@admin.register(AuctionFixedFee)
class AuctionFixedFeeAdmin(TariffAdmin):
    list_display = ('auction', 'fee_type', 'title_type', 'amount', 'valid_from', 'valid_to', 'is_verified')
    list_filter = ('auction', 'fee_type', 'title_type')


@admin.register(UsLandRoute)
class UsLandRouteAdmin(TariffAdmin):
    list_display = ('auction_location', 'us_port', 'cost_usd', 'valid_from', 'valid_to', 'is_verified')


@admin.register(OceanFreightRate)
class OceanFreightRateAdmin(TariffAdmin):
    list_display = ('us_port', 'eu_port', 'cost_usd', 'valid_from', 'valid_to', 'is_verified')


@admin.register(EuToUaDeliveryRate)
class EuToUaDeliveryRateAdmin(TariffAdmin):
    list_display = ('eu_port', 'cost_usd', 'valid_from', 'valid_to', 'is_verified')


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('from_currency', 'to_currency', 'rate', 'date', 'source')
    list_filter = ('from_currency', 'to_currency', 'source')
    date_hierarchy = 'date'


@admin.register(CustomsExciseRate)
class CustomsExciseRateAdmin(TariffAdmin):
    list_display = (
        'fuel_type', 'engine_cc_min', 'engine_cc_max',
        'eur_per_100cc', 'ev_excise_eur_per_kwh',
        'duty_rate', 'vat_rate', 'valid_from', 'valid_to', 'is_verified',
    )
    list_filter = ('fuel_type',)


@admin.register(PensionFundBracket)
class PensionFundBracketAdmin(TariffAdmin):
    list_display = ('min_value_uah', 'max_value_uah', 'rate', 'valid_from', 'valid_to', 'is_verified')


@admin.register(CustomsCalcRule)
class CustomsCalcRuleAdmin(TariffAdmin):
    """Правило розмитнення (2.5, Q5): значення підтверджує митний брокер; поки не звірено - «орієнтовно»."""
    list_display = ('valid_from', 'valid_to', 'pension_bracket_base', 'pension_rate_base',
                    'customs_value_includes_eu_to_ua', 'confirmed_by_broker', 'confirmed_at', 'is_verified')
    list_filter = ('confirmed_by_broker',)

    def get_readonly_fields(self, request, obj=None):
        # «Звірено з брокером» снимает пометку «орієнтовний розрахунок» - ставит только admin-роль.
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_admin_role:
            fields += ['confirmed_by_broker', 'confirmed_at']
        return fields

    fieldsets = (
        ('Період дії', {'fields': ('valid_from', 'valid_to')}),
        ('Пенсійний збір', {'fields': ('pension_bracket_base', 'pension_rate_base')}),
        ('Митна вартість', {'fields': ('customs_value_includes_eu_to_ua',)}),
        ('Віковий коефіцієнт акцизу', {'fields': ('age_coeff_min', 'age_coeff_max', 'age_offset_years')}),
        ('Звірка з брокером', {'fields': ('confirmed_by_broker', 'confirmed_at', 'note', 'is_verified')}),
    )


@admin.register(Calculation)
class CalculationAdmin(admin.ModelAdmin):
    """Снимок расчёта - только просмотр (02-S4): суммы, входы и ставки не редактируются."""
    list_display = ('pk', 'user', 'total_usd', 'total_uah', 'is_estimate', 'created_at')
    list_filter = ('is_estimate',)
    readonly_fields = ('user', 'inputs_snapshot', 'rates_snapshot', 'breakdown', 'total_usd', 'total_uah',
                       'is_estimate', 'created_at')
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)  # снимок - история расчётов, удаляет только superuser


class ActiveNowFilter(admin.SimpleListFilter):
    """«Діють зараз» (2.7): valid_from <= сьогодні и valid_to пусто или >= сьогодні."""
    title = 'Діють зараз'
    parameter_name = 'active_now'

    def lookups(self, request, model_admin):
        return (('yes', 'Так'), ('no', 'Ні'))

    def queryset(self, request, queryset):
        today = timezone.localdate()
        active = queryset.filter(valid_from__lte=today).exclude(valid_to__lt=today)
        if self.value() == 'yes':
            return active
        if self.value() == 'no':
            return queryset.exclude(pk__in=active.values('pk'))
        return queryset


@admin.register(UaDeliveryRate)
class UaDeliveryRateAdmin(TariffAdmin):
    """Доставка по Україні (2.7, Q6): сума або «Уточнюйте»; заповнює власник."""
    list_display = ('destination', 'eu_port', 'cost_usd', 'quote_on_request', 'sort_order',
                    'valid_from', 'valid_to', 'is_verified')
    list_filter = (ActiveNowFilter, 'quote_on_request')
    ordering = ('sort_order', 'destination')


@admin.register(BrokerServiceFee)
class BrokerServiceFeeAdmin(TariffAdmin):
    """Послуги брокера (2.7, Q6): фіксована сума (за замовчуванням) або % від ціни авто на аукціоні."""
    list_display = ('title', 'fee_mode', 'amount_usd', 'percent', 'sort_order', 'valid_from', 'valid_to',
                    'is_verified')
    list_filter = (ActiveNowFilter, 'fee_mode')
    ordering = ('sort_order', 'title')


@admin.register(CalculatorSettings)
class CalculatorSettingsAdmin(admin.ModelAdmin):
    """Тексты калькулятора (2.6): одна запись, создаёт data-миграция."""
    list_display = ('__str__',)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not CalculatorSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
