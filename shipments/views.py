from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, generics, permissions

from .models import Shipment
from .serializers import ShipmentListSerializer, ShipmentSerializer


def _visible_to(user):
    """
    Контейнери, які користувач має право бачити.

    Раніше обидві в'ю були без permission_classes, тобто AllowAny за дефолтом
    з settings, а ShipmentSerializer вкладає VehicleSerializer з полем vin —
    номери кузовів віддавалися анониму. При цьому в моделі є M2M watchers і
    приватна MyShipmentsView з фільтром по ньому: контроль доступу задумувався,
    але публічна в'ю його ігнорувала.
    """
    if user.is_staff:
        return Shipment.objects.all()
    return Shipment.objects.filter(watchers=user)


@extend_schema_view(
    get=extend_schema(
        tags=['shipments'],
        summary='Список контейнерів',
        description='Повертає контейнери, які відстежує поточний користувач. Адміністратор бачить усі.',
    ),
)
class ShipmentListView(generics.ListAPIView):
    serializer_class = ShipmentListSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['container_no', 'vessel']

    def get_queryset(self):
        qs = _visible_to(self.request.user).prefetch_related('vehicles')
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs.distinct()


@extend_schema_view(
    get=extend_schema(
        tags=['shipments'],
        summary='Деталі контейнера + історія подій',
        description='Доступно лише тим, хто відстежує контейнер, і адміністраторам.',
    ),
)
class ShipmentDetailView(generics.RetrieveAPIView):
    serializer_class = ShipmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return _visible_to(self.request.user).prefetch_related('vehicles__images', 'events').distinct()
