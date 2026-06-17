from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, filters
from .models import Vehicle
from .serializers import VehicleSerializer


@extend_schema_view(
    get=extend_schema(tags=['vehicles'], summary='Список автомобилей', description='Поиск по make, model, vin.'),
)
class VehicleListView(generics.ListAPIView):
    queryset = Vehicle.objects.prefetch_related('images').all()
    serializer_class = VehicleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['make', 'model', 'vin']


@extend_schema_view(
    get=extend_schema(tags=['vehicles'], summary='Детали автомобиля'),
)
class VehicleDetailView(generics.RetrieveAPIView):
    queryset = Vehicle.objects.prefetch_related('images').all()
    serializer_class = VehicleSerializer
