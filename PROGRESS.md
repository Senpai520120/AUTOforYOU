# PROGRESS.md — Живой журнал прогресса

## Статус: ФАЗА 1 ЗАВЕРШЕНА ✓

## Выполнено

### ШАГ 0 — Подготовка
- [x] Прочитан весь существующий код (settings, models, views, admin, urls)
- [x] Установлен djangorestframework-simplejwt 5.5.1
- [x] Созданы CLAUDE.md, ARCHITECTURE.md, PROGRESS.md
- [x] Удалена старая db.sqlite3 (чистая миграция)

### ШАГ 1 — CustomUser + JWT
- [x] App `users`: CustomUser(email, role: buyer/dealer/admin, is_verified_dealer, phone)
- [x] JWT через SimpleJWT: /api/v1/auth/register/, /token/, /token/refresh/, /profile/
- [x] Кастомная UserAdmin с fieldsets
- [x] AUTH_USER_MODEL = 'users.CustomUser'
- [x] cars/models.py обновлён на settings.AUTH_USER_MODEL

### ШАГ 2 — Vehicle
- [x] App `vehicles`: Vehicle(vin, make, model, year, engine_cc, fuel_type, mileage_km, damage_type, source_auction, lot_number)
- [x] VehicleImage с полем is_primary
- [x] VehicleAdmin с inline фотографиями
- [x] GET /api/v1/vehicles/, /api/v1/vehicles/<id>/

### ШАГ 3 — Тарифные справочники
- [x] AuctionFeeTier (аукцион, диапазон цен, фиксированный сбор + %)
- [x] UsLandRoute (аукцион_локация → порт США, стоимость)
- [x] OceanFreightRate (порт США → порт ЕС: klaipeda/gdansk)
- [x] EuToUaDeliveryRate (порт ЕС → Украина)
- [x] ExchangeRate (USD/UAH, USD/EUR)
- [x] CustomsExciseRate (акциз по типу топлива × объём × коэфф. возраста; пошлина 10%; НДС 20%)
- [x] PensionFundBracket (прогрессивная шкала в UAH)
- [x] Все модели редактируемы в Admin с valid_from/valid_to
- [x] management command `seed_rates` — начальное наполнение

### ШАГ 4 — Сервис калькулятора
- [x] `pricing/calculator.py`: чистая функция calculate_landed_cost(inputs, rates) → breakdown
- [x] Все деньги — Decimal, никакого float
- [x] RateSnapshot — неизменяемый снимок ставок для расчёта
- [x] Акциз для электро — символический 1 EUR (ПРОВЕРИТЬ)
- [x] Флаг is_estimate=True на каждом результате
- [x] 12 юнит-тестов, все зелёные (без БД, SimpleTestCase)
  - test_auction_fee_is_10_percent ✓
  - test_customs_value ✓
  - test_duty_is_10_percent_of_customs_value ✓
  - test_excise_calculation ✓
  - test_vat_is_20_percent ✓
  - test_is_estimate_always_true ✓
  - test_total_usd_components ✓
  - test_to_dict_serializable ✓
  - test_electric_excise_is_symbolic ✓
  - test_all_monetary_fields_are_decimal ✓
  - test_zero_price ✓

### ШАГ 5 — Calculation + эндпоинт
- [x] Модель Calculation: inputs_snapshot, rates_snapshot, breakdown (JSON), total_usd, total_uah, is_estimate, FK User (nullable)
- [x] POST /api/v1/pricing/calculate/ — принимает параметры авто, ищет активные тарифы в БД, считает, сохраняет снимок
- [x] GET /api/v1/pricing/rates/ — активные тарифы

### ШАГ 6 — Listing + каталог
- [x] Модель Listing: FK Vehicle, FK seller (CustomUser), price+currency, channel (retail/wholesale), status (in_transit/in_stock/sold), repair_description, FK Calculation
- [x] GET /api/v1/listings/ — с фильтрами: status, channel, fuel_type, max_price, currency, search (make/model/vin)
- [x] GET /api/v1/listings/<id>/ — детали
- [x] POST /api/v1/listings/create/ — создать объявление (только авторизованным)

## Допущения (бизнес-дефолты)
1. **Таможенная стоимость**: auction_price + us_land + ocean_freight (без EU→UA доставки)
2. **Курс валют**: последняя запись ExchangeRate с нужной парой (по дате)
3. **Пенсионный сбор**: применяется при каждом расчёте (считаем первой регистрацией)
4. **Акциз для электро**: 1 EUR (символически), ПРОВЕРИТЬ по законодательству
5. **Ставки акциза в seed_rates**: плейсхолдеры (0.7467 EUR/100cc для бензина, 1.0304 для дизеля) — ОБЯЗАТЕЛЬНО ПРОВЕРИТЬ
6. **Пенсионный сбор в seed_rates**: 3% / 4% / 5% по шкале в UAH — ПРОВЕРИТЬ
7. **Брекеты пенсионного сбора**: 0–375k UAH / 375k–750k / 750k+ — ПРОВЕРИТЬ
8. **SQLite в dev**: psycopg2-binary установлен, PostgreSQL — продакшн
9. **cars app**: legacy, Car.owner → settings.AUTH_USER_MODEL. Не мигрирует данные на Vehicle автоматически.

## Проблемы / решения
- django_filters не установлен → убрал импорт, фильтрация через query_params вручную
- Encoding output в Windows консоли → cp1251 артефакты, данные вставлены корректно (проверено через Python)

## URL-карта (итог)
```
POST /api/v1/auth/register/
POST /api/v1/auth/token/
POST /api/v1/auth/token/refresh/
GET  /api/v1/auth/profile/

GET  /api/v1/vehicles/
GET  /api/v1/vehicles/<id>/

POST /api/v1/pricing/calculate/
GET  /api/v1/pricing/rates/

GET  /api/v1/listings/
GET  /api/v1/listings/<id>/
POST /api/v1/listings/create/

# Legacy
GET  /api/calculate/
GET  /api/list/
```
