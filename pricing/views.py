import logging
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import cache as pricing_cache
from .calculator import (
    LandedCostInputs,
    MissingRate,
    applied_rates,
    broker_services_for,
    build_form_options,
    build_rate_snapshot_from_db,
    calc_auction_fees,
    calculate_landed_cost,
    catalog_is_demo,
    public_extra_options,
    rate_snapshot_to_dict,
    select_rates,
    selection_is_demo,
    ua_delivery_cost,
)
from .hooks import on_calculation_saved
from .models import (
    AuctionFeeTier,
    AuctionFixedFee,
    BrokerServiceFee,
    Calculation,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    RateSource,
    UaDeliveryRate,
    UsLandRoute,
)
from .serializers import CalculateInputSerializer

logger = logging.getLogger(__name__)

# Дефолты скрытых параметров тарифа - один источник (02-C11): и для расчёта, и для /rates/.
FORM_DEFAULTS = {
    'member_type': getattr(settings, 'AUCTION_DEFAULT_MEMBER_TYPE', 'broker'),
    'payment_type': 'secured',
    'title_type': 'salvage',
}
# Подписи значений, которые есть в choices моделей; порты и локации - данные, подпись из значения.
FORM_LABELS = {
    'auction': dict(AuctionFeeTier.Auction.choices),
    'member_type': {'public': 'Приватна особа', 'licensed': 'Ліцензований дилер', 'broker': 'Брокер'},
    'payment_type': {'secured': 'Забезпечена', 'unsecured': 'Незабезпечена'},
    'title_type': {'clean': 'Чистий (clean)', 'salvage': 'Salvage / Rebuildable', 'any': 'Будь-який'},
    'fuel_type': {'petrol': 'Бензин', 'diesel': 'Дизель', 'electric': 'Електро', 'hybrid': 'Гібрид',
                  'phev': 'Гібрид (PHEV)'},
}
INTERNAL_ERROR = {'error': 'internal_error'}


def _sees_full_grid(user) -> bool:
    """Q11: полная тарифная сетка и технические имена тарифов - только админ (staff-роль) и broker.

    Голый is_staff не годится: его получает и модератор, а граница модератора - никаких pricing.*.
    """
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_broker or user.is_admin_role))


def exchange_rate_info(selected, calc_date) -> dict:
    """Источник курса и предупреждение о давности (02-C8, 02-Q13). Демо-курс виден как `demo`."""
    uah, eur = selected.usd_to_uah, selected.usd_to_eur
    sources = {getattr(r, 'source', RateSource.DEMO) for r in (uah, eur) if r}
    source = RateSource.DEMO.value if RateSource.DEMO in sources else uah.source
    age_days = (calc_date - uah.date).days
    stale = age_days > settings.EXCHANGE_RATE_MAX_AGE_DAYS
    warning = None
    if stale:
        warning = (
            f'Курс валют застарілий: останній курс від {uah.date.strftime("%d.%m.%Y")} '
            f'({age_days} дн. до дати розрахунку). Підсумок може відрізнятися від фактичного.'
        )
    return {'exchange_rate_source': source, 'exchange_rate_stale': stale, 'exchange_rate_warning': warning}


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
        422: OpenApiResponse(description='Нет активных тарифов: `not_configured` (+ `missing` для staff/broker)'),
        429: OpenApiResponse(description='Превышен лимит расчётов (scope `calculator`)'),
        500: OpenApiResponse(description='`{"error": "internal_error"}` без деталей'),
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'calculator'

    def post(self, request):
        serializer = CalculateInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            return self._calculate(request, serializer.validated_data)
        except Exception:
            # 02-S1: текст исключения и тело запроса - только в лог (без ПДн), клиенту - код ошибки.
            logger.exception('calculate failed')
            return Response(INTERNAL_ERROR, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _calculate(self, request, data):
        calc_date = data.get('calculation_date') or date.today()
        params = {**data}
        for key, value in FORM_DEFAULTS.items():
            params[key] = data.get(key) or value

        # Подбор тарифов - чистая функция калькулятора (02-Q6); view только загружает каталог.
        selected = select_rates(pricing_cache.get_catalog(), params, calc_date)
        if data.get('ua_delivery_rate') is not None and selected.ua_delivery is None:
            # 2.7: несуществующая, недействующая или не с этого порта ЕС ставка - ошибка поля, а не тихий pending.
            return Response({'ua_delivery_rate': ['Доставка до цього міста зараз недоступна. Оберіть інше.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if selected.missing:
            return _missing_response(request, selected.missing)

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
                'ua_delivery_rate_id': selected.ua_delivery.pk if selected.ua_delivery else None,
                'broker_service_fee_ids': [f.pk for f in selected.broker_fees],
            },
        )
        rates.ua_delivery_cost_usd = ua_delivery_cost(selected.ua_delivery)
        rates.broker_services = broker_services_for(selected.broker_fees, data['auction_price_usd'])
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
            return _missing_response(request, [*map(str, exc.args)] or ['MissingRate'])

        breakdown = result.to_dict()
        rates_dict = rate_snapshot_to_dict(rates)
        updated_on = selected.rates_updated_on
        rates_dict['rates_updated_on'] = updated_on.isoformat() if updated_on else None
        is_demo = selection_is_demo(selected)
        rates_dict['is_demo'] = is_demo
        texts = pricing_cache.get_calculator_settings()

        calc = Calculation.objects.create(
            user=request.user if request.user.is_authenticated else None,
            inputs_snapshot=_inputs_snapshot(data),
            rates_snapshot=rates_dict,
            breakdown=breakdown,
            total_usd=result.total_usd,
            total_uah=result.total_uah,
            is_estimate=True,
        )
        # Счётчик расчётов (шаг 13): только после фиксации транзакции и только на 201.
        transaction.on_commit(lambda: on_calculation_saved(calc))

        return Response(
            {
                'calculation_id': calc.pk,
                'is_estimate': True,
                # 2.6: демо - есть непроверенная применённая ставка или курс из сида; баннер только по нему.
                'is_demo': is_demo,
                # Q5: пока брокер не подтвердил правило - интерфейс показывает «орієнтовний розрахунок».
                'rules_confirmed': bool(selected.rule.confirmed_by_broker),
                'rates_validity_date': calc_date.isoformat(),
                'rates_updated_on': updated_on.isoformat() if updated_on else None,
                'exchange_rate_date': selected.usd_to_uah.date.isoformat(),
                **exchange_rate_info(selected, calc_date),
                'applied_rates': applied_rates(rates, data['fuel_type']),
                'warning': texts.result_warning,
                'estimate_note': texts.estimate_note,
                'demo_banner': {'title': texts.demo_banner_title, 'text': texts.demo_banner_text},
                'breakdown': breakdown,
            },
            status=status.HTTP_201_CREATED,
        )


def _missing_response(request, missing):
    """422: гостю - без имён моделей и параметров тарифов (Q11), staff/broker - список недостающего."""
    body = {'error': 'not_configured', 'missing_count': len(missing)}
    if _sees_full_grid(request.user):
        body['missing'] = missing
    return Response(body, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


def _inputs_snapshot(data) -> dict:
    """Снимок входов (02-Q9): Decimal - строкой, даты - ISO, None остаётся None."""
    def conv(value):
        if value is None or isinstance(value, (bool, int, str)):
            return value
        return str(value)  # Decimal -> '5000.00', date -> ISO 'YYYY-MM-DD'
    return {k: conv(v) for k, v in data.items()}


_GRID_FIELDS = {
    'auction_fee_tiers': drf_serializers.ListField(),
    'auction_fixed_fees': drf_serializers.ListField(),
    'us_land_routes': drf_serializers.ListField(),
    'ocean_freight': drf_serializers.ListField(),
    'eu_to_ua': drf_serializers.ListField(),
    'exchange_rates': drf_serializers.ListField(),
    'excise_rates': drf_serializers.ListField(),
    'pension_brackets': drf_serializers.ListField(),
}
_PUBLIC_FIELDS = {
    'ua_delivery_rates': drf_serializers.ListField(
        help_text='Гостям: id, destination, eu_port, quote_on_request (без сумм); staff/broker - с cost_usd'),
    'broker_service_fees': drf_serializers.ListField(
        help_text='Гостям: id, title (без сумм и процентов); staff/broker - с fee_mode, amount_usd, percent'),
    'options': drf_serializers.DictField(help_text='Справочники формы без сумм (auctions, us_ports, eu_ports, …)'),
    'is_demo': drf_serializers.BooleanField(),
    'demo_banner': drf_serializers.DictField(),
}


@extend_schema(
    tags=['pricing'],
    summary='Справочники калькулятора (и тарифы для staff/broker)',
    description=(
        'Всем: `options` (значения формы из активных тарифов, без сумм) и `is_demo` (Q11). '
        'staff и broker дополнительно получают полную тарифную сетку на сегодня.'
    ),
    responses={
        200: OpenApiResponse(
            response=inline_serializer(name='ActiveRatesResponse', fields={**_PUBLIC_FIELDS, **_GRID_FIELDS}),
            description='Ключи сетки (auction_fee_tiers и др.) - только для staff и broker.',
        ),
    },
)
class ActiveRatesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        today = date.today()
        catalog = pricing_cache.get_catalog()
        texts = pricing_cache.get_calculator_settings()
        body = {
            'options': build_form_options(catalog, today, FORM_DEFAULTS, FORM_LABELS),
            # 2.7 (Q6, Q11): города и названия услуг без сумм; суммы - в расчёте и в сетке staff/broker.
            **public_extra_options(catalog, today),
            'is_demo': catalog_is_demo(catalog, today),
            'demo_banner': {'title': texts.demo_banner_title, 'text': texts.demo_banner_text},
        }
        if _sees_full_grid(request.user):
            body.update(_full_grid(today))
        return Response(body)


def _active_on(qs, on_date=None):
    """ORM-фильтр «действует на дату»."""
    on_date = on_date or date.today()
    return qs.filter(valid_from__lte=on_date).filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))


def _full_grid(today) -> dict:
    def active(qs):
        return _active_on(qs, today)

    return {
        'auction_fee_tiers': list(
            active(AuctionFeeTier.objects.all()).values(
                'id', 'auction', 'member_type', 'payment_type', 'title_type',
                'bid_min', 'bid_max', 'fee_flat', 'fee_percent', 'is_verified',
            )
        ),
        'auction_fixed_fees': list(
            active(AuctionFixedFee.objects.all()).values('id', 'auction', 'fee_type', 'title_type', 'amount',
                                                         'is_verified')
        ),
        'us_land_routes': list(
            active(UsLandRoute.objects.all()).values('id', 'auction_location', 'us_port', 'cost_usd', 'is_verified')
        ),
        'ocean_freight': list(
            active(OceanFreightRate.objects.all()).values('id', 'us_port', 'eu_port', 'cost_usd', 'is_verified')
        ),
        'eu_to_ua': list(active(EuToUaDeliveryRate.objects.all()).values('id', 'eu_port', 'cost_usd', 'is_verified')),
        'exchange_rates': list(
            ExchangeRate.objects.order_by('-date').values('from_currency', 'to_currency', 'rate', 'date', 'source')[:10]
        ),
        'excise_rates': list(
            active(CustomsExciseRate.objects.all()).values(
                'id', 'fuel_type', 'eur_per_100cc', 'ev_excise_eur_per_kwh', 'duty_rate', 'vat_rate', 'is_verified'
            )
        ),
        'pension_brackets': list(
            active(PensionFundBracket.objects.all()).values('id', 'min_value_uah', 'max_value_uah', 'rate',
                                                            'is_verified')
        ),
        # 2.7: с суммами - вместо публичного списка без сумм
        'ua_delivery_rates': list(
            active(UaDeliveryRate.objects.all()).values('id', 'destination', 'eu_port', 'cost_usd',
                                                        'quote_on_request', 'is_verified')
        ),
        'broker_service_fees': list(
            active(BrokerServiceFee.objects.all()).values('id', 'title', 'fee_mode', 'amount_usd', 'percent',
                                                          'is_verified')
        ),
    }
