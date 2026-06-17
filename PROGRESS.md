# PROGRESS.md — Живой журнал прогресса

## Статус: ФАЗА 2 ЗАВЕРШЕНА ✓

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
2. **Курс валют**: последняя запись ExchangeRate по дате
3. **Пенсионный сбор**: применяется при каждом расчёте (считаем первой регистрацией)
4. **Акциз для электро**: 1 EUR (символически) — ⚠ ПРОВЕРИТЬ по законодательству
5. **Ставки акциза в seed_rates**: плейсхолдеры — ⚠ ОБЯЗАТЕЛЬНО ПРОВЕРИТЬ
6. **Пенсионный сбор в seed_rates**: 3% / 4% / 5% по шкале — ⚠ ПРОВЕРИТЬ
7. **VIN-провайдеры**: только заглушки (StubVinProvider). Реальная интеграция — Фаза 3.
8. **SQLite в dev**: PostgreSQL — продакшн

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
