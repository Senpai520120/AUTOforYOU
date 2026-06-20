# PROGRESS.md — Живой журнал прогресса

## Статус: ФАЗА 2 ЗАВЕРШЕНА ✓ | Растаможка — реальные ставки ✓ | Реальные источники ✓ | Сетки Copart/IAAI — baseline + E2E верификация ✓

---

## Дальше (очередь задач до продакшена)

| # | Блокер | Что делать |
|---|--------|------------|
| 1 | ~~Ставки растаможки~~ | ✅ Снят — акциз/мито/НДС/ПФ актуальны на янв–июнь 2026 |
| 2 | ~~Тарифы Copart/IAAI~~ | Baseline готов (seed_auction_fees, 50 тиров). ⚠ Калибровать под реальный тариф брокера |
| 3 | **Тарифы фрахта** | UsLandRoute, OceanFreight, EuToUa — реальные котировки от брокера |
| 4 | ~~Живой курс НБУ~~ | ✅ Снят — `fetch_nbu_rates --date YYYYMMDD` обновляет ExchangeRate из bank.gov.ua |
| 5 | **Платные API для истории** | Carfax/BidFax (история ДТП и торгов), Opendatabot (UA реестры) — договоры |
| 6 | **Верификация дилеров** | Задать процедуру проверки `is_verified_dealer` (документы, КЕП) |
| 7 | ~~Платёжный шлюз~~ | ✅ Снят — LiqPay sandbox готов; для продакшена: LIQPAY_SANDBOX=false + реальные ключи |
| 8 | **Прожиточный минимум 2026** | Проверить `LIVING_WAGE_UAH` в `seed_rates.py` на дату деплоя |

---

## Промт 2 — Сетки аукционных сборов Copart/IAAI (завершено 2026-06-20)

### Модели
- [x] `AuctionFeeTier` v2: auction/member_type/payment_type/title_type/bid_min/bid_max/fee_flat/fee_percent
  + `clean()` validation: ровно одно из fee_flat/fee_percent
- [x] `AuctionFixedFee`: auction/fee_type(gate|environmental|virtual_bid)/title_type/amount
- [x] Миграция 0004: DeleteModel старой + CreateModel обеих новых

### Калькулятор
- [x] `AuctionFeeBreakdown` dataclass (buyer_fee/gate/environmental/virtual_bid/total)
- [x] `calc_auction_fees(bid, tier, fixed_fees)` — чистая функция в calculator.py
- [x] `RateSnapshot.auction_fee: AuctionFeeBreakdown` (замена старого AuctionFeeRateSnapshot)
- [x] `LandedCostBreakdown`: auction_fee_usd (total) + 4 sub-компонента
- [x] `_lookup_tier()`: точный title_type → fallback 'any'
- [x] `_lookup_fixed_fees()`: gate по title_type + env + virtual_bid

### Seed
- [x] `seed_auction_fees`: 50 тиров Copart/IAAI + 7 фиксированных сборов
  - Copart public/salvage/secured: 11 flat тиров $0-$499→$75 .. $5000+→10%
  - Copart licensed+broker/secured: flat $100 min + 6%; unsecured: 8%
  - IAAI licensed+broker/secured: flat до $4999 + 8%/$7500+10%
  - Fixed: gate clean $79/salvage $95, env $10, vb $99 (Copart); gate $95, env $15, vb $75 (IAAI)
  - Все строки: `# baseline — сверить с офиц. сеткой и тарифом брокера`
- [x] `seed_rates.py`: удалены старые тиры, ссылка на `seed_auction_fees`

### Админка
- [x] `AuctionFeeTierAdmin`: list_filter по auction/member_type/payment_type/title_type
- [x] `AuctionFixedFeeAdmin`: list_filter по auction/fee_type/title_type

### Тесты (14 новых в промте 2)
- [x] Copart public $3200 salvage → buyer_fee=385, gate=95, env=10, vb=99, total=589
- [x] Copart licensed $8000 → 6% = 480
- [x] Copart public $7500 $5000+ тир → 10% = 750
- [x] IAAI licensed $12000 → 8% = 960 + fixed fees
- [x] Граничные значения bid_min / bid_max / округление %
- [x] Нет фиксированных сборов → gate/env/vb = 0
- [x] Все поля AuctionFeeBreakdown — Decimal

---

## Промт 3 — Landed-cost E2E + фиксы ревью (завершено 2026-06-20)

### Fix 1 — IAAI тир 10% для ставок ≥$7500
- [x] Исправлен `TestIAAIPercentTier`: $12000 теперь тестируется с fee_percent=0.1000 → $1200 (было 0.0800→$960)
- [x] Добавлен тест IAAI 8% тир: $6000 → buyer_fee=$480
- [x] Добавлен `TestIAAITierBoundaryDB` (Django TestCase с реальной БД):
  - $7499 → tier.fee_percent == 0.0800
  - $7500 → tier.fee_percent == 0.1000
  - $12000 calc → buyer_fee=$1200

### Fix 2 — AUCTION_DEFAULT_MEMBER_TYPE в settings
- [x] `AUCTION_DEFAULT_MEMBER_TYPE = 'broker'` добавлен в `core/settings.py` (env-переопределяем)
- [x] `pricing/views.py`: `DEFAULT_MEMBER_TYPE = getattr(settings, 'AUCTION_DEFAULT_MEMBER_TYPE', 'broker')`
- [x] `TestCalculateInputSerializerDefaults`: дефолты member_type='broker', payment_type='secured'

### E2E интеграционный тест
- [x] `TestLandedCostE2ECopartBroker` — полный сценарий Copart broker/salvage/secured $5000 petrol 2.0L 2018:
  - auction_fee_buyer=$300 (6%), total auction_fee=$504 (buyer+gate$95+env$10+vb$99)
  - customs_value_usd=$6800, duty_usd=$680
  - excise_eur=800 (5.0 EUR/100cc × 20 × age_coeff=8)
  - total_usd=$8334 (все 6 компонентов)
  - total_uah > total_usd×rate (акциз+НДС+пенсионный сверху)
  - is_estimate=True, rates_date непустой
- [x] Все тесты зелёные: 58 тестов OK

### Следующий шаг (промт 4)
Верификация дилеров: процедура is_verified_dealer + документы

---

## Фаза 3 — Реальные источники данных (завершено 2026-06-20)

### VIN-декод NHTSA vPIC
- [x] `NHTSAVinDecodeProvider` в `integrations/providers.py` — httpx, без ключа
- [x] Поля NHTSA → Vehicle: Make/Model/ModelYear/DisplacementCC/FuelTypePrimary/BodyClass
- [x] Кэш в VinReport(provider='nhtsa_vpic', demo=False)
- [x] GET /api/v1/vehicles/<vin>/decode/ — реальные данные из NHTSA
- [x] StubVinProvider (история ДТП) не тронут — остаётся на /report/

### Платёжный шлюз LiqPay
- [x] `payments` app: модель Payment (order_id, amount, currency, status, listing FK, purpose)
- [x] `LiqPayClient`: create_checkout (URL + form_data) + decode_callback (проверка подписи SHA1)
- [x] POST /api/v1/payments/liqpay/checkout/ (auth required) → checkout_url
- [x] POST /api/v1/payments/liqpay/callback/ (csrf_exempt, signature check) → pending→completed/failed
- [x] unlock_listing() при completed — разблокирует листинг
- [x] Env: LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY, LIQPAY_SANDBOX=true (dev default)
- [x] .env.example с плейсхолдерами
- [x] Примечание: официальный SDK (liqpay/sdk-python) Python 2 only; протокол реализован напрямую

### Возрастной коэффициент — потолок 15
- [x] `calc_age_coeff()`: `min(15, max(1, год_расчёта − год_выпуска))`
- [x] Тест: авто 20 лет (2006→2026) → коэффициент = 15 (не 20)
- [x] 3 новых теста: cap boundary, exactly 15, below cap

### Курс НБУ (бесплатно, без ключа)
- [x] Management command `fetch_nbu_rates [--date YYYYMMDD]`
- [x] Источник: bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD/EUR&date=YYYYMMDD
- [x] USD/UAH + EUR/UAH → кросс-курс USD/EUR
- [x] Upserts в ExchangeRate с date-specific записями
- [x] Calculator view: ExchangeRate по calc_date (fallback к latest)
- [x] Добавлен опциональный `calculation_date` в CalculateInputSerializer
- [x] В ответе калькулятора: `exchange_rate_date` — дата использованного курса

---

## Пост-Фаза 2 — Реальные ставки растаможки (завершено 2026-06-18)

### Ставки растаможки Украины, актуальны на янв–июнь 2026
- [x] Акциз ДВС: бензин ≤3000 cc = 50 EUR/л, >3000 cc = 100 EUR/л; дизель ≤3500 cc = 75, >3500 cc = 150
- [x] Акциз EV/PHEV: 1 EUR × ёмкость батареи кВт·ч (фиксированная ставка)
- [x] Пошлина: EV/PHEV = 0%; все ДВС из США = 10% (льгота EUR.1 не применяется для US-origin)
- [x] НДС 20% для всех авто, включая EV (льгота EV отменена с 01.01.2026)
- [x] PHEV добавлен как отдельный тип топлива (как EV; уточнить у брокера)
- [x] Hybrid (HEV) = как бензин (уточнить у брокера)
- [x] Пенсионный сбор: пороги 165×/290× прожиточного минимума (3028 грн — ПРОВЕРИТЬ)
- [x] age_coefficient = max(1, год − год_выпуска) — вынесен в calc_age_coeff() с комментарием брокера
- [x] Миграция 0003_excise_rate_real_values: удалены age_bracket поля, добавлены engine_cc_min/max, ev_excise_eur_per_kwh
- [x] 25 тестов зелёные (добавлены: petrol 2000cc/8y, diesel 2000cc/7y, EV 60кВт, US-origin duty, PHEV, age_coeff)
- [x] В ответе калькулятора добавлен rates_validity_date
- [x] Swagger-пример обновлён, warning обновлён

---

## ФАЗА 1 — Backend (завершена)

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

### ШАГ 2 — Vehicle
- [x] App `vehicles`: Vehicle(vin, make, model, year, engine_cc, fuel_type, mileage_km, damage_type, source_auction, lot_number)
- [x] VehicleImage с полем is_primary
- [x] GET /api/v1/vehicles/, /api/v1/vehicles/<id>/

### ШАГ 3 — Тарифные справочники
- [x] AuctionFeeTier, UsLandRoute, OceanFreightRate, EuToUaDeliveryRate
- [x] ExchangeRate (USD/UAH, USD/EUR)
- [x] CustomsExciseRate (акциз × коэфф. возраста; пошлина 10%; НДС 20%)
- [x] PensionFundBracket (прогрессивная шкала)
- [x] Все модели редактируемы в Admin с valid_from/valid_to
- [x] management command `seed_rates`

### ШАГ 4 — Сервис калькулятора
- [x] `pricing/calculator.py`: чистая функция без обращений к БД
- [x] Все деньги — Decimal, никакого float
- [x] RateSnapshot — неизменяемый снимок ставок
- [x] Флаг is_estimate=True на каждом результате
- [x] 12 юнит-тестов (SimpleTestCase), все зелёные

### ШАГ 5 — Calculation + эндпоинт
- [x] Модель Calculation: inputs_snapshot, rates_snapshot, breakdown (JSON), total_usd, total_uah
- [x] POST /api/v1/pricing/calculate/
- [x] GET /api/v1/pricing/rates/

### ШАГ 6 — Listing + каталог
- [x] Модель Listing: FK Vehicle, seller, price, channel (retail/wholesale), status, is_express_buyout
- [x] GET /api/v1/listings/ (фильтры: status, fuel_type, max_price, search)
- [x] GET /api/v1/listings/<id>/
- [x] POST /api/v1/listings/create/

### ШАГ 7 — Swagger / OpenAPI
- [x] drf-spectacular, схема на /api/schema/, UI на /api/docs/
- [x] ENUM_NAME_OVERRIDES для статусов
- [x] 21 задокументированный эндпоинт

---

## ФАЗА 2 — Backend A1-A4 + Frontend B1-B5 (завершена)

### A1 — Shipments (контейнеры)
- [x] App `shipments`: Shipment (container_no, vessel, 7 статусов, M2M vehicles + watchers)
- [x] State machine: VALID_TRANSITIONS dict, метод advance_status() создаёт TrackingEvent
- [x] TrackingEvent (статус, нотатка, фото)
- [x] ShipmentAdmin: inline события, автосоздание события при смене статуса, превью фото
- [x] GET /api/v1/shipments/, GET /api/v1/shipments/<id>/
- [x] GET /api/v1/auth/me/shipments/ (только наблюдаемые текущим юзером)

### A2 — Особистий кабінет (cabinet)
- [x] TrustedShop (owner, name, type: сервіс/маляр/запчастини/інше, contacts, rating 1-5, notes)
- [x] CRUD /api/v1/auth/me/trusted-shops/ + /me/trusted-shops/<id>/
- [x] GET /api/v1/auth/me/calculations/ (история расчётов авторизованного юзера)
- [x] GET /api/v1/auth/profile/ (профиль с ролью и is_verified_dealer)

### A3 — B2B-доска
- [x] Листинги: is_wholesale property (channel == 'wholesale'), is_express_buyout (bool + срок)
- [x] GET /api/v1/b2b/board/ — только wholesale, только верифицированным дилерам/админам
- [x] IsVerifiedDealerOrAdmin permission class
- [x] Сортировка: срочный выкуп первым (-is_express_buyout)

### A4 — VIN-интеграции (заглушки)
- [x] App `integrations`: ABC-провайдеры VinProvider, AuctionHistoryProvider, OpendatabotProvider
- [x] StubVinProvider: демо-данные Toyota Camry, флаг demo=True
- [x] VinReport — кэш в БД (unique_together: vin + provider)
- [x] GET /api/v1/vehicles/<vin>/report/ — проверяет кэш, агрегирует от провайдеров

### B1 — Next.js scaffold
- [x] Next.js 16 App Router, TypeScript, Tailwind CSS
- [x] `lib/types.ts` — все интерфейсы (User, Vehicle, Listing, Calculation, Shipment, TrustedShop...)
- [x] `lib/auth-context.tsx` — AuthProvider, useAuth(), localStorage JWT, auto-refresh
- [x] `api/client.ts` — apiFetch с инжектом Bearer, retry на 401, редирект на /login
- [x] `api/listings.ts`, `api/pricing.ts`, `api/me.ts`
- [x] Header (навигация, B2B только для дилеров), Footer (⚠ предупреждение о тестовых тарифах)
- [x] DemoBanner — обязательный компонент на всех страницах с ценами

### B2 — Каталог объявлений
- [x] `/listings` — каталог с фильтрами (статус, тип топлива, макс. цена, поиск)
- [x] ListingCard (фото, бейдж статуса, бейдж срочного выкупа, объём/пробег/топливо, цена)
- [x] ListingFilters (URL params, Suspense)
- [x] `/listings/[id]` — детальная страница, галерея фото, спецификации, ссылка на калькулятор

### B3 — Калькулятор
- [x] `/calculator` — форма (аукцион, цена, объём, топливо, год, порты)
- [x] DemoBanner обязателен (⚠ Тестові тарифи — розрахунок демонстраційний)
- [x] CalcBreakdown — таблица разбивки USD + UAH по каждой статье
- [x] Prefill из URL params (?price=&engine_cc=&fuel_type=&year=) при переходе из листинга
- [x] Suspense-обёртка для useSearchParams (фикс build-ошибки)

### B4 — Особистий кабінет (frontend)
- [x] `/me` — дашборд: аватар-инициал, email, роль, бейдж "✓ Верифіковано"
- [x] `/me/calculations` — история расчётов (дата, total_usd, total_uah, разбивка)
- [x] `/me/trusted-shops` — полный CRUD партнёров (СТО, маляры, запчасти)
- [x] `/me/shipments` — наблюдаемые контейнеры, прогресс-бар 7 шагов

### B5 — B2B-доска (frontend)
- [x] `/b2b` — гейтинг по роли (is_verified_dealer || role === 'admin')
- [x] Экран "Доступ обмежено" для не-дилеров
- [x] Срочный выкуп — отдельная секция с ⚡ выше обычных лотов

---

## Конфигурация / инфраструктура
- [x] `frontend/.env.local`: NEXT_PUBLIC_API_URL=http://localhost:8000
- [x] `frontend/next.config.ts`: remotePatterns для localhost:8000/media/**
- [x] `requirements.txt`: все зависимости зафиксированы
- [x] Production build: `npm run build` — 12 роутов, 0 ошибок

---

## Допущения (бизнес-дефолты)
1. **Таможенная стоимость**: auction_price + us_land + ocean_freight (без EU→UA)
2. **Курс валют**: ExchangeRate для даты оформления; fallback — последняя запись
3. **Пенсионный сбор**: применяется при каждом расчёте (считаем первой регистрацией)
4. **Акциз для электро**: 1 EUR × кВт·ч (ставки из БД) — ⚠ ПРОВЕРИТЬ по законодательству
5. **Ставки акциза в seed_rates**: актуальны янв–июнь 2026 — проверить у брокера на дату деплоя
6. **Пенсионный сбор в seed_rates**: 3% / 4% / 5% по шкале — ⚠ ПРОВЕРИТЬ
7. **VIN-декод**: NHTSA vPIC — реальные технические данные (demo=false). История ДТП — заглушка.
8. **SQLite в dev**: PostgreSQL — продакшн
9. **LiqPay**: sandbox=true по умолчанию в dev. Для продакшена: LIQPAY_SANDBOX=false.

## Известные ограничения
- Swagger: одно предупреждение об enum-коллизии (CarStatusEnum), 0 ошибок
- Ставки — плейсхолдеры, все расчёты помечены is_estimate=true и DemoBanner
- VIN-репорт — демо-данные, demo=true в ответе и в кэше

---

## URL-карта (итог, 21 эндпоинт)

```
# Auth
POST /api/v1/auth/register/
POST /api/v1/auth/token/
POST /api/v1/auth/token/refresh/
GET  /api/v1/auth/profile/

# Cabinet
GET  /api/v1/auth/me/calculations/
GET  /api/v1/auth/me/shipments/
GET  /api/v1/auth/me/trusted-shops/
POST /api/v1/auth/me/trusted-shops/
GET  /api/v1/auth/me/trusted-shops/<id>/
PUT  /api/v1/auth/me/trusted-shops/<id>/
DEL  /api/v1/auth/me/trusted-shops/<id>/

# Vehicles
GET  /api/v1/vehicles/
GET  /api/v1/vehicles/<id>/
GET  /api/v1/vehicles/<vin>/report/

# Pricing
POST /api/v1/pricing/calculate/
GET  /api/v1/pricing/rates/

# Listings
GET  /api/v1/listings/
GET  /api/v1/listings/<id>/
POST /api/v1/listings/create/

# B2B (верифіковані дилери)
GET  /api/v1/b2b/board/

# Shipments
GET  /api/v1/shipments/
GET  /api/v1/shipments/<id>/

# Docs
GET  /api/schema/
GET  /api/docs/

# Legacy
GET  /api/calculate/
GET  /api/list/
```

---

## Frontend роути (12)

```
/               — головна (hero + 3 фічі)
/listings       — каталог з фільтрами
/listings/[id]  — деталі + галерея
/calculator     — калькулятор «під ключ»
/login          — вхід
/register       — реєстрація
/me             — кабінет
/me/calculations — історія розрахунків
/me/trusted-shops — партнери (CRUD)
/me/shipments   — контейнери + прогрес-бар
/b2b            — B2B-дошка (тільки дилери)
/_not-found     — 404
```
