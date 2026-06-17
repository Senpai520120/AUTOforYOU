from rest_framework import serializers
from .models import Listing
from vehicles.serializers import VehicleSerializer


class ListingSerializer(serializers.ModelSerializer):
    vehicle_detail = VehicleSerializer(source='vehicle', read_only=True)

    class Meta:
        model = Listing
        fields = (
            'id', 'vehicle', 'vehicle_detail', 'seller',
            'price', 'currency', 'channel', 'status',
            'repair_description', 'calculation',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'seller', 'created_at', 'updated_at')


class ListingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ('vehicle', 'price', 'currency', 'channel', 'status', 'repair_description', 'calculation')

    def create(self, validated_data):
        validated_data['seller'] = self.context['request'].user
        return super().create(validated_data)
