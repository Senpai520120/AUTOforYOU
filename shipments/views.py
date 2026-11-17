from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, generics, permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from core.uploads import private_file_response
from users.authentication import CookieJWTAuthentication

from .models import Shipment, TrackingEvent
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
    if user.is_admin_role:
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


@extend_schema(
    tags=['shipments'],
    summary='Фото події трекінгу (приватне)',
    description=(
        'Файл фото з приватного сховища. Доступ: хто відстежує контейнер, адміністратор, '
        'або співробітник з правом перегляду подій трекінгу в адмінці. Чужим — 404.'
    ),
    responses={(200, 'image/*'): OpenApiTypes.BINARY},
    # Сесія Django (адмінка) у схемі не описується: інакше конфлікт імен cookieAuth.
    auth=[{'jwtAuth': []}, {'cookieAuth': []}],
)
class TrackingEventPhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    # JWT першим: для аноніма 401 з WWW-Authenticate. Сесія Django — для мініатюр в адмінці
    # (тільки GET, тож CSRF не потрібен).
    authentication_classes = [CookieJWTAuthentication, SessionAuthentication]

    def get(self, request, pk, event_id):
        user = request.user
        if user.has_perm('shipments.view_trackingevent'):
            events = TrackingEvent.objects.all()
        else:
            events = TrackingEvent.objects.filter(shipment__in=_visible_to(user))
        event = get_object_or_404(events, pk=event_id, shipment_id=pk)
        if not event.photo:
            raise Http404
        return private_file_response(event.photo)
