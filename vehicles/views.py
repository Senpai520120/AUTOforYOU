from rest_framework import generics, filters
from .models import Vehicle
from .serializers import VehicleSerializer


class VehicleListView(generics.ListAPIView):
    queryset = Vehicle.objects.prefetch_related('images').all()
    serializer_class = VehicleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['make', 'model', 'vin']


class VehicleDetailView(generics.RetrieveAPIView):
    queryset = Vehicle.objects.prefetch_related('images').all()
    serializer_class = VehicleSerializer
