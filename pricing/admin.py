from django.contrib import admin
from .models import (
    AuctionFeeTier, UsLandRoute, OceanFreightRate,
    EuToUaDeliveryRate, ExchangeRate, CustomsExciseRate,
    PensionFundBracket, Calculation,
)


@admin.register(AuctionFeeTier)
class AuctionFeeTierAdmin(admin.ModelAdmin):
    list_display = ('auction', 'min_price_usd', 'max_price_usd', 'fee_fixed_usd', 'fee_pct', 'valid_from', 'valid_to')
    list_filter = ('auction',)


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
    list_display = ('fuel_type', 'eur_per_100cc', 'duty_rate', 'vat_rate', 'valid_from', 'valid_to')
    list_filter = ('fuel_type',)


@admin.register(PensionFundBracket)
class PensionFundBracketAdmin(admin.ModelAdmin):
    list_display = ('min_value_uah', 'max_value_uah', 'rate', 'valid_from', 'valid_to')


@admin.register(Calculation)
class CalculationAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'total_usd', 'total_uah', 'is_estimate', 'created_at')
    list_filter = ('is_estimate',)
    readonly_fields = ('inputs_snapshot', 'rates_snapshot', 'breakdown', 'created_at')
    date_hierarchy = 'created_at'
