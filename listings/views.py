from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, filters, permissions
from .models import Listing
from .permissions import IsVerifiedDealerOrAdmin
from .serializers import ListingSerializer, ListingCreateSerializer


def _base_queryset():
    return Listing.objects.select_related('vehicle', 'seller').prefetch_related('vehicle__images')


def _apply_filters(qs, params):
    status = params.get('status')
    channel = params.get('channel')
    fuel_type = params.get('fuel_type')
    max_price = params.get('max_price')
    currency = params.get('currency')

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
    get=extend_schema(
        tags=['listings'],
        summary='Каталог объявлений (розница)',
        description='Возвращает только retail-листинги. Wholesale скрыт.',
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
        user = self.request.user
        is_dealer = user.is_authenticated and (user.is_verified_dealer or user.role == 'admin')
        qs = _base_queryset() if is_dealer else _base_queryset().filter(channel=Listing.Channel.RETAIL)
        return _apply_filters(qs, self.request.query_params)


@extend_schema_view(
    get=extend_schema(tags=['listings'], summary='Детали объявления'),
)
class ListingDetailView(generics.RetrieveAPIView):
    serializer_class = ListingSerializer

    def get_queryset(self):
        qs = _base_queryset()
        user = self.request.user
        # Wholesale только для дилеров/админов
        if not (user.is_authenticated and (user.is_verified_dealer or user.role == 'admin')):
            qs = qs.filter(channel=Listing.Channel.RETAIL)
        return qs


@extend_schema_view(
    post=extend_schema(tags=['listings'], summary='Создать объявление', description='Требует авторизации.'),
)
class ListingCreateView(generics.CreateAPIView):
    serializer_class = ListingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]


@extend_schema_view(
    get=extend_schema(
        tags=['b2b'],
        summary='B2B-доска опта',
        description='Только для верифицированных перекупщиков (is_verified_dealer=true). '
                    'Возвращает wholesale-листинги, срочные выкупы вверху.',
    ),
)
class B2BBoardView(generics.ListAPIView):
    serializer_class = ListingSerializer
    permission_classes = [IsVerifiedDealerOrAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['vehicle__make', 'vehicle__model', 'vehicle__vin']
    ordering_fields = ['price', 'created_at', 'is_express_buyout']
    ordering = ['-is_express_buyout', '-created_at']

    def get_queryset(self):
        qs = _base_queryset().filter(channel=Listing.Channel.WHOLESALE)
        return _apply_filters(qs, self.request.query_params)
