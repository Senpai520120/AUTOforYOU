# AUTOforYOU — Целевая архитектура Фазы 1

## URL-пространство (v1)
```
/api/v1/auth/register/          POST  — регистрация
/api/v1/auth/token/             POST  — получить JWT (login)
/api/v1/auth/token/refresh/     POST  — обновить JWT

/api/v1/vehicles/               GET   — список Vehicle
/api/v1/vehicles/<id>/          GET   — детали Vehicle

/api/v1/pricing/calculate/      POST  — калькулятор (сохраняет Calculation)
/api/v1/pricing/rates/          GET   — текущие активные тарифы

/api/v1/listings/               GET   — каталог (фильтры: status, fuel_type, max_price)
/api/v1/listings/<id>/          GET   — детали Listing
```

## Модели

### users.CustomUser
```
id, email (unique, username), role (buyer/dealer/admin),
is_verified_dealer, phone, created_at
```

### vehicles.Vehicle
```
id, vin (unique), make, model, year,
engine_cc (IntegerField, объём в см³),
fuel_type (petrol/diesel/electric/hybrid),
mileage_km, damage_type, source_auction (copart/iaai),
lot_number, created_at
```

### vehicles.VehicleImage
```
id, vehicle FK, image, is_primary, uploaded_at
```

### pricing.AuctionFeeTier
```
id, auction (copart/iaai), min_price, max_price (null=unbounded),
fee_fixed, fee_pct, valid_from, valid_to
```

### pricing.UsLandRoute
```
id, auction_location, us_port, cost_usd, valid_from, valid_to
```

### pricing.OceanFreightRate
```
id, us_port, eu_port (klaipeda/gdansk), cost_usd, valid_from, valid_to
```

### pricing.EuToUaDeliveryRate
```
id, eu_port, cost_usd, valid_from, valid_to
```

### pricing.ExchangeRate
```
id, from_currency, to_currency, rate (Decimal), date
```

### pricing.CustomsExciseRate
```
id, fuel_type, eur_per_100cc,   # ПРОВЕРИТЬ по действующему законодательству
age_0_1_coeff, age_1_3_coeff, age_3_5_coeff,
age_5_7_coeff, age_7_plus_coeff,
duty_rate, vat_rate, valid_from, valid_to
```

### pricing.PensionFundBracket
```
id, min_value_uah, max_value_uah (null=unbounded),
rate,   # ПРОВЕРИТЬ по действующему законодательству
valid_from, valid_to
```

### pricing.Calculation
```
id, user FK (null=anonymous),
inputs_snapshot (JSONField),
rates_snapshot (JSONField),
breakdown (JSONField),
total_usd, total_uah,
is_estimate (bool, always True),
created_at
```

### listings.Listing
```
id, vehicle FK, seller FK (CustomUser),
price, currency (USD/UAH/EUR),
channel (retail/wholesale),
status (in_transit/in_stock/sold),
repair_description,
calculation FK (null),
created_at, updated_at
```

## Сервис калькулятора (pricing/calculator.py)
```python
def calculate_landed_cost(inputs: LandedCostInputs, rates: RateSnapshot) -> LandedCostBreakdown:
    ...
```
- Чистая функция, без БД, детерминированная
- Принимает dataclass с входами и снимком ставок
- Возвращает dataclass с полным breakdown (каждая статья расходов)

## Слои
```
Views (DRF) → Serializers → Service (calculator.py) → Models
                                    ↑
                           Rate models (DB → snapshot)
```
