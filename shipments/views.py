from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, filters
from .models import Shipment
from .serializers import ShipmentSerializer, ShipmentListSerializer


@extend_schema_view(
    get=extend_schema(tags=['shipments'], summary='Список контейнеров'),
)
class ShipmentListView(generics.ListAPIView):
    serializer_class = ShipmentListSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['container_no', 'vessel']

    def get_queryset(self):
        qs = Shipment.objects.prefetch_related('vehicles').all()
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs


@extend_schema_view(
    get=extend_schema(tags=['shipments'], summary='Детали контейнера + история событий'),
)
class ShipmentDetailView(generics.RetrieveAPIView):
    serializer_class = ShipmentSerializer
    queryset = Shipment.objects.prefetch_related('vehicles__images', 'events').all()
