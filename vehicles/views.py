from django.db.models import Exists, OuterRef
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, generics
from rest_framework.permissions import AllowAny

from core.modules import module_enabled
from listings.models import Listing
from listings.permissions import can_view_wholesale

from .models import Vehicle
from .serializers import VehicleSerializer


def visible_vehicles(user):
    """Авто, которые можно показать пользователю (04-S2, 13-S5).

    Аноним, buyer, broker, moderator: только авто с retail-листингом.
    Верифицированный дилер: ещё и с wholesale-листингом (при B2B_ENABLED).
    Админ (role=admin или superuser): всё, включая авто без листинга и в контейнерах.
    VIN и номер лота раскрываются только там, где авто и так видно в каталоге.
    """
    qs = Vehicle.objects.prefetch_related('images')
    if user.is_authenticated and user.is_admin_role:
        return qs
    channels = [Listing.Channel.RETAIL]
    if module_enabled('b2b') and can_view_wholesale(user):
        channels.append(Listing.Channel.WHOLESALE)
    listed = Listing.objects.filter(vehicle=OuterRef('pk'), channel__in=channels)
    return qs.filter(Exists(listed))


@extend_schema_view(
    get=extend_schema(tags=['vehicles'], summary='Список автомобилей', description='Поиск по make, model, vin.'),
)
class VehicleListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = VehicleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['make', 'model', 'vin']

    def get_queryset(self):
        return visible_vehicles(self.request.user)


@extend_schema_view(
    get=extend_schema(tags=['vehicles'], summary='Детали автомобиля'),
)
class VehicleDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = VehicleSerializer

    def get_queryset(self):
        return visible_vehicles(self.request.user)
