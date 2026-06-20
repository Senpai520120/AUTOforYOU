"""
Сервис расчёта стоимости автомобиля «под ключ» в Украине.

Чистая детерминированная функция без обращений к БД.
Принимает входные данные и снимок ставок → возвращает полную детализацию.

ВАЖНО: Ставки акциза и пенсионного сбора зафиксированы в БД
с плейсхолдер-значениями. Результат всегда is_estimate=True.
Сетки аукционных сборов — baseline (сверить с тарифом брокера).
"""
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP


ZERO = Decimal('0')
TWO_PLACES = Decimal('0.01')


def _d(value) -> Decimal:
    return Decimal(str(value))


# ─── Аукционные сборы ────────────────────────────────────────────────────────

@dataclass
class AuctionFeeBreakdown:
    """Детализация buyer fee + фиксированных сборов аукциона."""
    buyer_fee: Decimal    # тиерный сбор (flat или %)
    gate_fee: Decimal     # gate / service fee
    environmental_fee: Decimal
    virtual_bid_fee: Decimal
    total: Decimal        # сумма всех четырёх


def calc_auction_fees(
    bid: Decimal,
    tier,        # AuctionFeeTier (или объект с .fee_flat, .fee_percent)
    fixed_fees,  # list[AuctionFixedFee] — уже отфильтрованные по auction + title_type
) -> AuctionFeeBreakdown:
    """
    Рассчитывает полный аукционный сбор.
    Чистая функция: принимает готовые объекты, не обращается к БД.
    # baseline — сверить с офиц. сеткой и тарифом брокера
    """
    bid = _d(bid)

    if tier.fee_flat is not None:
        buyer_fee = _d(tier.fee_flat)
    else:
        buyer_fee = (bid * _d(tier.fee_percent)).quantize(TWO_PLACES, ROUND_HALF_UP)

    gate_fee = ZERO
    environmental_fee = ZERO
    virtual_bid_fee = ZERO

    for f in fixed_fees:
        amount = _d(f.amount)
        if f.fee_type == 'gate':
            gate_fee = (gate_fee + amount).quantize(TWO_PLACES, ROUND_HALF_UP)
        elif f.fee_type == 'environmental':
            environmental_fee = (environmental_fee + amount).quantize(TWO_PLACES, ROUND_HALF_UP)
        elif f.fee_type == 'virtual_bid':
            virtual_bid_fee = (virtual_bid_fee + amount).quantize(TWO_PLACES, ROUND_HALF_UP)

    total = (buyer_fee + gate_fee + environmental_fee + virtual_bid_fee).quantize(TWO_PLACES, ROUND_HALF_UP)

    return AuctionFeeBreakdown(
        buyer_fee=buyer_fee,
        gate_fee=gate_fee,
        environmental_fee=environmental_fee,
        virtual_bid_fee=virtual_bid_fee,
        total=total,
    )


# ─── Снимок ставок ───────────────────────────────────────────────────────────

@dataclass
class RateSnapshot:
    auction_fee: AuctionFeeBreakdown
    us_land_cost_usd: Decimal
    ocean_freight_usd: Decimal
    eu_to_ua_cost_usd: Decimal
    usd_to_uah: Decimal
    usd_to_eur: Decimal
    # Акциз ДВС: EUR за каждые 100 см³ (petrol/diesel/hybrid)
    # Источник: ставки растаможки Украины, актуальны на янв–июнь 2026; финал подтверждает таможенный брокер
    excise_eur_per_100cc: Decimal
    # Акциз EV/PHEV: EUR за кВт·ч ёмкости батареи
    ev_excise_eur_per_kwh: Decimal
    # Коэффициент возраста: min(15, max(1, год_расчёта − год_выпуска))
    age_coefficient: Decimal
    duty_rate: Decimal
    vat_rate: Decimal
    # Дата актуальности ставок (дата оформления таможни)
    rates_date: str = ''
    pension_fund_rate: Decimal = ZERO
    meta: dict = field(default_factory=dict)


# ─── Входные данные ───────────────────────────────────────────────────────────

@dataclass
class LandedCostInputs:
    auction_price_usd: Decimal
    engine_cc: int
    fuel_type: str   # petrol / diesel / electric / hybrid / phev
    vehicle_year: int
    calculation_year: int
    battery_capacity_kwh: int = 0  # для EV/PHEV — ёмкость батареи в кВт·ч


# ─── Детализация расчёта ──────────────────────────────────────────────────────

@dataclass
class LandedCostBreakdown:
    # Статьи расходов в USD
    auction_price_usd: Decimal
    auction_fee_usd: Decimal          # итог аукционного сбора (buyer+gate+env+vb)
    auction_fee_buyer_usd: Decimal    # только тиерный buyer fee
    auction_fee_gate_usd: Decimal
    auction_fee_environmental_usd: Decimal
    auction_fee_virtual_bid_usd: Decimal
    us_land_usd: Decimal
    ocean_freight_usd: Decimal
    eu_to_ua_usd: Decimal
    # Таможенная стоимость (для расчёта пошлины)
    customs_value_usd: Decimal
    # Растаможка (в EUR→UAH)
    excise_eur: Decimal
    excise_uah: Decimal
    duty_usd: Decimal
    duty_uah: Decimal
    vat_base_uah: Decimal
    vat_uah: Decimal
    pension_fund_uah: Decimal
    customs_total_uah: Decimal
    # Итоги
    total_usd: Decimal
    total_uah: Decimal
    is_estimate: bool = True

    def to_dict(self) -> dict:
        return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(self).items()}


# ─── Возрастной коэффициент ───────────────────────────────────────────────────

def calc_age_coeff(vehicle_year: int, calculation_year: int) -> Decimal:
    """
    Коэффициент возраста = min(15, max(1, год_расчёта − год_выпуска)).

    Потолок 15 — авто старше 15 лет таможатся с коэффициентом 15 (выше не растёт).
    Уточнить у брокера: часть брокеров считает (год − год_выпуска − 1).
    """
    return _d(min(15, max(1, calculation_year - vehicle_year)))


# ─── Основной расчёт «под ключ» ───────────────────────────────────────────────

def calculate_landed_cost(inputs: LandedCostInputs, rates: RateSnapshot) -> LandedCostBreakdown:
    """
    Рассчитывает стоимость авто «под ключ» в Украине.

    Формула:
      1. Аукционный сбор = rates.auction_fee.total (buyer + gate + env + virtual_bid)
      2. Таможенная стоимость = auction_price + us_land + ocean_freight
      3. Акциз (EUR) = eur_per_100cc × (engine_cc / 100) × age_coeff
         Для EV/PHEV: фиксированный EUR × ёмкость батареи кВт·ч
      4. Пошлина (USD) = customs_value_usd × duty_rate
      5. НДС (UAH) = (customs_value_uah + duty_uah + excise_uah) × vat_rate
      6. Пенсионный сбор = итоговая_стоимость_uah × pension_rate
      7. Итого USD = auction_price + auction_fee + us_land + ocean + eu_to_ua + duty_usd
      8. Итого UAH = итого_USD × usd_to_uah + excise_uah + vat_uah + pension_uah
    """
    price = _d(inputs.auction_price_usd)
    engine_cc = inputs.engine_cc
    is_ev_type = inputs.fuel_type in ('electric', 'phev')

    # 1. Аукционный сбор — уже рассчитан в RateSnapshot
    auction_fee_total = _d(rates.auction_fee.total)

    # 2. Таможенная стоимость (CIF до порта ЕС = auction + US land + ocean)
    customs_value_usd = (price + _d(rates.us_land_cost_usd) + _d(rates.ocean_freight_usd)).quantize(TWO_PLACES, ROUND_HALF_UP)

    # 3. Акциз
    # Источник: ставки растаможки Украины, актуальны на янв–июнь 2026; финал подтверждает таможенный брокер
    # EV/PHEV: фиксированная ставка EUR × ёмкость батареи кВт·ч
    # ДВС (petrol/diesel/hybrid): base_rate × (engine_cc/100) × age_coeff
    if is_ev_type:
        excise_eur = (_d(rates.ev_excise_eur_per_kwh) * _d(inputs.battery_capacity_kwh)).quantize(TWO_PLACES, ROUND_HALF_UP)
    else:
        excise_eur = (_d(rates.excise_eur_per_100cc) * _d(engine_cc) / Decimal('100') * _d(rates.age_coefficient)).quantize(TWO_PLACES, ROUND_HALF_UP)

    eur_to_uah = _d(rates.usd_to_uah) / _d(rates.usd_to_eur)
    excise_uah = (excise_eur * eur_to_uah).quantize(TWO_PLACES, ROUND_HALF_UP)

    # 4. Пошлина: EV/PHEV = 0%; US-origin ДВС = 10% (льгота EUR.1 не применяется для США)
    duty_usd = (customs_value_usd * _d(rates.duty_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)
    duty_uah = (duty_usd * _d(rates.usd_to_uah)).quantize(TWO_PLACES, ROUND_HALF_UP)

    # 5. НДС 20% от (таможенная стоимость + пошлина + акциз) в UAH
    # С 01.01.2026 льгота по НДС для EV отменена — все авто платят 20%
    customs_value_uah = (customs_value_usd * _d(rates.usd_to_uah)).quantize(TWO_PLACES, ROUND_HALF_UP)
    vat_base_uah = customs_value_uah + duty_uah + excise_uah
    vat_uah = (vat_base_uah * _d(rates.vat_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)

    # 6. Итого USD (аукцион + логистика + пошлина)
    total_logistic_usd = (price + auction_fee_total + _d(rates.us_land_cost_usd) + _d(rates.ocean_freight_usd) + _d(rates.eu_to_ua_cost_usd)).quantize(TWO_PLACES, ROUND_HALF_UP)
    total_usd = (total_logistic_usd + duty_usd).quantize(TWO_PLACES, ROUND_HALF_UP)

    # 7. Пенсионный сбор от общей стоимости авто в UAH
    # ПРОВЕРИТЬ по действующему законодательству Украины
    pre_pension_uah = (total_logistic_usd * _d(rates.usd_to_uah) + excise_uah + duty_uah + vat_uah).quantize(TWO_PLACES, ROUND_HALF_UP)
    pension_fund_uah = (pre_pension_uah * _d(rates.pension_fund_rate)).quantize(TWO_PLACES, ROUND_HALF_UP)

    # 8. Итого UAH
    customs_total_uah = excise_uah + duty_uah + vat_uah + pension_fund_uah
    total_uah = (total_logistic_usd * _d(rates.usd_to_uah) + customs_total_uah).quantize(TWO_PLACES, ROUND_HALF_UP)

    return LandedCostBreakdown(
        auction_price_usd=price,
        auction_fee_usd=auction_fee_total,
        auction_fee_buyer_usd=_d(rates.auction_fee.buyer_fee),
        auction_fee_gate_usd=_d(rates.auction_fee.gate_fee),
        auction_fee_environmental_usd=_d(rates.auction_fee.environmental_fee),
        auction_fee_virtual_bid_usd=_d(rates.auction_fee.virtual_bid_fee),
        us_land_usd=_d(rates.us_land_cost_usd),
        ocean_freight_usd=_d(rates.ocean_freight_usd),
        eu_to_ua_usd=_d(rates.eu_to_ua_cost_usd),
        customs_value_usd=customs_value_usd,
        excise_eur=excise_eur,
        excise_uah=excise_uah,
        duty_usd=duty_usd,
        duty_uah=duty_uah,
        vat_base_uah=vat_base_uah,
        vat_uah=vat_uah,
        pension_fund_uah=pension_fund_uah,
        customs_total_uah=customs_total_uah,
        total_usd=total_usd,
        total_uah=total_uah,
        is_estimate=True,
    )


# ─── Сборка RateSnapshot из объектов Django-моделей ──────────────────────────

def build_rate_snapshot_from_db(
    auction_fee_breakdown: AuctionFeeBreakdown,
    us_land_route,
    ocean_freight,
    eu_to_ua,
    usd_to_uah_rate,
    usd_to_eur_rate,
    excise_rate,
    vehicle_year: int,
    calculation_year: int,
    pension_rate,
    rates_date: str = '',
    meta: dict = None,
) -> RateSnapshot:
    """Собирает RateSnapshot из объектов моделей Django."""
    ev_kwh = excise_rate.ev_excise_eur_per_kwh
    return RateSnapshot(
        auction_fee=auction_fee_breakdown,
        us_land_cost_usd=_d(us_land_route.cost_usd),
        ocean_freight_usd=_d(ocean_freight.cost_usd),
        eu_to_ua_cost_usd=_d(eu_to_ua.cost_usd),
        usd_to_uah=_d(usd_to_uah_rate.rate),
        usd_to_eur=_d(usd_to_eur_rate.rate),
        excise_eur_per_100cc=_d(excise_rate.eur_per_100cc),
        ev_excise_eur_per_kwh=_d(ev_kwh) if ev_kwh is not None else Decimal('0'),
        age_coefficient=calc_age_coeff(vehicle_year, calculation_year),
        duty_rate=_d(excise_rate.duty_rate),
        vat_rate=_d(excise_rate.vat_rate),
        pension_fund_rate=_d(pension_rate.rate),
        rates_date=rates_date,
        meta=meta or {
            'us_land_route_id': us_land_route.pk,
            'ocean_freight_id': ocean_freight.pk,
            'eu_to_ua_id': eu_to_ua.pk,
            'usd_to_uah_rate_id': usd_to_uah_rate.pk,
            'usd_to_eur_rate_id': usd_to_eur_rate.pk,
            'excise_rate_id': excise_rate.pk,
            'pension_bracket_id': pension_rate.pk,
        },
    )


def rate_snapshot_to_dict(rates: RateSnapshot) -> dict:
    return {
        'auction_fee_total': str(rates.auction_fee.total),
        'auction_fee_buyer': str(rates.auction_fee.buyer_fee),
        'auction_fee_gate': str(rates.auction_fee.gate_fee),
        'auction_fee_environmental': str(rates.auction_fee.environmental_fee),
        'auction_fee_virtual_bid': str(rates.auction_fee.virtual_bid_fee),
        'us_land_cost_usd': str(rates.us_land_cost_usd),
        'ocean_freight_usd': str(rates.ocean_freight_usd),
        'eu_to_ua_cost_usd': str(rates.eu_to_ua_cost_usd),
        'usd_to_uah': str(rates.usd_to_uah),
        'usd_to_eur': str(rates.usd_to_eur),
        'excise_eur_per_100cc': str(rates.excise_eur_per_100cc),
        'ev_excise_eur_per_kwh': str(rates.ev_excise_eur_per_kwh),
        'age_coefficient': str(rates.age_coefficient),
        'duty_rate': str(rates.duty_rate),
        'vat_rate': str(rates.vat_rate),
        'pension_fund_rate': str(rates.pension_fund_rate),
        'rates_date': rates.rates_date,
        'meta': rates.meta,
    }
