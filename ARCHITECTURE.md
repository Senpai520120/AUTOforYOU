# AUTOforYOU — Архитектура

## C2C-модуль (C2C-промт 1)

### Рішення: LocalListing — окремий додаток, не розширення Listing

Існуючий `listings.Listing` = імпортний каталог (авто з США, Copart/IAAI). Він залишається без змін.
`local_listings.LocalListing` = місцеві оголошення від користувачів (стиль Auto.ria). Це **окремий Django-додаток** зі своїми моделями, серіалізаторами, URLs та фільтрами.

**Чому окремий додаток:** різна природа даних (імпорт vs. C2C), різна логіка статусів, різні ендпоінти, майбутня модерація/монетизація не перетинаються з імпортним каталогом.

### Моделі C2C

#### local_listings.Region / City (справочник)
```
Region: name (unique), slug
City:   region FK, name, slug  # unique_together (region, slug)
```
- Засівається командою `seed_regions` (25 областей + 96 міст КАТОТТГ-lite)
- # Неповний довідник: дозасіяти повним КАТОТТГ

#### local_listings.LocalListing
```
owner FK (CustomUser), make, model, year, mileage_km, engine_cc (nullable)
fuel_type: petrol/diesel/electric/hybrid/gas
transmission: auto/manual/cvt/robot
body_type: sedan/suv/hatchback/wagon/coupe/minivan/pickup/convertible/other
condition: new/used/damaged
price (Decimal), currency (UAH/USD/EUR), price_type (fixed/negotiable)
region FK, city FK
description (text), status, seller_type, contact_phone (private!)
status: draft/active/pending*/rejected*/expired*/sold/hidden
        * TODO: C2C-промт 2 (модерація), C2C-промт 5 (строк дії)
contact_phone — НЕ входить до публічного списку; детальний захист — C2C-промт 6
```
- Індекси БД: status, make, year, price, region, fuel_type

#### local_listings.LocalListingImage
```
listing FK, image (ImageField, nullable), source_url, is_primary
```

### URL-простір C2C (v1)
```
GET/POST  /api/v1/local/listings/              # список активних / створити
GET       /api/v1/local/listings/<id>/         # деталь
PATCH     /api/v1/local/listings/<id>/         # редагувати (тільки власник)
DELETE    /api/v1/local/listings/<id>/         # видалити (тільки власник)
GET       /api/v1/local/vin-prefill/<vin>/     # NHTSA vPIC автозаповнення (безкоштовно)
GET       /api/v1/local/regions/               # список областей
GET       /api/v1/local/regions/<id>/cities/   # міста за областю
```

### Фільтри LocalListing
make, model, year_min/max, price_min/max, fuel_type, transmission, body_type,
region, city, mileage_max, search (make/model/description), ordering (-created_at/created_at/price/-price)

### Ліміт оголошень
`LOCAL_LISTING_MAX_ACTIVE` (env, дефолт 10) — перевіряється при POST. Повний антиспам — C2C-промт 6.

### Модерація (C2C-промт 2) — готово

**Статус-машина**: `pending` → `active` (approve) або `rejected` (reject + причина).
Власник може знімати (`hidden`) або позначати проданим (`sold`).

**Ремодерація**: суттєва правка `active` → повертає в `pending`.
Суттєві поля: `{make, model, year, price, description}`.
Будь-яка правка `rejected` → повертає в `pending` (власник виправив).

**Згода з правилами**: `agreed_to_rules` + `agreed_to_rules_at`. Без згоди → 400.
Текст правил — заглушка, повна версія у C2C-промті 7.

**Сервіс** (`local_listings/services.py`):
- `approve_listing(listing, admin)` → active + email + Telegram
- `reject_listing(listing, admin, reason)` → rejected + збереження причини + email + Telegram

**Admin**:
- `PendingLocalListingProxy` → окрема секція «Черга модерації» (тільки pending, sorted by created_at)
- Дія «Одобрити» (масова, без форми)
- Дія «Відхилити» → проміжна HTML-форма з полем причини відхилення

**API**: `GET /api/v1/local/my-listings/` — всі оголошення власника (всі статуси).
`rejection_reason` видно тільки власнику та адміну.

### Що далі (наступні C2C-промти)
- C2C-промт 3: повідомлення між покупцем і продавцем
- C2C-промт 4: верифікація дилерів (LocalListing.seller_type=dealer)
- C2C-промт 5: строк дії оголошення (expired), продовження
- C2C-промт 6: захист контактів (телефон тільки авторизованим, антиспам)
- C2C-промт 7: юридичні правила розміщення (замінити заглушку agreed_to_rules)

---

## QA и E2E-тесты (промт 14)
- **Backend E2E** (`tests/test_e2e.py`, 38 тестов): критичные пути целиком через APIClient.
  - Auth chain: регистрация (с consent) → JWT → профиль
  - Калькулятор: полный landed-cost (Copart broker $5 000, все статьи, total = сумма, is_estimate=true)
  - LiqPay: checkout → valid callback → listing unlocked; invalid sig → 400, listing intact; duplicate → idempotent
  - B2B гейтинг: anon/buyer → 403/404; verified dealer/admin → 200
  - Dealer flow: apply → admin approves → is_verified_dealer=True → wholesale доступен
  - Throttle: `ScopedRateThrottle` deny → 429 для /registry/
- **Frontend E2E** (`frontend/e2e/`, Playwright `@playwright/test`):
  - `catalog.spec.ts`: каталог → калькулятор → 404-страница
  - `register.spec.ts`: чекбокс consent присутствует, required, ссылки /terms и /privacy, footer-ссылки
  - Требует: `npx playwright install chromium` + работающий фронт (`npm run dev`) + бэкенд (`runserver`)
  - Запуск: `npm run test:e2e` (из `frontend/`)
- **Итог**: 199 backend-тестов OK; TypeScript 0 ошибок
- **Блокер перед продом**: живая проверка LiqPay в sandbox на публичном URL (см. `docs/PRODUCTION_ROADMAP.md`)

## Юридические страницы (промт 13)
- **Шаблоны**: `/terms`, `/privacy`, `/cookies` — три отдельные Next.js Server Component страницы на украинском языке. Каждая начинается с янтарного баннера «Шаблон — потребує перевірки юристом». **Перед продакшеном: юридическая проверка обязательна.**
- **Согласие с условиями**: `CustomUser.agreed_to_terms_at` (DateTimeField, null=True). `RegisterSerializer` принимает `agreed_to_terms: bool`; при False/отсутствии → 400; при True → устанавливает `agreed_to_terms_at = timezone.now()` в `create()`. Дата согласия фиксируется в БД.
- **Cookie-баннер**: `CookieBanner.tsx` — клиентский компонент, появляется при первом визите (localStorage). Две опции: «Лише необхідні» / «Прийняти всі». Состояние сохраняется 1 год в `localStorage('cookie_consent')`.
- **Footer**: юридические ссылки через Next.js `<Link>` в `<nav aria-label="Юридичні документи">`.
- **Форма регистрации**: обязательный чекбокс с двумя ссылками (/terms, /privacy, `target="_blank"`); `agreed_to_terms: true` передаётся на бэкенд.
- **Robots**: все три страницы — `robots: { index: false }` (не индексируются до юридической проверки).

## Frontend SEO + полировка (промт 12)
- **Метаданные**: `metadataBase` + title template в layout. `generateMetadata` на странице листинга — Server Component с OG-тегами (title/description/og:image/canonical). Остальные страницы: статические `metadata` экспорты или route-level layouts.
- **Telegram-шеринг**: листинг, опубликованный ботом → при вставке URL в Telegram-чат показывается превью: фото авто + название + цена.
- **Slug URL**: `/listings/42-toyota-camry-2020` — человекочитаемый, `parseInt()` возвращает ID.
- **Sitemap**: `app/sitemap.ts` — динамический (статика + активные листинги, revalidate 1h).
- **Robots**: Allow публичные страницы; Disallow кабинет/B2B/API/admin.
- **404/Error**: кастомные `not-found.tsx`, `error.tsx`, `global-error.tsx` с кнопкой «Повторити».
- **Скелетоны**: `Skeleton.tsx`, `loading.tsx` для каталога/карточки/кабинета — нет «мигания» при загрузке.
- **DemoBanner**: `NEXT_PUBLIC_DEMO_MODE=false` выключает баннер когда тарифы реальные; флаг в `.env`.
- **Изображения**: `source_url` (лот-импорт) как fallback к `image`. SVG-плейсхолдер. `sizes`, `priority`.
- **a11y**: `focus:ring`, `aria-*`, `role=alert`, семантические теги.

## Telegram-бот (промт 11)
- **Отдельный процесс**: `python manage.py run_bot` — polling-режим (dev/prod без SSL).
  Прод: `set_webhook https://yourdomain.com/api/v1/telegram/webhook/` → webhook через Django.
- **Включается токеном**: без `TELEGRAM_BOT_TOKEN` — бот не стартует; сайт и API не затронуты.
- **Привязка аккаунта**: `GET /api/v1/telegram/link-token/` → JWT-защищённый эндпоинт генерирует
  `TelegramLinkToken` (UUID, 30 мин, одноразовый) и deep-link `t.me/<bot>?start=link_<uuid>`.
  `/start link_<uuid>` в боте записывает `CustomUser.telegram_id`, помечает токен `used=True`.
- **Middleware** (`UserBindingMiddleware`): по `telegram_id` находит Django-пользователя,
  кладёт в `data['telegram_user']` / `data['is_linked']`; без привязки — только `/start`, `/help`.
- **Команды**: `/start` (+ deeplink), `/help`, `/latest` (3–5 свежих retail-листингов с фото/ценой).
- **Уведомления** (`integrations.tasks.send_notification`): отправляет привязанному пользователю
  через `Bot.send_message`; не привязан / нет токена → no-op.
  Триггеры: смена статуса Shipment, одобрение/отклонение заявки дилера.
- **Автопостинг** (`telegram_bot.tasks.post_listing_to_channel`): новый retail-листинг → пост в
  `TELEGRAM_CHANNEL_ID`; `is_express_buyout` → `TELEGRAM_B2B_CHANNEL_ID` (или основной).
  Throttling обязателен: пауза 3 с между постами, ретрай на `TelegramRetryAfter`.
- **Webhook**: `POST /api/v1/telegram/webhook/` проверяет `X-Telegram-Bot-Api-Secret-Token`.
- **Docker-compose**: отдельный контейнер `bot:` (промт 15, docker-compose).
- **Env**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_CHANNEL_ID`,
  `TELEGRAM_B2B_CHANNEL_ID` (опц.), `TELEGRAM_WEBHOOK_SECRET` (прод), `SITE_URL`.

## Celery — фоновые задачи (промт 10)
- **Брокер**: `REDIS_URL` → Redis; нет `REDIS_URL` ИЛИ `DEBUG=True` → `CELERY_TASK_ALWAYS_EAGER=True` (синхронный режим, воркер не нужен — dev и тесты работают без Redis).
- **Расписание**: `django-celery-beat` с `DatabaseScheduler`; расписание хранится в БД, правится из админки.
- **Задачи**:
  - `pricing.tasks.fetch_nbu_rates_task` — ежедневно в 09:00 (Kyiv), ретрай ×3 при `URLError`. **После записи явно сбрасывает кэш `pricing:exchange_rates`** (промт 9).
  - `integrations.tasks.import_lot_task` — импорт одного лота через Apify; идемпотентен по VIN; ретрай ×3 при сетевых ошибках.
  - `integrations.tasks.send_notification` — заглушка Telegram (реализация — промт 11).
- **Prod-команды**: `celery -A core worker -l info` + `celery -A core beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler`.
- **Flower** (опционально, dev): `pip install flower && celery -A core flower`.

## Кэш и производительность (промт 9)
- **Кэш-бэкенд**: `REDIS_URL` → django-redis; не задан → LocMemCache (dev без Redis).
- **Тарифные справочники кэшируются**: AuctionFeeTier, AuctionFixedFee, логистика, ExchangeRate, акциз, пенсионный сбор — TTL 24ч. `CalculateView` делает 0 DB-запросов на cache hit (было 8+).
- **Автоматическая инвалидация**: `post_save`/`post_delete` на каждой модели сбрасывает соответствующий ключ. Правка ставки в админке → следующий расчёт берёт новое значение без перезапуска.
- **DB-индексы**: Listing — `(status)`, `(channel)`, `(channel, status)`, `(price)`; Vehicle — `(fuel_type)`. VIN уже уникальный.
- **N+1 устранён**: ShipmentListSerializer.vehicle_count использует prefetch cache. Каталог листингов = 3 DB-запроса независимо от числа объектов (доказано `assertNumQueries`).

## Безопасность (промт 8)
- **Throttling**: `AnonRateThrottle` 60/hr + `UserRateThrottle` 300/hr глобально. Дорогие платные эндпоинты (`/registry/`, `/decode/`) — отдельный `ScopedRateThrottle` scope `expensive` 10/hr. Лимиты env-overridable (`THROTTLE_ANON_RATE`, `THROTTLE_USER_RATE`, `THROTTLE_EXPENSIVE_RATE`).
- **Auth на /registry/**: только авторизованные пользователи (Opendatabot платный).
- **JWT**: access 15 мин, refresh 7 дней, blacklist при ротации. Logout-эндпоинт: `POST /api/v1/auth/token/logout/`.
- **Security-заголовки**: HSTS, SSL redirect, secure cookies, X-Frame-Options=DENY, NOSNIFF — только при `DEBUG=False` (в dev localhost без https не ломается).
- **CORS**: перед продом задать `CORS_ALLOWED_ORIGINS=https://yourdomain.com,...` в env.
- **ALLOWED_HOSTS**: перед продом задать `ALLOWED_HOSTS=yourdomain.com,...` в env.

## Инфраструктура (промт 7)
- **БД**: `DATABASE_URL` не задан → SQLite (dev, без настройки). Задан → PostgreSQL (prod).
- **Медиа/S3**: S3-переменные не заданы → `media/` локально (dev). Заданы → AWS S3 / Cloudflare R2.
- **Пакеты**: `dj-database-url`, `django-storages[s3]`, `boto3` добавлены в requirements.txt.
- **Документация**: `DEPLOY_NOTES.md` — пошаговая инструкция для продакшен-деплоя.

## ⛔ ЗАПУСК ЗАБЛОКИРОВАН ДО (финальный список):
1. ~~**Реальные ставки растаможки**~~ — ✅ СНЯТ (акциз, пошлина, НДС, пенсионный сбор актуальны на янв–июнь 2026; финал у брокера)
2. **Baseline-сетки Copart/IAAI** — ✅ BASELINE ГОТОВО (seed_auction_fees, 50 тиров).
   ✅ E2E формула верифицирована: Copart broker $5000 petrol 2.0L 2018 → total_usd=$8334, excise=800 EUR.
   ✅ Граничные тиры IAAI ($7499→8%, $7500→10%) — протестированы в TestIAAITierBoundaryDB.
   ✅ AUCTION_DEFAULT_MEMBER_TYPE=broker выведен в settings.py (env-переопределение).
   ⚠ Требует калибровки под реальный тариф брокера — не снят полностью.
   **Тарифы фрахта** — UsLandRoute, OceanFreight, EuToUa — реальные котировки от брокера
3. ~~**VIN-декод (технические данные)**~~ — ✅ СНЯТ (NHTSA vPIC, бесплатно, без ключа, GET /api/v1/vehicles/<vin>/decode/)
   ⚠ История ДТП остаётся заглушкой — нужен Carfax/BidFax (платный, /report/)
4. **Реальные API-ключи для истории** — BidFax (история торгов), Carfax/CarVertical (ДТП) — нужен договор
   ~~Opendatabot~~ — ✅ СНЯТ (реальный с OPENDATABOT_API_KEY / demo-режим без ключа, GET /api/v1/vehicles/<vin>/registry/)
5. ~~**Верификация дилеров**~~ — ✅ СНЯТ (DealerApplication + approve/reject actions + B2B гейтинг)
6. ~~**Платёжный шлюз**~~ — ✅ СНЯТ после теста sandbox (LiqPay: checkout + webhook, /api/v1/payments/)
   ⚠ Для продакшена: заменить LIQPAY_SANDBOX=false и вставить реальные ключи
7. ~~**Курс НБУ**~~ — ✅ СНЯТ (management command fetch_nbu_rates, бесплатно, без ключа)

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
GET  /api/v1/vehicles/<vin>/report/    ← A4 (заглушка: Carfax/BidFax)
GET  /api/v1/vehicles/<vin>/decode/    ← РЕАЛЬНЫЙ (NHTSA vPIC, без ключа)
GET  /api/v1/vehicles/<vin>/registry/ ← РЕАЛЬНЫЙ (Opendatabot UA реестры; ?plate= для поиска по номеру)

# Lots import                          ← промт 6 (Manual — рабочий MVP; Apify — заглушка до токена)
POST /api/v1/lots/import/             ← только admin (ManualLotProvider / ApifyLotProvider)

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

# Payments (LiqPay)
POST /api/v1/payments/liqpay/checkout/ ← создать платёж (auth required)
POST /api/v1/payments/liqpay/callback/ ← webhook от LiqPay (csrf_exempt, signature check)

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

### integrations.RegistryReport (кэш UA реестров)
```
id, vin (nullable), plate (nullable), provider ('opendatabot'), payload (JSONField), demo (bool), created_at
```

### vehicles.VehicleImage — новые поля (промт 6)
```
source_url (CharField, blank) — URL внешнего фото до переноса в S3 (промт 7)
image — теперь nullable (blank/null)
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
