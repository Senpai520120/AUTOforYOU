# AUTOforYOU — Архитектура

## ⛔ ЗАПУСК ЗАБЛОКИРОВАН ДО:
1. ~~**Реальные ставки растаможки**~~ — ✅ СНЯТ (акциз, пошлина, НДС, пенсионный сбор актуальны на янв–июнь 2026; финал у брокера)
2. **Реальные тарифы фрахта/логистики** — Copart buyer fees, реальные ставки
   UsLandRoute, OceanFreight, EuToUa (обновить seed_rates или внести вручную)
3. **Реальные API-ключи интеграций** — VinCheck/CarVertical (VIN-отчёты),
   BidFax (история торгов), Opendatabot (UA реестры)
4. **Верификация дилеров** — процедура подтверждения is_verified_dealer
5. **Платёжный шлюз** — не входит в Фазу 2, но нужен до продакшена

---

## Фаза 1 — ЗАВЕРШЕНА ✓
CustomUser, Vehicle, Listing, Calculation, справочники тарифов,
калькулятор «под ключ», Swagger

## Фаза 2 — ТЕКУЩАЯ СЕССИЯ

### A. Backend
- A1. Shipment + TrackingEvent (логистика контейнеров)
- A2. Личный кабинет байера (история расчётов, TrustedShop, мои контейнеры)
- A3. B2B закрытый клуб (wholesale-гейтинг, доска, is_express_buyout)
- A4. Интеграции-стабы (VinProvider, AuctionHistoryProvider, OpendatabotProvider)

### B. Frontend (Next.js)
- B1. Каркас + JWT API-клиент + layout
- B2. Каталог листингов + страница авто
- B3. Калькулятор (с обязательным demo-баннером)
- B4. Личный кабинет
- B5. B2B-доска

---

## URL-пространство (v1) — полная карта

```
# Auth
POST /api/v1/auth/register/
POST /api/v1/auth/token/
POST /api/v1/auth/token/refresh/
GET  /api/v1/auth/profile/

# Vehicles
GET  /api/v1/vehicles/
GET  /api/v1/vehicles/<id>/
GET  /api/v1/vehicles/<vin>/report/    ← A4

# Pricing
POST /api/v1/pricing/calculate/
GET  /api/v1/pricing/rates/

# Listings
GET  /api/v1/listings/
GET  /api/v1/listings/<id>/
POST /api/v1/listings/create/

# Shipments                            ← A1
GET  /api/v1/shipments/
GET  /api/v1/shipments/<id>/

# Personal cabinet                     ← A2
GET  /api/v1/me/calculations/
GET  /api/v1/me/shipments/
GET/POST/PUT/DELETE /api/v1/me/trusted-shops/
GET/PUT/DELETE      /api/v1/me/trusted-shops/<id>/

# B2B                                  ← A3
GET  /api/v1/b2b/board/

# Docs
GET  /api/schema/
GET  /api/docs/
GET  /api/redoc/
```

---

## Новые модели Фазы 2

### shipments.Shipment
```
id, container_no (unique), vessel, us_warehouse, departure_port_us,
arrival_port_eu (klaipeda/gdansk), eta, status (state-machine),
vehicles M2M Vehicle, created_at
```

Статусы: at_us_warehouse → loading → in_ocean →
          at_eu_port → on_truck_to_ua → cleared → delivered

### shipments.TrackingEvent
```
id, shipment FK, status, note, photo (nullable), created_at
```

### users.TrustedShop
```
id, owner FK (CustomUser), name,
type (service/painter/parts/other),
contacts, rating (1-5), notes, created_at
```

### integrations.VinReport (кэш)
```
id, vin, provider, report_data (JSONField), demo (bool), created_at
```

### listings.Listing — новые поля
```
is_express_buyout (bool, default False)
express_buyout_until (DateTimeField, null)
```

---

## Структура frontend/
```
frontend/
├── src/
│   ├── app/                    # Next.js App Router
│   │   ├── layout.tsx          # Root layout (header/footer)
│   │   ├── page.tsx            # Home → redirect to /listings
│   │   ├── listings/
│   │   │   ├── page.tsx        # Каталог
│   │   │   └── [id]/page.tsx   # Детали авто
│   │   ├── calculator/
│   │   │   └── page.tsx        # Калькулятор + demo-баннер
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   ├── me/
│   │   │   ├── page.tsx        # Личный кабинет
│   │   │   ├── calculations/page.tsx
│   │   │   ├── trusted-shops/page.tsx
│   │   │   └── shipments/page.tsx
│   │   └── b2b/page.tsx        # B2B-доска (dealer only)
│   ├── api/                    # API-клиент
│   │   ├── client.ts           # JWT fetch wrapper + refresh
│   │   ├── auth.ts
│   │   ├── listings.ts
│   │   ├── vehicles.ts
│   │   ├── pricing.ts
│   │   ├── shipments.ts
│   │   └── me.ts
│   ├── components/
│   │   ├── layout/             # Header, Footer, Nav
│   │   ├── listings/           # ListingCard, ListingFilters
│   │   ├── calculator/         # CalcForm, CalcBreakdown, DemoBanner
│   │   └── ui/                 # Button, Input, Badge, Spinner
│   └── lib/
│       ├── auth-context.tsx    # AuthProvider + useAuth hook
│       └── types.ts            # Shared TypeScript types
├── public/
├── package.json
├── tailwind.config.ts
└── next.config.ts
```

## Слои
```
Next.js Pages → api/ client (JWT) → Django DRF API
                                          ↓
                              Services (calculator.py)
                                          ↓
                              Models (DB)
```
