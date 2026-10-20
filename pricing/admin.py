from django.contrib import admin

from .models import (
    AuctionFeeTier,
    AuctionFixedFee,
    Calculation,
    CustomsCalcRule,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UsLandRoute,
)


@admin.register(AuctionFeeTier)
class AuctionFeeTierAdmin(admin.ModelAdmin):
    list_display = (
        'auction', 'member_type', 'payment_type', 'title_type',
        'bid_min', 'bid_max', 'fee_flat', 'fee_percent',
        'valid_from', 'valid_to',
    )
    list_filter = ('auction', 'member_type', 'payment_type', 'title_type')
    ordering = ('auction', 'member_type', 'bid_min')


@admin.register(AuctionFixedFee)
class AuctionFixedFeeAdmin(admin.ModelAdmin):
    list_display = ('auction', 'fee_type', 'title_type', 'amount', 'valid_from', 'valid_to')
    list_filter = ('auction', 'fee_type', 'title_type')


@admin.register(UsLandRoute)
class UsLandRouteAdmin(admin.ModelAdmin):
    list_display = ('auction_location', 'us_port', 'cost_usd', 'valid_from', 'valid_to')


@admin.register(OceanFreightRate)
class OceanFreightRateAdmin(admin.ModelAdmin):
    list_display = ('us_port', 'eu_port', 'cost_usd', 'valid_from', 'valid_to')


@admin.register(EuToUaDeliveryRate)
class EuToUaDeliveryRateAdmin(admin.ModelAdmin):
    list_display = ('eu_port', 'cost_usd', 'valid_from', 'valid_to')


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('from_currency', 'to_currency', 'rate', 'date')
    list_filter = ('from_currency', 'to_currency')
    date_hierarchy = 'date'


@admin.register(CustomsExciseRate)
class CustomsExciseRateAdmin(admin.ModelAdmin):
    list_display = (
        'fuel_type', 'engine_cc_min', 'engine_cc_max',
        'eur_per_100cc', 'ev_excise_eur_per_kwh',
        'duty_rate', 'vat_rate', 'valid_from', 'valid_to',
    )
    list_filter = ('fuel_type',)


@admin.register(PensionFundBracket)
class PensionFundBracketAdmin(admin.ModelAdmin):
    list_display = ('min_value_uah', 'max_value_uah', 'rate', 'valid_from', 'valid_to')


@admin.register(CustomsCalcRule)
class CustomsCalcRuleAdmin(admin.ModelAdmin):
    """Правило розмитнення (2.5, Q5): значення підтверджує митний брокер; поки не звірено - «орієнтовно»."""
    list_display = ('valid_from', 'valid_to', 'pension_bracket_base', 'pension_rate_base',
                    'customs_value_includes_eu_to_ua', 'confirmed_by_broker', 'confirmed_at')
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
        ('Звірка з брокером', {'fields': ('confirmed_by_broker', 'confirmed_at', 'note')}),
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
