from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics
from .models import Car
from .serializers import CarSerializer


@extend_schema(
    tags=['legacy'],
    summary='[УСТАРЕЛО] Калькулятор растаможки',
    description='Устаревший эндпоинт. Используйте POST /api/v1/pricing/calculate/ вместо него.',
    deprecated=True,
    responses={200: inline_serializer(
        name='LegacyCalcResponse',
        fields={
            'auction_fee': drf_serializers.FloatField(),
            'delivery_to_ukraine': drf_serializers.FloatField(),
            'customs_total': drf_serializers.FloatField(),
            'total_cost': drf_serializers.FloatField(),
        },
    )},
)
class CustomsCalculatorView(APIView):
    def get(self, request):
        try:
            price = float(request.query_params.get('price', 0))
            engine = int(request.query_params.get('engine', 2000))
            age = int(request.query_params.get('age', 5))
            is_diesel = request.query_params.get('diesel', 'false').lower() == 'true'

            auction_fee = price * 0.10 if price > 5000 else 600.0
            delivery = 2200.0

            base_rate = 75.0 if is_diesel else 50.0
            age_coeff = 1 if age == 0 else (15 if age > 15 else age)
            excise = (base_rate * (engine / 1000.0) * age_coeff) * 1.1

            duty = price * 0.10
            vat = (price + auction_fee + duty + excise) * 0.20
            customs_total = duty + excise + vat

            total_cost = price + auction_fee + delivery + customs_total

            return Response({
                "auction_fee": round(auction_fee, 2),
                "delivery_to_ukraine": round(delivery, 2),
                "customs_total": round(customs_total, 2),
                "total_cost": round(total_cost, 2)
            })
        except ValueError:
            return Response({"error": "Переданы некорректные параметры"}, status=400)


@extend_schema(tags=['legacy'], summary='[УСТАРЕЛО] Список Car', deprecated=True)
class CarListView(generics.ListAPIView):
    serializer_class = CarSerializer

    def get_queryset(self):
        queryset = Car.objects.all().prefetch_related('images')
        status = self.request.query_params.get('status')
        max_price = self.request.query_params.get('max_price')

        if status:
            queryset = queryset.filter(status=status)
        if max_price:
            queryset = queryset.filter(total_price__lte=max_price)

        return queryset
