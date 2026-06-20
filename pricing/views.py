from datetime import date

from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .calculator import (
    AuctionFeeBreakdown,
    LandedCostInputs,
    build_rate_snapshot_from_db,
    calc_auction_fees,
    calculate_landed_cost,
    rate_snapshot_to_dict,
    ZERO,
)
from .models import (
    AuctionFeeTier, AuctionFixedFee, Calculation, CustomsExciseRate,
    EuToUaDeliveryRate, ExchangeRate, OceanFreightRate,
    PensionFundBracket, UsLandRoute,
)
from .serializers import CalculateInputSerializer, CalculationSerializer

# Дефолтный тип участника для наших расчётов (broker — основной режим работы)
DEFAULT_MEMBER_TYPE = 'broker'


def _active_on(qs, on_date=None):
    on_date = on_date or date.today()
    return qs.filter(valid_from__lte=on_date).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)
    )


def _lookup_tier(auction, bid, member_type, payment_type, title_type, on_date):
    """
    Ищет подходящий AuctionFeeTier.
    Приоритет: точный title_type → 'any'.
    """
    base_qs = _active_on(
        AuctionFeeTier.objects.filter(
            auction=auction,
            member_type=member_type,
            payment_type=payment_type,
            bid_min__lte=bid,
        ).filter(
            Q(bid_max__isnull=True) | Q(bid_max__gte=bid)
        ),
        on_date,
    ).order_by('bid_min')

    return (
        base_qs.filter(title_type=title_type).first()
        or base_qs.filter(title_type='any').first()
    )


def _lookup_fixed_fees(auction, title_type, on_date):
    """Возвращает применимые фиксированные сборы: gate по title_type + env + virtual_bid."""
    active = _active_on(AuctionFixedFee.objects.filter(auction=auction), on_date)
    gate = active.filter(fee_type='gate').filter(
        Q(title_type=title_type) | Q(title_type='any')
    )
    others = active.filter(fee_type__in=['environmental', 'virtual_bid'])
    return list(gate) + list(others)


@extend_schema(
    tags=['pricing'],
    summary='Калькулятор стоимости «под ключ»',
    description=(
        'Рассчитывает полную стоимость автомобиля в Украине: '
        'аукционный сбор (buyer fee + gate + environmental + virtual bid), '
        'логистика США, морской фрахт, доставка ЕС→UA, растаможка.\n\n'
        '**Важно**: результат всегда `is_estimate: true`. '
        'Ставки аукционных сборов — baseline (сверить с тарифом брокера). '
        'Ставки акциза и пенсионного сбора — требуют проверки по законодательству.'
    ),
    request=CalculateInputSerializer,
    responses={
        201: OpenApiResponse(description='Расчёт выполнен, снимок сохранён'),
        400: OpenApiResponse(description='Ошибка валидации входных данных'),
        422: OpenApiResponse(description='Отсутствуют активные тарифы в БД'),
    },
    examples=[
        OpenApiExample(
            'Toyota Camry 2019 бензин 2500cc $10 000 (broker/secured/salvage)',
            value={
                'auction_price_usd': '10000.00',
                'engine_cc': 2500,
                'fuel_type': 'petrol',
                'vehicle_year': 2019,
                'auction': 'copart',
                'member_type': 'broker',
                'payment_type': 'secured',
                'title_type': 'salvage',
                'auction_location': 'general',
                'us_port': 'houston',
                'eu_port': 'klaipeda',
            },
            request_only=True,
        ),
        OpenApiExample(
            'Tesla Model 3 2022 электро $25 000',
            value={
                'auction_price_usd': '25000.00',
                'engine_cc': 1,
                'fuel_type': 'electric',
                'vehicle_year': 2022,
                'auction': 'copart',
                'member_type': 'broker',
                'payment_type': 'secured',
                'title_type': 'salvage',
                'auction_location': 'california',
                'us_port': 'houston',
                'eu_port': 'gdansk',
            },
            request_only=True,
        ),
    ],
)
class CalculateView(APIView):
    def post(self, request):
        serializer = CalculateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        today = date.today()
        calc_date = data.get('calculation_date') or today

        # Параметры аукционного сбора
        member_type = data.get('member_type', DEFAULT_MEMBER_TYPE)
        payment_type = data.get('payment_type', 'secured')
        title_type = data.get('title_type', 'salvage')
        auction_price = data['auction_price_usd']

        try:
            tier = _lookup_tier(
                auction=data['auction'],
                bid=auction_price,
                member_type=member_type,
                payment_type=payment_type,
                title_type=title_type,
                on_date=calc_date,
            )

            fixed_fees = _lookup_fixed_fees(
                auction=data['auction'],
                title_type=title_type,
                on_date=calc_date,
            )

            us_land = _active_on(
                UsLandRoute.objects.filter(
                    auction_location__iexact=data['auction_location'],
                    us_port__iexact=data['us_port'],
                ),
                calc_date,
            ).first()

            ocean = _active_on(
                OceanFreightRate.objects.filter(
                    us_port__iexact=data['us_port'],
                    eu_port=data['eu_port'],
                ),
                calc_date,
            ).first()

            eu_to_ua = _active_on(
                EuToUaDeliveryRate.objects.filter(eu_port=data['eu_port']),
                calc_date,
            ).first()

            # Курс НБУ на дату оформления. Если нет — берём ближайший предыдущий.
            usd_to_uah = (
                ExchangeRate.objects.filter(from_currency='USD', to_currency='UAH', date=calc_date).first()
                or ExchangeRate.objects.filter(from_currency='USD', to_currency='UAH').order_by('-date').first()
            )

            usd_to_eur = (
                ExchangeRate.objects.filter(from_currency='USD', to_currency='EUR', date=calc_date).first()
                or ExchangeRate.objects.filter(from_currency='USD', to_currency='EUR').order_by('-date').first()
            )

            excise_rate = _active_on(
                CustomsExciseRate.objects.filter(
                    fuel_type=data['fuel_type'],
                    engine_cc_min__lte=data['engine_cc'],
                ).filter(
                    Q(engine_cc_max__isnull=True) | Q(engine_cc_max__gte=data['engine_cc'])
                ),
                calc_date,
            ).order_by('-engine_cc_min').first()

            approx_uah = data['auction_price_usd'] * usd_to_uah.rate if usd_to_uah else None
            pension_bracket = None
            if approx_uah:
                pension_bracket = _active_on(
                    PensionFundBracket.objects.filter(min_value_uah__lte=approx_uah).filter(
                        Q(max_value_uah__isnull=True) | Q(max_value_uah__gte=approx_uah)
                    ),
                    calc_date,
                ).order_by('-min_value_uah').first()

            missing = []
            if not tier:
                missing.append(
                    f'AuctionFeeTier для {data["auction"]} / {member_type}/{payment_type}/{title_type} / ${auction_price}'
                )
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

        # Рассчитываем аукционный сбор (чистая функция калькулятора)
        fee_breakdown = calc_auction_fees(
            bid=auction_price,
            tier=tier,
            fixed_fees=fixed_fees,
        )

        rates = build_rate_snapshot_from_db(
            auction_fee_breakdown=fee_breakdown,
            us_land_route=us_land,
            ocean_freight=ocean,
            eu_to_ua=eu_to_ua,
            usd_to_uah_rate=usd_to_uah,
            usd_to_eur_rate=usd_to_eur,
            excise_rate=excise_rate,
            vehicle_year=data['vehicle_year'],
            calculation_year=calc_date.year,
            pension_rate=pension_bracket,
            rates_date=str(calc_date),
            meta={
                'auction_fee_tier_id': tier.pk,
                'fixed_fee_ids': [f.pk for f in fixed_fees],
                'us_land_route_id': us_land.pk,
                'ocean_freight_id': ocean.pk,
                'eu_to_ua_id': eu_to_ua.pk,
                'usd_to_uah_rate_id': usd_to_uah.pk,
                'usd_to_eur_rate_id': usd_to_eur.pk,
                'excise_rate_id': excise_rate.pk,
                'pension_bracket_id': pension_bracket.pk,
            },
        )

        inputs = LandedCostInputs(
            auction_price_usd=data['auction_price_usd'],
            engine_cc=data['engine_cc'],
            fuel_type=data['fuel_type'],
            vehicle_year=data['vehicle_year'],
            calculation_year=calc_date.year,
            battery_capacity_kwh=data.get('battery_capacity_kwh', 0),
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
                'rates_validity_date': str(calc_date),
                'exchange_rate_date': str(usd_to_uah.date),
                'warning': (
                    'Розрахунок є орієнтовним. '
                    'Ставки аукціонних зборів — baseline (звірити з тарифом брокера). '
                    'Ставки акцизу актуальні на янв–чер 2026; фінальний розрахунок підтверджує митний брокер.'
                ),
                'breakdown': breakdown,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=['pricing'],
    summary='Активные тарифы',
    description='Возвращает все тарифы, действующие на сегодняшний день.',
    responses={
        200: inline_serializer(
            name='ActiveRatesResponse',
            fields={
                'auction_fee_tiers': drf_serializers.ListField(),
                'auction_fixed_fees': drf_serializers.ListField(),
                'us_land_routes': drf_serializers.ListField(),
                'ocean_freight': drf_serializers.ListField(),
                'eu_to_ua': drf_serializers.ListField(),
                'exchange_rates': drf_serializers.ListField(),
                'excise_rates': drf_serializers.ListField(),
                'pension_brackets': drf_serializers.ListField(),
            },
        )
    },
)
class ActiveRatesView(APIView):
    # noinspection PyMethodMayBeStatic
    def get(self, request):
        today = date.today()

        def active(qs):
            return qs.filter(valid_from__lte=today).filter(
                Q(valid_to__isnull=True) | Q(valid_to__gte=today)
            )

        return Response({
            'auction_fee_tiers': list(
                active(AuctionFeeTier.objects.all()).values(
                    'id', 'auction', 'member_type', 'payment_type', 'title_type',
                    'bid_min', 'bid_max', 'fee_flat', 'fee_percent',
                )
            ),
            'auction_fixed_fees': list(
                active(AuctionFixedFee.objects.all()).values(
                    'id', 'auction', 'fee_type', 'title_type', 'amount',
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
