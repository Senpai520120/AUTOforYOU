from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, filters, permissions
from .models import Listing
from .serializers import ListingSerializer, ListingCreateSerializer


@extend_schema_view(
    get=extend_schema(
        tags=['listings'],
        summary='Каталог объявлений',
        description='Список объявлений с фильтрацией и поиском.',
        parameters=[
            OpenApiParameter('status', OpenApiTypes.STR, description='in_transit | in_stock | sold'),
            OpenApiParameter('channel', OpenApiTypes.STR, description='retail | wholesale'),
            OpenApiParameter('fuel_type', OpenApiTypes.STR, description='petrol | diesel | electric | hybrid'),
            OpenApiParameter('currency', OpenApiTypes.STR, description='USD | UAH | EUR'),
            OpenApiParameter('max_price', OpenApiTypes.NUMBER, description='Максимальная цена'),
            OpenApiParameter('search', OpenApiTypes.STR, description='Поиск по марке, модели, VIN'),
        ],
    ),
)
class ListingListView(generics.ListAPIView):
    serializer_class = ListingSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['vehicle__make', 'vehicle__model', 'vehicle__vin']
    ordering_fields = ['price', 'created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Listing.objects.select_related('vehicle', 'seller').prefetch_related('vehicle__images')

        status = self.request.query_params.get('status')
        channel = self.request.query_params.get('channel')
        fuel_type = self.request.query_params.get('fuel_type')
        max_price = self.request.query_params.get('max_price')
        currency = self.request.query_params.get('currency')

        if status:
            qs = qs.filter(status=status)
        if channel:
            qs = qs.filter(channel=channel)
        if fuel_type:
            qs = qs.filter(vehicle__fuel_type=fuel_type)
        if currency:
            qs = qs.filter(currency=currency)
        if max_price:
            try:
                qs = qs.filter(price__lte=max_price)
            except (ValueError, TypeError):
                pass

        return qs


@extend_schema_view(
    get=extend_schema(tags=['listings'], summary='Детали объявления'),
)
class ListingDetailView(generics.RetrieveAPIView):
    queryset = Listing.objects.select_related('vehicle', 'seller').prefetch_related('vehicle__images')
    serializer_class = ListingSerializer


@extend_schema_view(
    post=extend_schema(tags=['listings'], summary='Создать объявление', description='Требует авторизации.'),
)
class ListingCreateView(generics.CreateAPIView):
    serializer_class = ListingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
