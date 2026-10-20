import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import cache as pricing_cache
from .calculator import (
    LandedCostInputs,
    MissingRate,
    build_rate_snapshot_from_db,
    calc_auction_fees,
    calculate_landed_cost,
    rate_snapshot_to_dict,
    select_rates,
)
from .models import (
    AuctionFeeTier,
    AuctionFixedFee,
    Calculation,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UsLandRoute,
)
from .serializers import CalculateInputSerializer

logger = logging.getLogger(__name__)

DEFAULT_MEMBER_TYPE = getattr(settings, 'AUCTION_DEFAULT_MEMBER_TYPE', 'broker')


def _active_on(qs, on_date=None):
    """Вспомогательный ORM-фильтр (используется в ActiveRatesView)."""
    on_date = on_date or date.today()
    return qs.filter(valid_from__lte=on_date).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)
    )


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
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = CalculateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        calc_date = data.get('calculation_date') or date.today()
        params = {
            **data,
            'member_type': data.get('member_type', DEFAULT_MEMBER_TYPE),
            'payment_type': data.get('payment_type', 'secured'),
            'title_type': data.get('title_type', 'salvage'),
        }

        # Подбор тарифов - чистая функция калькулятора (02-Q6); view только загружает каталог.
        try:
            selected = select_rates(pricing_cache.get_catalog(), params, calc_date)
        except Exception as exc:
            logger.exception('Помилка підготовки тарифів калькулятора: %s', type(exc).__name__)
            return Response(
                {'error': 'Не вдалося виконати розрахунок. Спробуйте пізніше.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if selected.missing:
            return _missing_response(selected.missing)

        fee_breakdown = calc_auction_fees(bid=data['auction_price_usd'], tier=selected.tier,
                                          fixed_fees=selected.fixed_fees)
        rates = build_rate_snapshot_from_db(
            auction_fee_breakdown=fee_breakdown,
            us_land_route=selected.us_land,
            ocean_freight=selected.ocean,
            eu_to_ua=selected.eu_to_ua,
            usd_to_uah_rate=selected.usd_to_uah,
            usd_to_eur_rate=selected.usd_to_eur,
            excise_rate=selected.excise,
            vehicle_year=data['vehicle_year'],
            calculation_year=calc_date.year,
            rates_date=calc_date.isoformat(),
            rule=selected.rule,
            on_date=calc_date,
            meta={
                'auction_fee_tier_id': selected.tier.pk,
                'fixed_fee_ids': [f.pk for f in selected.fixed_fees],
                'us_land_route_id': selected.us_land.pk,
                'ocean_freight_id': selected.ocean.pk,
                'eu_to_ua_id': selected.eu_to_ua.pk,
                'usd_to_uah_rate_id': selected.usd_to_uah.pk,
                'usd_to_eur_rate_id': selected.usd_to_eur.pk,
                'excise_rate_id': selected.excise.pk,
                'customs_calc_rule_id': selected.rule.pk,
            },
        )
        inputs = LandedCostInputs(
            auction_price_usd=data['auction_price_usd'],
            engine_cc=data['engine_cc'],
            fuel_type=data['fuel_type'],
            vehicle_year=data['vehicle_year'],
            calculation_year=calc_date.year,
            battery_capacity_kwh=data.get('battery_capacity_kwh') or Decimal('0'),
        )
        try:
            result = calculate_landed_cost(inputs, rates, selected.pension_brackets, selected.rule)
        except MissingRate as exc:
            return _missing_response([str(exc)])
        except Exception as exc:  # например, правило с неизвестной базой, записанное в обход админки
            logger.exception('Помилка розрахунку калькулятора: %s', type(exc).__name__)
            return Response(
                {'error': 'Не вдалося виконати розрахунок. Спробуйте пізніше.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        breakdown = result.to_dict()
        rates_dict = rate_snapshot_to_dict(rates)
        updated_on = selected.rates_updated_on
        rates_dict['rates_updated_on'] = updated_on.isoformat() if updated_on else None

        calc = Calculation.objects.create(
            user=request.user if request.user.is_authenticated else None,
            inputs_snapshot=_inputs_snapshot(data),
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
                # Q5: пока брокер не подтвердил правило - интерфейс показывает «орієнтовний розрахунок».
                'rules_confirmed': bool(selected.rule.confirmed_by_broker),
                'rates_validity_date': calc_date.isoformat(),
                'rates_updated_on': updated_on.isoformat() if updated_on else None,
                'exchange_rate_date': selected.usd_to_uah.date.isoformat(),
                'warning': (
                    'Розрахунок є орієнтовним. '
                    'Ставки аукціонних зборів — baseline (звірити з тарифом брокера). '
                    'Фінальний розрахунок підтверджує митний брокер.'
                ),
                'breakdown': breakdown,
            },
            status=status.HTTP_201_CREATED,
        )


def _missing_response(missing):
    return Response(
        {'error': 'Отсутствуют активные тарифы в БД', 'missing': missing},
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _inputs_snapshot(data) -> dict:
    """Снимок входов (02-Q9): Decimal - строкой, даты - ISO, None остаётся None."""
    def conv(value):
        if value is None or isinstance(value, (bool, int, str)):
            return value
        return str(value)  # Decimal -> '5000.00', date -> ISO 'YYYY-MM-DD'
    return {k: conv(v) for k, v in data.items()}


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
    permission_classes = [AllowAny]
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
