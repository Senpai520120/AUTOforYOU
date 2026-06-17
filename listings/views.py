from rest_framework import generics, filters, permissions
from .models import Listing
from .serializers import ListingSerializer, ListingCreateSerializer


class ListingListView(generics.ListAPIView):
    """
    GET /api/v1/listings/
    Фильтры: status, channel, currency, vehicle__fuel_type, max_price
    """
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


class ListingDetailView(generics.RetrieveAPIView):
    queryset = Listing.objects.select_related('vehicle', 'seller').prefetch_related('vehicle__images')
    serializer_class = ListingSerializer


class ListingCreateView(generics.CreateAPIView):
    serializer_class = ListingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]
