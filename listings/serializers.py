from django.utils import timezone
from rest_framework import serializers
from .models import Listing
from vehicles.serializers import VehicleSerializer


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

    def create(self, validated_data):
        validated_data['seller'] = self.context['request'].user
        return super().create(validated_data)
