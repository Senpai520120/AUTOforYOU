import json
from datetime import date

from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .calculator import (
    LandedCostInputs,
    build_rate_snapshot_from_db,
    calculate_landed_cost,
    rate_snapshot_to_dict,
)
from .models import (
    AuctionFeeTier, Calculation, CustomsExciseRate,
    EuToUaDeliveryRate, ExchangeRate, OceanFreightRate,
    PensionFundBracket, UsLandRoute,
)
from .serializers import CalculateInputSerializer, CalculationSerializer


def _active_on(qs, on_date=None):
    on_date = on_date or date.today()
    return qs.filter(valid_from__lte=on_date).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)
    )


class CalculateView(APIView):
    """
    POST /api/v1/pricing/calculate/

    Принимает параметры авто и логистики → возвращает детализацию стоимости «под ключ».
    Сохраняет снимок расчёта в Calculation. Результат всегда помечен is_estimate=true.
    """

    def post(self, request):
        serializer = CalculateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        today = date.today()

        # Получаем активные тарифы из БД
        try:
            auction_fee = _active_on(
                AuctionFeeTier.objects.filter(
                    auction=data['auction'],
                    min_price_usd__lte=data['auction_price_usd'],
                ).filter(
                    Q(max_price_usd__isnull=True) | Q(max_price_usd__gte=data['auction_price_usd'])
                )
            ).order_by('min_price_usd').first()

            us_land = _active_on(
                UsLandRoute.objects.filter(
                    auction_location__iexact=data['auction_location'],
                    us_port__iexact=data['us_port'],
                )
            ).first()

            ocean = _active_on(
                OceanFreightRate.objects.filter(
                    us_port__iexact=data['us_port'],
                    eu_port=data['eu_port'],
                )
            ).first()

            eu_to_ua = _active_on(
                EuToUaDeliveryRate.objects.filter(eu_port=data['eu_port'])
            ).first()

            usd_to_uah = ExchangeRate.objects.filter(
                from_currency='USD', to_currency='UAH'
            ).order_by('-date').first()

            usd_to_eur = ExchangeRate.objects.filter(
                from_currency='USD', to_currency='EUR'
            ).order_by('-date').first()

            excise_rate = _active_on(
                CustomsExciseRate.objects.filter(fuel_type=data['fuel_type'])
            ).first()

            # Определяем пенсионный брекет по ориентировочной стоимости авто в UAH
            # (используем auction_price * usd_to_uah как грубую оценку)
            approx_uah = data['auction_price_usd'] * usd_to_uah.rate if usd_to_uah else None
            pension_bracket = None
            if approx_uah:
                pension_bracket = _active_on(
                    PensionFundBracket.objects.filter(min_value_uah__lte=approx_uah).filter(
                        Q(max_value_uah__isnull=True) | Q(max_value_uah__gte=approx_uah)
                    )
                ).order_by('-min_value_uah').first()

            missing = []
            if not auction_fee:
                missing.append(f'AuctionFeeTier для {data["auction"]} / ${data["auction_price_usd"]}')
            if not us_land:
                missing.append(f'UsLandRoute для {data["auction_location"]} → {data["us_port"]}')
            if not ocean:
                missing.append(f'OceanFreightRate для {data["us_port"]} → {data["eu_port"]}')
            if not eu_to_ua:
                missing.append(f'EuToUaDeliveryRate для {data["eu_port"]}')
            if not usd_to_uah:
                missing.append('ExchangeRate USD→UAH')
            if not usd_to_eur:
                missing.append('ExchangeRate USD→EUR')
            if not excise_rate:
                missing.append(f'CustomsExciseRate для {data["fuel_type"]}')
            if not pension_bracket:
                missing.append('PensionFundBracket')

            if missing:
                return Response(
                    {'error': 'Отсутствуют активные тарифы в БД', 'missing': missing},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Строим снимок ставок и считаем
        rates = build_rate_snapshot_from_db(
            auction_fee_tier=auction_fee,
            us_land_route=us_land,
            ocean_freight=ocean,
            eu_to_ua=eu_to_ua,
            usd_to_uah_rate=usd_to_uah,
            usd_to_eur_rate=usd_to_eur,
            excise_rate=excise_rate,
            vehicle_year=data['vehicle_year'],
            calculation_year=today.year,
            pension_rate=pension_bracket,
        )

        inputs = LandedCostInputs(
            auction_price_usd=data['auction_price_usd'],
            engine_cc=data['engine_cc'],
            fuel_type=data['fuel_type'],
            vehicle_year=data['vehicle_year'],
            calculation_year=today.year,
        )

        result = calculate_landed_cost(inputs, rates)
        breakdown = result.to_dict()
        rates_dict = rate_snapshot_to_dict(rates)
        inputs_dict = {k: str(v) if hasattr(v, '__str__') else v for k, v in data.items()}

        calc = Calculation.objects.create(
            user=request.user if request.user.is_authenticated else None,
            inputs_snapshot=inputs_dict,
            rates_snapshot=rates_dict,
            breakdown=breakdown,
            total_usd=result.total_usd,
            total_uah=result.total_uah,
            is_estimate=True,
        )

        return Response(
            {
                'calculation_id': calc.pk,
                'is_estimate': True,
                'warning': 'Розрахунок є орієнтовним. Ставки акцизу та пенсійного збору потребують перевірки за чинним законодавством України.',
                'breakdown': breakdown,
            },
            status=status.HTTP_201_CREATED,
        )


class ActiveRatesView(APIView):
    """GET /api/v1/pricing/rates/ — текущие активные тарифы."""

    def get(self, request):
        today = date.today()

        def active(qs):
            return qs.filter(valid_from__lte=today).filter(
                Q(valid_to__isnull=True) | Q(valid_to__gte=today)
            )

        return Response({
            'auction_fees': list(
                active(AuctionFeeTier.objects.all()).values(
                    'id', 'auction', 'min_price_usd', 'max_price_usd', 'fee_fixed_usd', 'fee_pct'
                )
            ),
            'us_land_routes': list(
                active(UsLandRoute.objects.all()).values('id', 'auction_location', 'us_port', 'cost_usd')
            ),
            'ocean_freight': list(
                active(OceanFreightRate.objects.all()).values('id', 'us_port', 'eu_port', 'cost_usd')
            ),
            'eu_to_ua': list(
                active(EuToUaDeliveryRate.objects.all()).values('id', 'eu_port', 'cost_usd')
            ),
            'exchange_rates': list(
                ExchangeRate.objects.order_by('-date').values('from_currency', 'to_currency', 'rate', 'date')[:10]
            ),
            'excise_rates': list(
                active(CustomsExciseRate.objects.all()).values(
                    'id', 'fuel_type', 'eur_per_100cc', 'duty_rate', 'vat_rate'
                )
            ),
            'pension_brackets': list(
                active(PensionFundBracket.objects.all()).values(
                    'id', 'min_value_uah', 'max_value_uah', 'rate'
                )
            ),
        })
