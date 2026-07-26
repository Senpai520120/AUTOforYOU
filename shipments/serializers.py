from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from vehicles.serializers import VehicleSerializer

from .models import Shipment, TrackingEvent


class TrackingEventSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = TrackingEvent
        fields = ('id', 'status', 'status_display', 'note', 'photo', 'created_at')


class ShipmentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    arrival_port_eu_display = serializers.CharField(source='get_arrival_port_eu_display', read_only=True)
    events = TrackingEventSerializer(many=True, read_only=True)
    vehicles = VehicleSerializer(many=True, read_only=True)
    vehicle_count = serializers.SerializerMethodField()
    next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = (
            'id', 'container_no', 'vessel', 'us_warehouse',
            'departure_port_us', 'arrival_port_eu', 'arrival_port_eu_display',
            'eta', 'status', 'status_display', 'next_statuses',
            'vehicles', 'vehicle_count', 'events',
            'created_at', 'updated_at',
        )

    @extend_schema_field(serializers.IntegerField())
    def get_vehicle_count(self, obj):
        # vehicles prefetched — используем кэш prefetch_related
        if hasattr(obj, '_prefetched_objects_cache') and 'vehicles' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['vehicles'])
        return obj.vehicles.count()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_next_statuses(self, obj):
        return Shipment.VALID_TRANSITIONS.get(obj.status, [])


class ShipmentListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    vehicle_count = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = (
            'id', 'container_no', 'vessel', 'arrival_port_eu',
            'eta', 'status', 'status_display', 'vehicle_count', 'created_at',
        )

    @extend_schema_field(serializers.IntegerField())
    def get_vehicle_count(self, obj):
        if hasattr(obj, '_prefetched_objects_cache') and 'vehicles' in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache['vehicles'])
        return obj.vehicles.count()
