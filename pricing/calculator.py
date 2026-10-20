"""
Сервис расчёта стоимости автомобиля «под ключ» в Украине.

Чистая детерминированная функция без обращений к БД.
Принимает входные данные и снимок ставок → возвращает полную детализацию.

ВАЖНО: Ставки акциза и пенсионного сбора зафиксированы в БД
с плейсхолдер-значениями. Результат всегда is_estimate=True.
Сетки аукционных сборов — baseline (сверить с тарифом брокера).
"""
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal

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
    # Фактические даты курсов (02-Q5, 02-Q10): не позже даты расчёта
    usd_to_uah_date: str = ''
    usd_to_eur_date: str = ''
    # Правило растаможки, по которому считали (2.5, Q5): id и значения полей
    rule: dict = field(default_factory=dict)
    # Дата расчёта для выбора брекета внутри calculate_landed_cost
    rates_on_date: object = None


# ─── Входные данные ───────────────────────────────────────────────────────────

@dataclass
class LandedCostInputs:
    auction_price_usd: Decimal
    engine_cc: int
    fuel_type: str   # petrol / diesel / electric / hybrid / phev
    vehicle_year: int
    calculation_year: int
    battery_capacity_kwh: Decimal = ZERO  # для EV/PHEV — ёмкость батареи в кВт·ч (напр. 75.5)


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

def calc_age_coeff(vehicle_year: int, calculation_year: int, min_coeff: int = 1, max_coeff: int = 15,
                   offset_years: int = 0) -> Decimal:
    """
    Коэффициент возраста = min(max_coeff, max(min_coeff, год_расчёта − год_выпуска − offset_years)).

    Параметры - из правила растаможки (CustomsCalcRule, 02-C6); значения по умолчанию воспроизводят
    прежнюю формулу. Часть брокеров считает (год − год_выпуска − 1) - это offset_years=1.
    """
    return _d(min(max_coeff, max(min_coeff, calculation_year - vehicle_year - offset_years)))


# ─── Основной расчёт «под ключ» ───────────────────────────────────────────────

def calculate_landed_cost(inputs: LandedCostInputs, rates: RateSnapshot, pension_brackets=None,
                          rule=None) -> LandedCostBreakdown:
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

    pension_brackets и rule (2.5, Q5): брекет пенсионного сбора выбирается здесь по базе из правила
    (rule.pension_bracket_base), ставка применяется к rule.pension_rate_base. Без брекетов -
    берётся готовая rates.pension_fund_rate (прежнее поведение, юнит-тесты формулы).
    Брекет не найден - MissingRate('PensionFundBracket').
    """
    rule = rule or DEFAULT_RULE
    price = _d(inputs.auction_price_usd)
    engine_cc = inputs.engine_cc
    is_ev_type = inputs.fuel_type in ('electric', 'phev')

    # 1. Аукционный сбор — уже рассчитан в RateSnapshot
    auction_fee_total = _d(rates.auction_fee.total)

    # 2. Таможенная стоимость (CIF до порта ЕС = auction + US land + ocean)
    customs_value_usd = price + _d(rates.us_land_cost_usd) + _d(rates.ocean_freight_usd)
    if rule.customs_value_includes_eu_to_ua:  # 02-Q7: по заключению брокера (CustomsCalcRule)
        customs_value_usd += _d(rates.eu_to_ua_cost_usd)
    customs_value_usd = customs_value_usd.quantize(TWO_PLACES, ROUND_HALF_UP)

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
    bases = {
        PENSION_BASE_AUCTION_PRICE: (price * _d(rates.usd_to_uah)).quantize(TWO_PLACES, ROUND_HALF_UP),
        PENSION_BASE_CUSTOMS_VALUE: customs_value_uah,
        PENSION_BASE_CUSTOMS_WITH_TAXES: (customs_value_uah + duty_uah + excise_uah + vat_uah).quantize(
            TWO_PLACES, ROUND_HALF_UP),
        PENSION_BASE_TOTAL: pre_pension_uah,
    }
    pension_rate = _d(rates.pension_fund_rate)
    if pension_brackets is not None:
        bracket = pick_pension_bracket(pension_brackets, bases[rule.pension_bracket_base], rates.rates_on_date)
        if bracket is None:
            raise MissingRate('PensionFundBracket')
        pension_rate = _d(bracket.rate)
        rates.pension_fund_rate = pension_rate
        rates.meta = {**rates.meta, 'pension_bracket_id': bracket.pk}
    pension_fund_uah = (bases[rule.pension_rate_base] * pension_rate).quantize(TWO_PLACES, ROUND_HALF_UP)

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
    pension_rate=None,
    rates_date: str = '',
    meta: dict = None,
    rule=None,
    on_date=None,
) -> RateSnapshot:
    """Собирает RateSnapshot из объектов моделей Django (или заглушек с теми же атрибутами).

    pension_rate=None: брекет выберет calculate_landed_cost по правилу (2.5).
    """
    rule = rule or DEFAULT_RULE
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
        age_coefficient=calc_age_coeff(vehicle_year, calculation_year, rule.age_coeff_min, rule.age_coeff_max,
                                       rule.age_offset_years),
        duty_rate=_d(excise_rate.duty_rate),
        vat_rate=_d(excise_rate.vat_rate),
        pension_fund_rate=_d(pension_rate.rate) if pension_rate is not None else ZERO,
        rates_date=rates_date,
        meta=meta or {
            'us_land_route_id': us_land_route.pk,
            'ocean_freight_id': ocean_freight.pk,
            'eu_to_ua_id': eu_to_ua.pk,
            'usd_to_uah_rate_id': usd_to_uah_rate.pk,
            'usd_to_eur_rate_id': usd_to_eur_rate.pk,
            'excise_rate_id': excise_rate.pk,
            **({'pension_bracket_id': pension_rate.pk} if pension_rate is not None else {}),
        },
        usd_to_uah_date=_iso(getattr(usd_to_uah_rate, 'date', '')),
        usd_to_eur_date=_iso(getattr(usd_to_eur_rate, 'date', '')),
        rule=rule_to_dict(rule),
        rates_on_date=on_date,
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
        'usd_to_uah_date': rates.usd_to_uah_date,
        'usd_to_eur_date': rates.usd_to_eur_date,
        'rule': rates.rule,
        'meta': rates.meta,
    }


# ─── Правило растаможки и подбор тарифов (задача 2.5) ───────────────────────────
# Без Django и ORM: на вход - списки объектов тарифов (из pricing/cache.py) или заглушки.

PENSION_BASE_AUCTION_PRICE = 'auction_price'          # цена аукциона × курс
PENSION_BASE_CUSTOMS_VALUE = 'customs_value'          # таможенная стоимость, грн
PENSION_BASE_CUSTOMS_WITH_TAXES = 'customs_value_with_taxes'  # таможенная + пошлина + акциз + НДС
PENSION_BASE_TOTAL = 'total_before_pension'           # всё, кроме самого сбора (прежняя формула)

EV_FUEL_TYPES = ('electric', 'phev')


class MissingRate(Exception):
    """Нет активной ставки/правила для расчёта (view отвечает 422)."""


@dataclass
class DefaultRule:
    """Значения по умолчанию = прежнее поведение кода, а не юридическая трактовка (Q5)."""
    pk: object = None
    pension_bracket_base: str = PENSION_BASE_AUCTION_PRICE
    pension_rate_base: str = PENSION_BASE_TOTAL
    customs_value_includes_eu_to_ua: bool = False
    age_coeff_min: int = 1
    age_coeff_max: int = 15
    age_offset_years: int = 0
    confirmed_by_broker: bool = False
    confirmed_at: object = None
    valid_from: object = None


DEFAULT_RULE = DefaultRule()

_RULE_FIELDS = ('pension_bracket_base', 'pension_rate_base', 'customs_value_includes_eu_to_ua',
                'age_coeff_min', 'age_coeff_max', 'age_offset_years', 'confirmed_by_broker')


def _iso(value) -> str:
    if not value:
        return ''
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def rule_to_dict(rule) -> dict:
    data = {'id': getattr(rule, 'pk', None), **{f: getattr(rule, f) for f in _RULE_FIELDS}}
    data['confirmed_at'] = _iso(getattr(rule, 'confirmed_at', None)) or None
    data['valid_from'] = _iso(getattr(rule, 'valid_from', None)) or None
    return data


def is_active(obj, on_date) -> bool:
    return obj.valid_from <= on_date and (obj.valid_to is None or obj.valid_to >= on_date)


def _latest(items):
    """Из нескольких подходящих записей побеждает самый поздний valid_from, при равенстве - больший pk (02-Q4)."""
    items = list(items)
    if not items:
        return None
    return max(items, key=lambda o: (o.valid_from, o.pk or 0))


def pick_active(items, on_date, predicate=lambda o: True):
    return _latest(o for o in items if is_active(o, on_date) and predicate(o))


def lookup_tier(tiers, auction, bid, member_type, payment_type, title_type, on_date):
    """AuctionFeeTier: приоритет точного title_type, затем 'any' (смысл прежнего _lookup_tier)."""
    bid = _d(bid)

    def fits(t, title):
        return (t.auction == auction and t.member_type == member_type and t.payment_type == payment_type
                and t.title_type == title and t.bid_min <= bid and (t.bid_max is None or t.bid_max >= bid))

    return (pick_active(tiers, on_date, lambda t: fits(t, title_type))
            or pick_active(tiers, on_date, lambda t: fits(t, 'any')))


def lookup_fixed_fees(fees, auction, title_type, on_date):
    """Фиксированные сборы: по одному на тип (gate - точный title_type или 'any'), самый свежий."""
    result = []
    for fee_type in ('gate', 'environmental', 'virtual_bid'):
        if fee_type == 'gate':
            fee = (pick_active(fees, on_date, lambda f: f.auction == auction and f.fee_type == 'gate'
                               and f.title_type == title_type)
                   or pick_active(fees, on_date, lambda f: f.auction == auction and f.fee_type == 'gate'
                                  and f.title_type == 'any'))
        else:
            fee = pick_active(fees, on_date, lambda f, ft=fee_type: f.auction == auction and f.fee_type == ft)
        if fee is not None:
            result.append(fee)
    return result


def pick_exchange_rate(rates, from_currency, to_currency, on_date):
    """Курс с максимальной датой не позже on_date; курса «из будущего» нет (02-Q5)."""
    candidates = [r for r in rates if r.from_currency == from_currency and r.to_currency == to_currency
                  and r.date <= on_date]
    return max(candidates, key=lambda r: (r.date, r.pk or 0)) if candidates else None


def pick_pension_bracket(brackets, base_uah, on_date):
    """Брекет: min <= база <= max; на общей границе - верхний брекет, затем самый свежий (02-Q2)."""
    base_uah = _d(base_uah)
    candidates = [b for b in brackets
                  if (on_date is None or is_active(b, on_date))
                  and b.min_value_uah <= base_uah and (b.max_value_uah is None or b.max_value_uah >= base_uah)]
    if not candidates:
        return None
    return max(candidates, key=lambda b: (b.min_value_uah, b.valid_from, b.pk or 0))


@dataclass
class RateCatalog:
    auction_fee_tiers: list = field(default_factory=list)
    auction_fixed_fees: list = field(default_factory=list)
    us_land_routes: list = field(default_factory=list)
    ocean_freight: list = field(default_factory=list)
    eu_to_ua: list = field(default_factory=list)
    exchange_rates: list = field(default_factory=list)
    excise_rates: list = field(default_factory=list)
    pension_brackets: list = field(default_factory=list)
    customs_rules: list = field(default_factory=list)


@dataclass
class SelectedRates:
    tier: object = None
    fixed_fees: list = field(default_factory=list)
    us_land: object = None
    ocean: object = None
    eu_to_ua: object = None
    usd_to_uah: object = None
    usd_to_eur: object = None
    excise: object = None
    rule: object = None
    pension_brackets: list = field(default_factory=list)
    missing: list = field(default_factory=list)

    @property
    def applied(self) -> list:
        return [x for x in (self.tier, self.us_land, self.ocean, self.eu_to_ua, self.excise, self.rule) if x] \
            + list(self.fixed_fees)

    @property
    def rates_updated_on(self):
        """Дата последнего обновления применённых ставок (максимум valid_from) - «Ставки оновлено»."""
        dates = [x.valid_from for x in self.applied if getattr(x, 'valid_from', None)]
        return max(dates) if dates else None


def select_rates(catalog: RateCatalog, params: dict, on_date) -> SelectedRates:
    """Подбор тарифов на дату расчёта. Не найденное - в missing (формат view 422 сохраняется)."""
    auction = params['auction']
    member_type = params['member_type']
    payment_type = params['payment_type']
    title_type = params['title_type']
    bid = _d(params['auction_price_usd'])
    loc = params['auction_location'].lower()
    us_port = params['us_port'].lower()
    eu_port = params['eu_port']
    fuel_type = params['fuel_type']
    engine_cc = params['engine_cc']

    sel = SelectedRates()
    sel.tier = lookup_tier(catalog.auction_fee_tiers, auction, bid, member_type, payment_type, title_type, on_date)
    sel.fixed_fees = lookup_fixed_fees(catalog.auction_fixed_fees, auction, title_type, on_date)
    sel.us_land = pick_active(catalog.us_land_routes, on_date,
                              lambda r: r.auction_location.lower() == loc and r.us_port.lower() == us_port)
    sel.ocean = pick_active(catalog.ocean_freight, on_date,
                            lambda r: r.us_port.lower() == us_port and r.eu_port == eu_port)
    sel.eu_to_ua = pick_active(catalog.eu_to_ua, on_date, lambda r: r.eu_port == eu_port)
    sel.usd_to_uah = pick_exchange_rate(catalog.exchange_rates, 'USD', 'UAH', on_date)
    sel.usd_to_eur = pick_exchange_rate(catalog.exchange_rates, 'USD', 'EUR', on_date)
    # Акциз: из подходящих по объёму - с самым большим engine_cc_min, затем самый свежий.
    excise = [r for r in catalog.excise_rates
              if is_active(r, on_date) and r.fuel_type == fuel_type and r.engine_cc_min <= engine_cc
              and (r.engine_cc_max is None or r.engine_cc_max >= engine_cc)]
    sel.excise = max(excise, key=lambda r: (r.engine_cc_min, r.valid_from, r.pk or 0)) if excise else None
    sel.rule = pick_active(catalog.customs_rules, on_date)
    sel.pension_brackets = [b for b in catalog.pension_brackets if is_active(b, on_date)]

    if not sel.tier:
        sel.missing.append(f'AuctionFeeTier для {auction} / {member_type}/{payment_type}/{title_type} / ${bid}')
    if not sel.us_land:
        sel.missing.append(f'UsLandRoute для {params["auction_location"]} → {params["us_port"]}')
    if not sel.ocean:
        sel.missing.append(f'OceanFreightRate для {params["us_port"]} → {eu_port}')
    if not sel.eu_to_ua:
        sel.missing.append(f'EuToUaDeliveryRate для {eu_port}')
    if not sel.usd_to_uah:
        sel.missing.append('ExchangeRate USD→UAH')
    if not sel.usd_to_eur:
        sel.missing.append('ExchangeRate USD→EUR')
    if not sel.excise:
        sel.missing.append(f'CustomsExciseRate для {fuel_type}')
    elif fuel_type in EV_FUEL_TYPES and sel.excise.ev_excise_eur_per_kwh is None:
        sel.missing.append(f'CustomsExciseRate: немає ставки акцизу EV (EUR/кВт·год) для {fuel_type}')
    if not sel.rule:
        sel.missing.append('CustomsCalcRule')
    if not sel.pension_brackets:
        sel.missing.append('PensionFundBracket')
    return sel
