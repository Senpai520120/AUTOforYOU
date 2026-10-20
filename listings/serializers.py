from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from vehicles.serializers import VehicleSerializer

from .models import Listing


class ListingSerializer(serializers.ModelSerializer):
    vehicle_detail = VehicleSerializer(source='vehicle', read_only=True)
    is_express_active = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = (
            'id', 'vehicle', 'vehicle_detail', 'seller',
            'price', 'currency', 'channel', 'status',
            'repair_description', 'calculation',
            'is_express_buyout', 'express_buyout_until', 'is_express_active',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'seller', 'created_at', 'updated_at')

    @extend_schema_field(serializers.BooleanField())
    def get_is_express_active(self, obj):
        if not obj.is_express_buyout:
            return False
        if obj.express_buyout_until is None:
            return True
        return obj.express_buyout_until > timezone.now()


class ListingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = (
            'vehicle', 'price', 'currency', 'channel', 'status',
            'repair_description', 'calculation',
            'is_express_buyout', 'express_buyout_until',
        )

    def validate_calculation(self, calculation):
        """04-S1: чужой расчёт не привязывается (IDOR по pk); admin-роль может привязать любой."""
        user = self.context['request'].user
        if calculation is not None and calculation.user_id != user.pk and not user.is_admin_role:
            raise serializers.ValidationError('Можна привʼязати лише власний розрахунок.')
        return calculation

    def validate(self, attrs):
        from core.modules import module_enabled
        vehicle, channel = attrs.get('vehicle'), attrs.get('channel', Listing.Channel.RETAIL)
        if channel == Listing.Channel.WHOLESALE and not module_enabled('b2b'):
            raise serializers.ValidationError({'channel': 'Оптовий канал вимкнено (B2B заморожено).'})
        if vehicle is not None and Listing.objects.filter(vehicle=vehicle, channel=channel).exists():
            raise serializers.ValidationError({'vehicle': 'Оголошення на це авто в цьому каналі вже існує.'})
        return attrs

    def create(self, validated_data):
        validated_data['seller'] = self.context['request'].user
        return super().create(validated_data)


class ListingFilterSerializer(serializers.Serializer):
    """04-Q1: query-параметры каталога и B2B-доски; нечисловая/отрицательная цена - 400, а не 500."""
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False)
