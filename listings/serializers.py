from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from vehicles.models import Vehicle
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

    def validate_calculation(self, value):
        if value is None:
            return value
        user = self.context['request'].user
        # Чужой расчёт нельзя привязать (IDOR по PK); админ может привязать любой.
        if value.user_id != user.pk and not user.is_admin_role:
            raise serializers.ValidationError('Розрахунок не знайдено.')
        return value

    def validate_is_express_buyout(self, value):
        # Срочный выкуп уходит в B2B-канал Telegram - только админ.
        if value and not self.context['request'].user.is_admin_role:
            raise serializers.ValidationError('Термінний викуп може позначити лише адміністратор.')
        return value

    def validate(self, attrs):
        channel = attrs.get('channel', Listing.Channel.RETAIL)
        if Listing.objects.filter(vehicle=attrs['vehicle'], channel=channel).exists():
            raise serializers.ValidationError('Оголошення для цього авто в цьому каналі вже існує.')
        user = self.context['request'].user
        # Retail-оголошення на авто з оптовим розкрило б його VIN через visible_vehicles.
        if (
            channel == Listing.Channel.RETAIL
            and not user.is_admin_role
            and Listing.objects.filter(vehicle=attrs['vehicle']).exclude(channel=channel).exists()
        ):
            raise serializers.ValidationError({'vehicle': 'Авто не знайдено.'})
        return attrs

    def create(self, validated_data):
        validated_data['seller'] = self.context['request'].user
        return super().create(validated_data)


class ListingFilterSerializer(serializers.Serializer):
    """Query-параметры каталога и B2B-доски (задача 2.8, 04-Q1/04-Q8)."""

    status = serializers.ChoiceField(choices=Listing.ListingStatus.choices, required=False)
    channel = serializers.ChoiceField(choices=Listing.Channel.choices, required=False)
    currency = serializers.ChoiceField(choices=Listing.Currency.choices, required=False)
    fuel_type = serializers.ChoiceField(choices=Vehicle.FuelType.choices, required=False)
    # max_digits=12, decimal_places=2 - те же границы, что у Listing.price.
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False)
