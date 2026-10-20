from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, generics
from rest_framework.permissions import AllowAny

from .models import Vehicle
from .serializers import VehicleSerializer


def visible_vehicles(user):
    """04-S2 / 13-S5: VIN и лот видны только там, где авто видно в каталоге.

    Гость и buyer - авто с retail-листингом; verified dealer (и admin) при B2B - ещё wholesale;
    admin-роль - всё. Авто без листинга и в контейнерах без retail-листинга посторонним не видны.
    """
    from listings.models import Listing
    from listings.permissions import can_view_wholesale

    qs = Vehicle.objects.prefetch_related('images')
    if user and user.is_authenticated and user.is_admin_role:
        return qs.all()
    channels = [Listing.Channel.RETAIL]
    if can_view_wholesale(user):
        channels.append(Listing.Channel.WHOLESALE)
    return qs.filter(listings__channel__in=channels).distinct()


@extend_schema_view(
    get=extend_schema(tags=['vehicles'], summary='Список автомобилей', description='Поиск по make, model, vin.'),
)
class VehicleListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = VehicleSerializer

    def get_queryset(self):
        return visible_vehicles(self.request.user).order_by('-pk')
    filter_backends = [filters.SearchFilter]
    search_fields = ['make', 'model', 'vin']


@extend_schema_view(
    get=extend_schema(tags=['vehicles'], summary='Детали автомобиля'),
)
class VehicleDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = VehicleSerializer

    def get_queryset(self):
        return visible_vehicles(self.request.user)
