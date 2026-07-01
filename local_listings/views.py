from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.models import VinReport
from integrations.providers import NHTSAVinDecodeProvider
from .filters import LocalListingFilter
from .models import LocalListing, Region, City
from .serializers import (
    LocalListingListSerializer,
    LocalListingDetailSerializer,
    LocalListingCreateSerializer,
    LocalListingUpdateSerializer,
    LocalListingOwnerSerializer,
    RegionSerializer,
    CitySerializer,
)


def _base_queryset():
    return LocalListing.objects.select_related('owner', 'region', 'city').prefetch_related('images')


class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.owner == request.user or request.user.is_staff


@extend_schema_view(
    get=extend_schema(
        tags=['local'],
        summary='Каталог Україна — список активних оголошень',
        parameters=[
            OpenApiParameter('make', OpenApiTypes.STR),
            OpenApiParameter('model', OpenApiTypes.STR),
            OpenApiParameter('year_min', OpenApiTypes.INT),
            OpenApiParameter('year_max', OpenApiTypes.INT),
            OpenApiParameter('price_min', OpenApiTypes.NUMBER),
            OpenApiParameter('price_max', OpenApiTypes.NUMBER),
            OpenApiParameter('fuel_type', OpenApiTypes.STR),
            OpenApiParameter('transmission', OpenApiTypes.STR),
            OpenApiParameter('body_type', OpenApiTypes.STR),
            OpenApiParameter('region', OpenApiTypes.INT),
            OpenApiParameter('city', OpenApiTypes.INT),
            OpenApiParameter('mileage_max', OpenApiTypes.INT),
            OpenApiParameter('search', OpenApiTypes.STR),
            OpenApiParameter('ordering', OpenApiTypes.STR,
                             description='-created_at | created_at | price | -price'),
        ],
    ),
    post=extend_schema(
        tags=['local'],
        summary='Подати місцеве оголошення (авторизований)',
        description='Нове оголошення отримує статус pending і проходить модерацію.',
    ),
)
class LocalListingListCreateView(generics.ListCreateAPIView):
    filter_backends = [LocalListingFilter]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return LocalListingCreateSerializer
        return LocalListingListSerializer

    def get_queryset(self):
        return _base_queryset().filter(status=LocalListing.Status.ACTIVE)


@extend_schema_view(
    get=extend_schema(tags=['local'], summary='Деталі місцевого оголошення'),
    patch=extend_schema(tags=['local'], summary='Редагувати своє оголошення'),
    delete=extend_schema(tags=['local'], summary='Видалити своє оголошення'),
)
class LocalListingDetailView(generics.RetrieveUpdateDestroyAPIView):
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrAdmin]

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return LocalListingUpdateSerializer
        return LocalListingDetailSerializer

    def get_queryset(self):
        return _base_queryset()

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if obj.owner != request.user and not request.user.is_staff:
                self.permission_denied(
                    request,
                    message='Тільки власник може редагувати оголошення.',
                    code=403,
                )


@extend_schema(
    tags=['local'],
    summary='Мої оголошення (усі статуси)',
    description='Повертає всі оголошення поточного авторизованого користувача, включаючи pending та rejected.',
)
class MyListingsView(generics.ListAPIView):
    serializer_class = LocalListingOwnerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _base_queryset().filter(owner=self.request.user).order_by('-created_at')


@extend_schema_view(
    get=extend_schema(
        tags=['local'],
        summary='VIN-автозаповнення (NHTSA vPIC)',
        description='Безкоштовно, без ключа. Повертає make/model/year/engine_cc/fuel_type з кешу або NHTSA.',
    ),
)
class VinPrefillView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, vin: str):
        vin = vin.upper()
        if len(vin) != 17:
            return Response({'error': 'VIN має бути 17 символів.'}, status=status.HTTP_400_BAD_REQUEST)

        cached = VinReport.objects.filter(vin=vin, provider='nhtsa_vpic').first()
        if cached:
            return Response({**cached.report_data, 'cached': True})

        provider = NHTSAVinDecodeProvider()
        data = provider.decode(vin)

        if 'error' not in data:
            VinReport.objects.get_or_create(
                vin=vin,
                provider='nhtsa_vpic',
                defaults={'report_data': data, 'demo': False},
            )

        return Response({**data, 'cached': False})


@extend_schema(tags=['local'], summary='Список областей України')
class RegionListView(generics.ListAPIView):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


@extend_schema(tags=['local'], summary='Міста за областю')
class CityListView(generics.ListAPIView):
    serializer_class = CitySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        region_id = self.kwargs.get('region_id')
        return City.objects.filter(region_id=region_id).select_related('region')
