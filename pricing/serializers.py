from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from .models import (
    Calculation, AuctionFeeTier, UsLandRoute, OceanFreightRate,
    EuToUaDeliveryRate, ExchangeRate, CustomsExciseRate, PensionFundBracket,
)


class CalculateInputSerializer(serializers.Serializer):
    auction_price_usd = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'))
    engine_cc = serializers.IntegerField(min_value=0, max_value=10000)
    fuel_type = serializers.ChoiceField(choices=['petrol', 'diesel', 'electric', 'hybrid', 'phev'])
    vehicle_year = serializers.IntegerField(min_value=1900, max_value=2100)
    # Ёмкость батареи в кВт·ч — обязательно для EV/PHEV, для ДВС оставить 0
    battery_capacity_kwh = serializers.IntegerField(min_value=0, max_value=200, default=0)
    auction = serializers.ChoiceField(choices=['copart', 'iaai'], default='copart')
    auction_location = serializers.CharField(max_length=100, default='general')
    us_port = serializers.CharField(max_length=50, default='houston')
    eu_port = serializers.ChoiceField(choices=['klaipeda', 'gdansk'], default='klaipeda')


class CalculationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calculation
        fields = ('id', 'user', 'inputs_snapshot', 'rates_snapshot', 'breakdown',
                  'total_usd', 'total_uah', 'is_estimate', 'created_at')
        read_only_fields = fields


class ActiveRatesSerializer(serializers.Serializer):
    """Возвращает текущие активные тарифы для информации."""

    def to_representation(self, instance):
        today = timezone.now().date()

        def active(qs):
            return qs.filter(valid_from__lte=today).filter(
                models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=today)
            )

        from django.db import models
        return {
            'auction_fees': list(
                active(AuctionFeeTier.objects.all()).values(
                    'auction', 'min_price_usd', 'max_price_usd', 'fee_fixed_usd', 'fee_pct'
                )
            ),
            'exchange_rates': list(
                ExchangeRate.objects.order_by('-date').values('from_currency', 'to_currency', 'rate', 'date')[:10]
            ),
        }
