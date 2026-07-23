from datetime import date

from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .calculator import (
    LandedCostInputs,
    build_rate_snapshot_from_db,
    calc_auction_fees,
    calculate_landed_cost,
    rate_snapshot_to_dict,
)
from .models import (
    AuctionFeeTier, AuctionFixedFee, Calculation, CustomsExciseRate,
    EuToUaDeliveryRate, ExchangeRate, OceanFreightRate,
    PensionFundBracket, UsLandRoute,
)
from .serializers import CalculateInputSerializer
from . import cache as pricing_cache

DEFAULT_MEMBER_TYPE = getattr(settings, 'AUCTION_DEFAULT_MEMBER_TYPE', 'broker')


def _is_active(obj, on_date):
    """True, если запись активна на дату on_date."""
    return obj.valid_from <= on_date and (obj.valid_to is None or obj.valid_to >= on_date)


def _active_on(qs, on_date=None):
    """Вспомогательный ORM-фильтр (используется в ActiveRatesView)."""
    on_date = on_date or date.today()
    return qs.filter(valid_from__lte=on_date).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=on_date)
    )


def _lookup_tier(auction, bid, member_type, payment_type, title_type, on_date):
    """
    Ищет AuctionFeeTier в кэше (in-memory фильтрация).
    Приоритет: точный title_type → 'any'.
    """
    all_tiers = pricing_cache.get_auction_fee_tiers()

    candidates = sorted(
        [
            t for t in all_tiers
            if (
                t.auction == auction
                and t.member_type == member_type
                and t.payment_type == payment_type
                and t.bid_min <= bid
                and (t.bid_max is None or t.bid_max >= bid)
                and _is_active(t, on_date)
            )
        ],
        key=lambda t: t.bid_min,
    )

    return (
        next((t for t in candidates if t.title_type == title_type), None)
        or next((t for t in candidates if t.title_type == 'any'), None)
    )


def _lookup_fixed_fees(auction, title_type, on_date):
    """Возвращает применимые фиксированные сборы из кэша."""
    all_fees = pricing_cache.get_auction_fixed_fees()
    result = []
    for f in all_fees:
        if not (f.auction == auction and _is_active(f, on_date)):
            continue
        if f.fee_type == 'gate' and f.title_type in (title_type, 'any'):
            result.append(f)
        elif f.fee_type in ('environmental', 'virtual_bid'):
            result.append(f)
    return result


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

            loc = data['auction_location'].lower()
            us_p = data['us_port'].lower()
            eu_p = data['eu_port']

            us_land = next(
                (r for r in sorted(pricing_cache.get_us_land_routes(), key=lambda x: x.valid_from)
                 if r.auction_location.lower() == loc
                 and r.us_port.lower() == us_p
                 and _is_active(r, calc_date)),
                None,
            )

            ocean = next(
                (r for r in pricing_cache.get_ocean_freight()
                 if r.us_port.lower() == us_p
                 and r.eu_port == eu_p
                 and _is_active(r, calc_date)),
                None,
            )

            eu_to_ua = next(
                (r for r in pricing_cache.get_eu_to_ua()
                 if r.eu_port == eu_p and _is_active(r, calc_date)),
                None,
            )

            # Курс НБУ: сначала точный по дате, затем ближайший предыдущий
            all_rates = pricing_cache.get_exchange_rates()
            usd_to_uah = next(
                (r for r in all_rates if r.from_currency == 'USD' and r.to_currency == 'UAH' and r.date == calc_date),
                None,
            ) or next(
                iter(sorted(
                    [r for r in all_rates if r.from_currency == 'USD' and r.to_currency == 'UAH'],
                    key=lambda r: r.date, reverse=True,
                )),
                None,
            )

            usd_to_eur = next(
                (r for r in all_rates if r.from_currency == 'USD' and r.to_currency == 'EUR' and r.date == calc_date),
                None,
            ) or next(
                iter(sorted(
                    [r for r in all_rates if r.from_currency == 'USD' and r.to_currency == 'EUR'],
                    key=lambda r: r.date, reverse=True,
                )),
                None,
            )

            engine_cc = data['engine_cc']
            excise_rate = next(
                iter(sorted(
                    [r for r in pricing_cache.get_customs_excise()
                     if r.fuel_type == data['fuel_type']
                     and r.engine_cc_min <= engine_cc
                     and (r.engine_cc_max is None or r.engine_cc_max >= engine_cc)
                     and _is_active(r, calc_date)],
                    key=lambda r: r.engine_cc_min, reverse=True,
                )),
                None,
            )

            approx_uah = data['auction_price_usd'] * usd_to_uah.rate if usd_to_uah else None
            pension_bracket = None
            if approx_uah:
                pension_bracket = next(
                    iter(sorted(
                        [r for r in pricing_cache.get_pension_brackets()
                         if r.min_value_uah <= approx_uah
                         and (r.max_value_uah is None or r.max_value_uah >= approx_uah)
                         and _is_active(r, calc_date)],
                        key=lambda r: r.min_value_uah, reverse=True,
                    )),
                    None,
                )

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
