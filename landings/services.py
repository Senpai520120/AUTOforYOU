"""Расчёт «під ключ» для SEO-страницы модели (задача 2.16).

Формул здесь нет: подбор ставок - pricing.calculator.select_rates, расчёт - calculate_landed_cost.
Модуль ничего не пишет в БД (ни Calculation, ни страницу).
"""
import uuid
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

from pricing import cache as pricing_cache
from pricing.calculator import (
    EV_FUEL_TYPES,
    LandedCostInputs,
    MissingRate,
    applied_rates,
    broker_services_for,
    build_rate_snapshot_from_db,
    calc_auction_fees,
    calculate_landed_cost,
    rate_snapshot_to_dict,
    select_rates,
    selection_is_demo,
)
from pricing.views import FORM_DEFAULTS

from .models import LandingSettings, ModelLandingPage

ZERO = Decimal('0')
CACHE_TTL = 600  # 10 минут; правка тарифов или страницы сбрасывает кэш сразу (версия + updated_at в ключе)
VERSION_KEY = 'landings:version'  # тот же ключ, что KEYS['landings_version'] в pricing.cache


def _cache_version() -> str:
    try:
        version = cache.get(VERSION_KEY)
        if version is None:
            version = uuid.uuid4().hex
            cache.set(VERSION_KEY, version, None)
        return version
    except Exception:
        return 'nocache'


def bump_cache_version() -> None:
    try:
        cache.delete(VERSION_KEY)
    except Exception:
        pass


def cached_calculation(page: ModelLandingPage) -> dict | None:
    """build_landing_calculation с кэшем. Ключ: версия каталога, страница, updated_at, дата расчёта."""
    key = f'landings:calc:{_cache_version()}:{page.pk}:{page.updated_at.timestamp()}:{timezone.localdate()}'
    try:
        hit = cache.get(key)
    except Exception:
        hit = None
    if hit is not None:
        return hit['calc']
    calc = build_landing_calculation(page)
    try:
        cache.set(key, {'calc': calc}, CACHE_TTL)  # None (нет расчёта) тоже кэшируется
    except Exception:
        pass
    return calc


def _inputs(page: ModelLandingPage) -> dict | None:
    """Входы расчёта из полей страницы; None - не хватает обязательного."""
    is_ev = page.fuel_type in EV_FUEL_TYPES
    if (page.auction_price_usd is None or not page.fuel_type or page.calc_year is None
            or not (page.auction_location and page.us_port and page.eu_port)):
        return None
    if not is_ev and page.engine_cc is None:
        return None
    if is_ev and not (page.battery_capacity_kwh and page.battery_capacity_kwh > 0):
        return None
    return {
        'auction_price_usd': page.auction_price_usd,
        'engine_cc': page.engine_cc or 0,
        'fuel_type': page.fuel_type,
        'vehicle_year': page.calc_year,
        'battery_capacity_kwh': page.battery_capacity_kwh if is_ev else None,
        'auction': page.auction,
        'auction_location': page.auction_location,
        'us_port': page.us_port,
        'eu_port': page.eu_port,
        **FORM_DEFAULTS,
    }


def _inputs_snapshot(page: ModelLandingPage, inputs: dict, calc_date: date) -> dict:
    snap = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in inputs.items()}
    snap.update({'make': page.make, 'model': page.model, 'year': page.calc_year,
                 'calculation_date': calc_date.isoformat()})
    return snap


def build_landing_calculation(page: ModelLandingPage, *, now=None) -> dict | None:
    """Полный расчёт по входам страницы или None (входы неполны / нет активных ставок).

    Деньги - строками Decimal. `rates_snapshot` - только для снимка заявки, в публичный API не отдаётся.
    """
    inputs = _inputs(page)
    if inputs is None:
        return None
    calc_date = timezone.localdate(now) if now else timezone.localdate()
    selected = select_rates(pricing_cache.get_catalog(), inputs, calc_date)
    if selected.missing:
        return None

    fees = calc_auction_fees(bid=inputs['auction_price_usd'], tier=selected.tier, fixed_fees=selected.fixed_fees)
    rates = build_rate_snapshot_from_db(
        auction_fee_breakdown=fees, us_land_route=selected.us_land, ocean_freight=selected.ocean,
        eu_to_ua=selected.eu_to_ua, usd_to_uah_rate=selected.usd_to_uah, usd_to_eur_rate=selected.usd_to_eur,
        excise_rate=selected.excise, vehicle_year=inputs['vehicle_year'], calculation_year=calc_date.year,
        rates_date=calc_date.isoformat(), rule=selected.rule, on_date=calc_date,
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
            'broker_service_fee_ids': [f.pk for f in selected.broker_fees],
        },
    )
    # Город доставки по Украине на странице не выбран: ua_delivery остаётся «уточнюється менеджером».
    rates.broker_services = broker_services_for(selected.broker_fees, inputs['auction_price_usd'])
    landed = LandedCostInputs(
        auction_price_usd=inputs['auction_price_usd'], engine_cc=inputs['engine_cc'],
        fuel_type=inputs['fuel_type'], vehicle_year=inputs['vehicle_year'], calculation_year=calc_date.year,
        battery_capacity_kwh=inputs['battery_capacity_kwh'] or ZERO,
    )
    try:
        result = calculate_landed_cost(landed, rates, selected.pension_brackets, selected.rule)
    except MissingRate:
        return None

    updated_on = selected.rates_updated_on
    rates_dict = rate_snapshot_to_dict(rates)
    rates_dict['rates_updated_on'] = updated_on.isoformat() if updated_on else None
    return {
        'is_estimate': True,
        'is_demo': selection_is_demo(selected),
        'rules_confirmed': bool(selected.rule.confirmed_by_broker),
        'rates_valid_from': updated_on.isoformat() if updated_on else None,
        'rates_date': calc_date.isoformat(),
        'currency': 'USD',
        'local_currency': 'UAH',
        'usd_to_uah': str(rates.usd_to_uah),
        'exchange_rate_date': selected.usd_to_uah.date.isoformat(),
        'total_usd': str(result.total_usd),
        'total_uah': str(result.total_uah),
        'breakdown': result.to_dict(),
        'applied_rates': applied_rates(rates, inputs['fuel_type']),
        'inputs': _inputs_snapshot(page, inputs, calc_date),
        'rates_snapshot': rates_dict,
    }


def can_publish(page: ModelLandingPage) -> bool:
    return build_landing_calculation(page) is not None


def published_pages():
    return ModelLandingPage.objects.filter(is_published=True)


def get_published_page(slug: str) -> tuple[ModelLandingPage, dict] | None:
    """Опубликованная страница и её расчёт. Нет страницы, черновик или расчёт не получается - None."""
    page = published_pages().filter(slug=slug).first()
    if page is None or page.has_draft_marker():
        return None
    calc = cached_calculation(page)
    return (page, calc) if calc is not None else None


def published_with_calculation() -> list[tuple[ModelLandingPage, dict]]:
    result = []
    for page in published_pages():
        if page.has_draft_marker():
            continue
        calc = cached_calculation(page)
        if calc is not None:
            result.append((page, calc))
    return result


def lead_calculation_snapshot(page: ModelLandingPage, calc: dict) -> dict:
    """Снимок для Lead.calculation_snapshot: форма та же, что у build_calculation_snapshot."""
    return {
        'landing_slug': page.slug,
        'created_at': timezone.now().isoformat(),
        'is_estimate': True,
        'rates_valid_from': calc['rates_valid_from'],
        'inputs_snapshot': calc['inputs'],
        'rates_snapshot': calc['rates_snapshot'],
        'breakdown': calc['breakdown'],
        'total_usd': calc['total_usd'],
        'total_uah': calc['total_uah'],
    }


def publication_warning() -> str | None:
    """Предупреждение админке: опубликовано больше рекомендованного. Публикацию не блокирует."""
    limit = LandingSettings.get_solo().max_published
    count = published_pages().count()
    if count > limit:
        return (f'Опубліковано {count} сторінок, рекомендована межа - {limit}. '
                'Змінити межу: «Налаштування сторінок моделей».')
    return None
