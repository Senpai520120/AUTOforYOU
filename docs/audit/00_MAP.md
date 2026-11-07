# 00_MAP — карта репозитория AUTOforYOU (фаза A аудита)

Снимок: ветка `finish-site`, коммит `d4cbfab`, 2026-09-25. Код не менялся.
Считались только файлы под git (`git ls-files`), без миграций, `venv/`, `node_modules/`, `.next/`, медиа, дампов.
Числа строк — `wc -l`.

> Замечание: в `.claude/worktrees/agent-a0e9aa80/` лежит полная копия репозитория (git worktree на `4ef27f4`, ветка `worktree-agent-a0e9aa80`). При grep по репо она дублирует результаты — её нужно исключать (или удалить worktree).

---

## 1. Дерево каталогов и строки

### 1.1 Бэкенд (Python, без миграций)

Итого Python: **14 693** строки, из них тесты **5 361**, продовый код **~9 330**.

| Приложение | Всего | Из них тесты |
|---|---:|---:|
| local_listings | 2 761 | 1 092 |
| pricing | 2 700 | 917 |
| integrations | 1 656 | 590 |
| telegram_bot | 1 153 | 515 |
| users | 1 000 | 397 |
| tests/ (корень) | 875 | 875 |
| deals | 787 | 321 |
| messaging | 765 | 213 |
| payments | 521 | 66 |
| core | 517 | 0 |
| listings | 460 | 166 |
| shipments | 376 | 99 |
| reports | 312 | 106 |
| favorites | 208 | 0 |
| saved_searches | 183 | 0 |
| cars (legacy) | 146 | 2 |
| notifications | 129 | 0 |
| vehicles | 122 | 2 |
| manage.py | 22 | — |

```
manage.py                                   22
core/                                      517
  __init__.py 3 · asgi.py 16 · wsgi.py 16 · celery.py 9
  settings.py 431 · urls.py 42
users/                                    1000
  __init__.py 0 · apps.py 5 · admin.py 99 · models.py 129 · serializers.py 100
  services.py 74 · urls.py 41 · views.py 155 · tests.py 397
vehicles/                                  122
  __init__.py 0 · apps.py 5 · admin.py 17 · models.py 50 · serializers.py 17
  urls.py 8 · views.py 23 · tests.py 2
pricing/                                  2700
  __init__.py 0 · apps.py 8 · admin.py 75 · models.py 231 · serializers.py 62
  calculator.py 309 · cache.py 121 · nbu.py 68 · signals.py 54 · tasks.py 28
  urls.py 8 · views.py 419 · tests.py 917
  management/commands/: fetch_nbu_rates.py 49 · seed_auction_fees.py 206 · seed_rates.py 145
integrations/                             1656
  __init__.py 0 · apps.py 5 · admin.py 19 · models.py 40 · serializers.py 21
  importer.py 77 · providers.py 374 · tasks.py 104 · views.py 241 · tests.py 590
  management/commands/: import_lot.py 111 · upload_lot_photos.py 74
listings/                                  460
  __init__.py 0 · apps.py 5 · admin.py 12 · models.py 93 · permissions.py 19
  serializers.py 45 · urls.py 13 · views.py 107 · tests.py 166
local_listings/                           2761
  __init__.py 0 · apps.py 7 · admin.py 196 · models.py 214 · serializers.py 280
  antispam.py 54 · filters.py 96 · services.py 84 · tasks.py 75
  urls.py 29 · views.py 453 · tests.py 1092
  management/commands/: seed_regions.py 181
cars/  (legacy)                            146
  __init__.py 0 · apps.py 5 · admin.py 15 · models.py 29 · serializers.py 16
  urls.py 8 · views.py 71 · tests.py 2
shipments/                                 376
  __init__.py 0 · apps.py 5 · admin.py 50 · models.py 96 · serializers.py 62
  urls.py 8 · views.py 56 · tests.py 99
favorites/                                 208
  __init__.py 0 · apps.py 7 · admin.py 11 · models.py 40 · serializers.py 67
  urls.py 8 · views.py 75
saved_searches/                            183
  __init__.py 0 · apps.py 7 · admin.py 11 · models.py 21 · serializers.py 10
  tasks.py 88 · urls.py 8 · views.py 38
reports/                                   312
  __init__.py 0 · apps.py 7 · admin.py 71 · models.py 73 · serializers.py 40
  urls.py 7 · views.py 8 · tests.py 106
deals/                                     787
  __init__.py 0 · apps.py 7 · admin.py 29 · models.py 88 · serializers.py 53
  services.py 163 · urls.py 19 · views.py 107 · tests.py 321
messaging/                                 765
  __init__.py 0 · apps.py 7 · admin.py 32 · models.py 75 · serializers.py 117
  services.py 177 · urls.py 15 · views.py 129 · tests.py 213
notifications/                             129
  __init__.py 0 · apps.py 7 · admin.py 16 · models.py 33 · serializers.py 10
  services.py 16 · urls.py 9 · views.py 38
payments/                                  521
  __init__.py 0 · apps.py 7 · admin.py 12 · models.py 79 · serializers.py 48
  liqpay_client.py 119 · urls.py 8 · views.py 182 · tests.py 66
telegram_bot/                             1153
  __init__.py 0 · apps.py 10 · admin.py 11 · models.py 29 · dispatcher.py 22
  handlers.py 134 · middleware.py 37 · signals.py 13 · tasks.py 117
  urls.py 9 · views.py 114 · tests.py 515
  management/commands/: run_bot.py 52 · set_webhook.py 45 · unset_webhook.py 45
tests/                                     875
  __init__.py 0 · test_e2e.py 572 · test_favorites_notifications_saved_searches.py 303
```

Нет `tests.py`: favorites, saved_searches, notifications (покрыты корневым `tests/test_favorites_notifications_saved_searches.py`). `vehicles/tests.py` и `cars/tests.py` — пустые заглушки (2 строки).

### 1.2 Инфраструктура

```
Dockerfile                 6   (node:20-slim, CMD node server.js — не используется docker-compose)
Dockerfile.backend        33
Dockerfile.frontend       34
docker-compose.yml       145   сервисы: db, redis, backend, frontend, bot, celery_worker, celery_beat, nginx
deploy.sh                 75
docker/entrypoint.sh      33   migrate → seed_regions/seed_rates/seed_auction_fees → collectstatic → gunicorn
docker/bot_entrypoint.sh   8   exec manage.py run_bot
nginx/nginx.conf          62   /static/, /media/, ^/(api|admin)/ → backend, / → frontend
.github/workflows/ci-cd.yml 192  jobs: backend, frontend, deploy
openapi.yaml            3937   (генерируемая схема, проверяется в CI)
requirements.txt, ruff.toml 19
```

### 1.3 Миграции (только список)

| App | Файлы | Назначение (по имени) |
|---|---|---|
| users | 0001_initial; 0002_alter_customuser_managers; 0003_trustedshop; 0004_dealer_application; 0005_customuser_telegram_id; 0006_customuser_agreed_to_terms_at; 0007_customuser_is_banned_is_email_verified; 0008_dealerapplication_agreed_to_processing_at | CustomUser и его поля, TrustedShop, DealerApplication |
| vehicles | 0001_initial; 0002_vehicleimage_source_url; 0003_perf_indexes | Vehicle/VehicleImage, source_url фото, индексы |
| pricing | 0001_initial; 0002_initial; 0003_excise_rate_real_values; 0004_auction_fee_v2 | тарифные справочники, data-миграция реальных ставок акциза, новая сетка аукционных сборов |
| listings | 0001–0003_initial; 0004_listing_express_buyout_until_and_more; 0005_perf_indexes; 0006_listing_listing_status_valid_and_more | Listing, экспресс-выкуп, индексы, check-constraint статуса |
| local_listings | 0001_initial; 0002_moderation_fields; 0003_lifecycle_and_promotion; 0004_seed_promotion_tariffs; 0005_locallisting_has_contact_in_text | объявления, модерация, срок жизни/продвижение, data-сид тарифов, антиспам-флаг |
| integrations | 0001_initial; 0002_registryreport | VinReport, RegistryReport |
| cars | 0001_initial; 0002_initial | legacy Car/CarImage |
| shipments | 0001_initial | Shipment, TrackingEvent |
| payments | 0001_initial; 0002_local_listing_promote | Payment, привязка к продвижению LocalListing |
| messaging | 0001_initial | Conversation, Message |
| notifications | 0001_initial; 0002_notification_deal_types | Notification, типы для сделок |
| favorites / saved_searches / reports / deals / telegram_bot | 0001_initial | начальные схемы |

### 1.4 Фронтенд (Next.js)

Итого TS/TSX/CSS в app, components, lib, api, e2e: **7 543** строки
(app 3 994 · components 2 015 · lib 674 · e2e 493 · api 367). Плюс конфиги: next.config.ts 38, playwright.config.ts 40, eslint.config.mjs 33, tsconfig.json 34, package.json 33.

```
frontend/app/                                   3994
  layout.tsx 46 · page.tsx 227 · globals.css 21 · error.tsx 38 · global-error.tsx 30
  not-found.tsx 25 · robots.ts 22 · sitemap.ts 59
  b2b/page.tsx 95
  calculator/layout.tsx 11 · page.tsx 141
  cookies/page.tsx 164
  dealers/apply/page.tsx 161
  listings/page.tsx 52 · loading.tsx 12 · ListingsGrid.tsx 71 · WholesaleHint.tsx 30
  listings/[id]/page.tsx 74 · loading.tsx 22
  local/[id]/page.tsx 42 · LocalListingDetail.tsx 216
  local/[id]/edit/page.tsx 37
  local/new/page.tsx 24
  login/layout.tsx 10 · page.tsx 55
  register/layout.tsx 10 · page.tsx 99
  me/layout.tsx 10 · loading.tsx 20 · page.tsx 71
  me/calculations/page.tsx 63 · me/deals/page.tsx 207 · me/favorites/page.tsx 104
  me/local-listings/page.tsx 302 · me/messages/page.tsx 262 · me/notifications/page.tsx 118
  me/saved-searches/page.tsx 117 · me/shipments/page.tsx 87 · me/telegram/page.tsx 131
  me/trusted-shops/page.tsx 99
  privacy/page.tsx 106 · refund/page.tsx 145 · rules/page.tsx 115 · terms/page.tsx 90
  ua/page.tsx 74 · LocalCatalogGrid.tsx 79
frontend/components/                            2015
  calculator/CalcBreakdown.tsx 56
  favorites/HeartButton.tsx 74
  layout/Footer.tsx 24 · Header.tsx 107
  listings/ListingCard.tsx 74 · ListingDetail.tsx 124 · ListingFilters.tsx 68
  local/LocalListingCard.tsx 72 · LocalListingFilters.tsx 181 · LocalListingForm.tsx 429
       PhotoUploadBlock.tsx 143 · PromoteModal.tsx 135 · SaveSearchButton.tsx 117
  messaging/WriteSellerButton.tsx 86
  reports/ReportButton.tsx 126
  ui/Badge.tsx 20 · CookieBanner.tsx 55 · CookieSettings.tsx 67 · DemoBanner.tsx 23
     Skeleton.tsx 28 · Spinner.tsx 6
frontend/lib/                                    674
  auth-context.tsx 110 · consent.ts 77 · server-api.ts 51 · types.ts 421 · utils.ts 15
frontend/api/                                    367
  client.ts 80 · dealers.ts 19 · deals.ts 27 · favorites.ts 23 · listings.ts 29 · local.ts 71
  me.ts 16 · messages.ts 35 · notifications.ts 18 · pricing.ts 21 · reports.ts 7 · saved-searches.ts 21
frontend/e2e/                                    493
  catalog.spec.ts 92 · home.spec.ts 69 · negative.spec.ts 144 · register.spec.ts 74
  ssr.spec.ts 55 · test-1.spec.ts 59 (бывший codegen-черновик, навигация в шапке)
```

Нет `middleware.ts`, нет `route.ts` (API-роутов Next нет), нет `src/`.

---

## 2. Назначение модулей

| Модуль | Назначение |
|---|---|
| core | Проект Django: settings (DRF, JWT, throttling, Celery beat, S3/storages, CORS), корневой urls.py, celery.py (autodiscover). |
| users | CustomUser (email-логин, telegram_id, is_banned, согласия), TrustedShop, DealerApplication; регистрация/JWT/logout/профиль, «мои расчёты/контейнеры», заявки дилера. |
| vehicles | Каноническая модель Vehicle + VehicleImage; публичные list/detail. |
| pricing | Тарифные справочники с valid_from/valid_to, чистый калькулятор `calculator.py`, кэш тарифов (`cache.py` + сигналы инвалидации), курсы НБУ (`nbu.py`, задача, команда), сиды тарифов, модель Calculation. |
| integrations | Провайдеры внешних данных (VIN decode NHTSA, Opendatabot-отчёт, реестр МВД), импорт лотов Copart/IAAI → Vehicle+Listing, Celery-задача `send_notification` (Telegram-уведомления пользователю). |
| listings | Listing (импортный маркетплейс: retail/wholesale), публичный каталог, создание, B2B-доска для верифицированных дилеров. |
| cars | Legacy Car/CarImage и старый калькулятор растаможки на float с захардкоженными ставками; висит на `/api/calculate/`, `/api/list/`; фронтом не используется. |
| shipments | Контейнерные отгрузки (Shipment ↔ Vehicle M2M, watchers) и TrackingEvent; list/detail для авторизованных. |
| local_listings | Украинские частные объявления: области/города, модерация, антиспам, фильтры, фото, контакт продавца, продвижение (тарифы + LiqPay), VIN-префилл, авто-истечение. |
| favorites | Избранное (LocalListing или импортный Listing). |
| saved_searches | Сохранённые поиски + ежедневная рассылка совпадений. |
| reports | Жалобы на локальные объявления/пользователей (создание через API, разбор в админке). |
| deals | Сделки по LocalListing (propose/confirm/cancel), отзывы и рейтинг продавца. |
| messaging | Диалоги покупатель↔продавец по объявлению, сообщения, счётчик непрочитанных, уведомления. |
| notifications | In-app уведомления; `services.create_notification` используется другими приложениями. |
| payments | Payment + клиент LiqPay; checkout и callback (для Listing и продвижения LocalListing). |
| telegram_bot | aiogram-бот: привязка аккаунта через токен, webhook-вью, polling-команда, сигнал «новый Listing → пост в канал». |
| tests/ (корень) | Сквозные API-тесты (`test_e2e.py`) и тесты favorites/notifications/saved_searches. |
| docker/ | Entrypoint бэкенда (migrate, сиды, collectstatic, gunicorn) и бота (run_bot). |
| nginx/ | Реверс-прокси: api/admin → backend, остальное → frontend, раздача static/media. |
| .github/workflows | ci-cd.yml: job `backend` (тесты, ruff, проверка openapi.yaml), `frontend` (lint/build/e2e), `deploy`. |

---

## 3. Связи

### 3.1 Импорты между приложениями (без tests.py и миграций)

| App | Зависит от (где) |
|---|---|
| core | integrations (urls.py:7 — 4 вью VIN/лотов), listings (urls.py:8), users (urls.py:9) |
| users | pricing (views.py:67,71), shipments (views.py:80,84), local_listings (admin.py:9) |
| vehicles | — |
| pricing | — |
| integrations | listings, vehicles (importer.py:12-13; upload_lot_photos.py:23) |
| listings | pricing (models.py:4 — Calculation), vehicles (models.py:5, serializers.py:5) |
| cars | — |
| shipments | vehicles (models.py:4, serializers.py:4) |
| local_listings | deals (serializers.py:25,37; views.py:54), integrations (services.py:75, tasks.py:10,47, views.py:24-25), notifications (services.py:66-67, tasks.py:11-12,48-49), payments (views.py:421-422) |
| favorites | — (только строковые FK) |
| saved_searches | local_listings (tasks.py:17), notifications (tasks.py:18-19), integrations (tasks.py:48) |
| reports | local_listings (admin.py:3) |
| deals | local_listings (services.py:77, views.py:6), messaging (services.py:29, views.py:99), notifications (services.py:10), integrations (services.py:16) |
| messaging | listings (services.py:28), local_listings (services.py:29,111), notifications (services.py:132-133), integrations (services.py:127) |
| notifications | — |
| payments | listings (serializers.py:44, views.py:85), local_listings (views.py:27) |
| telegram_bot | listings (handlers.py:58, tasks.py:33; signals.py — строковый sender `listings.Listing`) |

Замечания:
- Цикл `local_listings ↔ deals` (оба импортируют друг друга; разрешён ленивыми импортами внутри функций).
- `integrations.tasks.send_notification` — фактически общий «Telegram-нотификатор», его зовут deals, local_listings, messaging, saved_searches. Место в `integrations` неочевидно.
- `tests/` импортирует: favorites, listings, local_listings, messaging, notifications, payments, pricing, saved_searches, users, vehicles.

### 3.2 Связи моделей

GenericForeignKey/GenericRelation в проекте нет. `integrations.VinReport`/`RegistryReport` без FK (ключ — VIN).

| Модель.поле | Тип | → Цель | Файл:строка |
|---|---|---|---|
| users.TrustedShop.owner | FK | CustomUser | users/models.py:62 |
| users.DealerApplication.user | FK | User | users/models.py:93 |
| users.DealerApplication.reviewed_by | FK (SET_NULL) | User | users/models.py:106 |
| vehicles.VehicleImage.vehicle | FK | Vehicle | vehicles/models.py:41 |
| pricing.Calculation.user | FK (SET_NULL) | User | pricing/models.py:210 |
| listings.Listing.vehicle | FK | vehicles.Vehicle | listings/models.py:34 |
| listings.Listing.seller | FK | User | listings/models.py:35 |
| listings.Listing.calculation | FK (SET_NULL) | pricing.Calculation | listings/models.py:41 |
| local_listings.City.region | FK | Region | local_listings/models.py:22 |
| local_listings.LocalListing.owner | FK | User | local_listings/models.py:116 |
| local_listings.LocalListing.region | FK (PROTECT) | Region | local_listings/models.py:140 |
| local_listings.LocalListing.city | FK (PROTECT) | City | local_listings/models.py:141 |
| local_listings.LocalListing.moderated_by | FK (SET_NULL) | User | local_listings/models.py:153 |
| local_listings.LocalListingImage.listing | FK | LocalListing | local_listings/models.py:200 |
| cars.Car.owner | FK | User | cars/models.py:12 |
| cars.CarImage.car | FK | Car | cars/models.py:28 |
| shipments.Shipment.vehicles | M2M | vehicles.Vehicle | shipments/models.py:44 |
| shipments.Shipment.watchers | M2M | User | shipments/models.py:47 |
| shipments.TrackingEvent.shipment | FK | Shipment | shipments/models.py:79 |
| favorites.Favorite.user | FK | User | favorites/models.py:6 |
| favorites.Favorite.local_listing | FK (null) | local_listings.LocalListing | favorites/models.py:11 |
| favorites.Favorite.imported_listing | FK (null) | listings.Listing | favorites/models.py:17 |
| saved_searches.SavedSearch.user | FK | User | saved_searches/models.py:6 |
| reports.Report.reporter | FK | User | reports/models.py:20 |
| reports.Report.listing | FK | local_listings.LocalListing | reports/models.py:26 |
| reports.Report.reported_user | FK | User | reports/models.py:33 |
| deals.Deal.listing | FK | local_listings.LocalListing | deals/models.py:12 |
| deals.Deal.seller | FK | User | deals/models.py:18 |
| deals.Deal.buyer | FK | User | deals/models.py:24 |
| deals.Review.deal | OneToOne | Deal | deals/models.py:57 |
| deals.Review.author | FK | User | deals/models.py:63 |
| deals.Review.target | FK | User | deals/models.py:69 |
| messaging.Conversation.initiator | FK | User | messaging/models.py:14 |
| messaging.Conversation.local_listing | FK (null) | local_listings.LocalListing | messaging/models.py:19 |
| messaging.Conversation.imported_listing | FK (null) | listings.Listing | messaging/models.py:25 |
| messaging.Conversation.participants | M2M | User | messaging/models.py:31 |
| messaging.Message.conversation | FK | Conversation | messaging/models.py:57 |
| messaging.Message.sender | FK | User | messaging/models.py:62 |
| notifications.Notification.user | FK | User | notifications/models.py:17 |
| payments.Payment.user | FK (SET_NULL) | User | payments/models.py:18 |
| payments.Payment.listing | FK (SET_NULL) | listings.Listing | payments/models.py:25 |
| payments.Payment.local_listing | FK (SET_NULL) | local_listings.LocalListing | payments/models.py:32 |
| payments.Payment.tariff | FK (SET_NULL) | local_listings.PromotionTariff | payments/models.py:39 |
| telegram_bot.TelegramLinkToken.user | FK | User | telegram_bot/models.py:10 |

User = `settings.AUTH_USER_MODEL` (users.CustomUser). Все FK на пользователя, кроме TrustedShop (прямой класс CustomUser), через `settings.AUTH_USER_MODEL`.

Сигналы: `pricing/signals.py` (post_save/post_delete тарифов → сброс кэша), `telegram_bot/signals.py:5` (post_save `listings.Listing` → `post_listing_to_channel.delay`).

---

## 4. URL бэкенда

Глобально: `DEFAULT_PERMISSION_CLASSES = AllowAny` (core/settings.py:223), auth — JWT, throttle anon/user + scopes `expensive`, `messages`, `contact`. «(дефолт) AllowAny» = у вью нет своих permission_classes.

Итого: **63** маршрута (+ static media при DEBUG).

| Путь | Методы | View | Permission | Файл:строка (url / view) |
|---|---|---|---|---|
| /admin/ | — | django admin | staff | core/urls.py:12 |
| /api/schema/ | GET | SpectacularAPIView | (дефолт) AllowAny | core/urls.py:36 |
| /api/docs/ | GET | SpectacularSwaggerView | (дефолт) AllowAny | core/urls.py:37 |
| /api/redoc/ | GET | SpectacularRedocView | (дефолт) AllowAny | core/urls.py:38 |
| **auth (users.urls)** | | | | |
| /api/v1/auth/register/ | POST | RegisterView | AllowAny | users/urls.py:26 / views.py:41 |
| /api/v1/auth/token/ | POST | TokenObtainPairView (SimpleJWT) | AllowAny | users/urls.py:27 |
| /api/v1/auth/token/refresh/ | POST | TokenRefreshView | AllowAny | users/urls.py:28 |
| /api/v1/auth/token/logout/ | POST | LogoutView | IsAuthenticated | users/urls.py:29 / views.py:25 |
| /api/v1/auth/profile/ | GET, PUT, PATCH | ProfileView | IsAuthenticated | users/urls.py:30 / views.py:52 |
| /api/v1/auth/me/calculations/ | GET | MyCalculationsView | IsAuthenticated | users/urls.py:32 / views.py:63 |
| /api/v1/auth/me/shipments/ | GET | MyShipmentsView | IsAuthenticated | users/urls.py:33 / views.py:76 |
| /api/v1/auth/me/trusted-shops/ | GET, POST | TrustedShopListView | IsAuthenticated | users/urls.py:34 / views.py:92 |
| /api/v1/auth/me/trusted-shops/<pk>/ | GET, PUT, PATCH, DELETE | TrustedShopDetailView | IsAuthenticated | users/urls.py:35 / views.py:106 |
| /api/v1/dealers/apply/ | POST | DealerApplyView | IsAuthenticated | users/urls.py:39 / views.py:124 |
| /api/v1/dealers/application/ | GET | DealerApplicationStatusView | IsAuthenticated | users/urls.py:40 / views.py:146 |
| **vehicles + integrations** | | | | |
| /api/v1/vehicles/ | GET | VehicleListView | (дефолт) AllowAny | vehicles/urls.py:6 / views.py:11 |
| /api/v1/vehicles/<pk>/ | GET | VehicleDetailView | (дефолт) AllowAny | vehicles/urls.py:7 / views.py:21 |
| /api/v1/vehicles/<vin>/report/ | GET | VinReportView (Opendatabot) | IsAuthenticated + throttle expensive | core/urls.py:15 / integrations/views.py:34 |
| /api/v1/vehicles/<vin>/decode/ | GET | VinDecodeView (NHTSA) | (дефолт) AllowAny + throttle expensive | core/urls.py:16 / integrations/views.py:91 |
| /api/v1/vehicles/<vin>/registry/ | GET | RegistryReportView | IsAuthenticated + throttle expensive | core/urls.py:17 / integrations/views.py:140 |
| /api/v1/lots/import/ | POST | LotImportView | IsAdminUser | core/urls.py:18 / integrations/views.py:206 |
| **pricing** | | | | |
| /api/v1/pricing/calculate/ | POST | CalculateView | (дефолт) AllowAny | pricing/urls.py:6 / views.py:144 |
| /api/v1/pricing/rates/ | GET | ActiveRatesView | (дефолт) AllowAny | pricing/urls.py:7 / views.py:375 |
| **listings / b2b** | | | | |
| /api/v1/listings/ | GET | ListingListView | (дефолт) AllowAny | listings/urls.py:6 / views.py:52 |
| /api/v1/listings/<pk>/ | GET | ListingDetailView | (дефолт) AllowAny | listings/urls.py:7 / views.py:69 |
| /api/v1/listings/create/ | POST | ListingCreateView | IsAuthenticated | listings/urls.py:8 / views.py:84 |
| /api/v1/b2b/board/ | GET | B2BBoardView | IsVerifiedDealerOrAdmin | listings/urls.py:12 / views.py:97 |
| **shipments** | | | | |
| /api/v1/shipments/ | GET | ShipmentListView | IsAuthenticated | shipments/urls.py:6 / views.py:30 |
| /api/v1/shipments/<pk>/ | GET | ShipmentDetailView | IsAuthenticated | shipments/urls.py:7 / views.py:51 |
| **payments** | | | | |
| /api/v1/payments/liqpay/checkout/ | POST | LiqPayCheckoutView | IsAuthenticated | payments/urls.py:6 / views.py:66 |
| /api/v1/payments/liqpay/callback/ | POST | LiqPayCallbackView | [] без auth (подпись LiqPay) | payments/urls.py:7 / views.py:133 |
| **local (local_listings)** | | | | |
| /api/v1/local/listings/ | GET, POST | LocalListingListCreateView | GET AllowAny / POST IsAuthenticated (get_permissions) | local_listings/urls.py:18 / views.py:124 |
| /api/v1/local/listings/<pk>/ | GET, PATCH, DELETE | LocalListingDetailView | IsAuthenticatedOrReadOnly + IsOwnerOrAdmin | urls.py:19 / views.py:146 |
| /api/v1/local/listings/<pk>/contact/ | GET | LocalListingContactView | IsAuthenticated + throttle contact | urls.py:20 / views.py:364 |
| /api/v1/local/listings/<pk>/images/ | POST | LocalListingImageUploadView | IsAuthenticated | urls.py:21 / views.py:266 |
| /api/v1/local/listings/<pk>/images/<img_id>/ | PATCH, DELETE | LocalListingImageDetailView | IsAuthenticated | urls.py:22 / views.py:322 |
| /api/v1/local/listings/<pk>/promote/ | POST | LocalListingPromoteView | IsAuthenticated | urls.py:23 / views.py:402 |
| /api/v1/local/my-listings/ | GET | MyListingsView | IsAuthenticated | urls.py:24 / views.py:190 |
| /api/v1/local/tariffs/ | GET | PromotionTariffListView | AllowAny | urls.py:25 / views.py:384 |
| /api/v1/local/vin-prefill/<vin>/ | GET | VinPrefillView | AllowAny | urls.py:26 / views.py:205 |
| /api/v1/local/regions/ | GET | RegionListView | AllowAny | urls.py:27 / views.py:231 |
| /api/v1/local/regions/<region_id>/cities/ | GET | CityListView | AllowAny | urls.py:28 / views.py:239 |
| **messages** | | | | |
| /api/v1/messages/start/ | POST | StartConversationView | IsAuthenticated + throttle messages | messaging/urls.py:11 / views.py:33 |
| /api/v1/messages/conversations/ | GET | ConversationListView | IsAuthenticated | urls.py:12 / views.py:57 |
| /api/v1/messages/conversations/<pk>/ | GET, POST | ConversationDetailView | IsAuthenticated | urls.py:13 / views.py:78 |
| /api/v1/messages/unread-count/ | GET | UnreadCountView | IsAuthenticated | urls.py:14 / views.py:125 |
| **notifications** | | | | |
| /api/v1/notifications/ | GET | NotificationListView | IsAuthenticated | notifications/urls.py:6 / views.py:11 |
| /api/v1/notifications/mark-read/ | POST | MarkReadView | IsAuthenticated | urls.py:7 / views.py:19 |
| /api/v1/notifications/unread-count/ | GET | UnreadCountView | IsAuthenticated | urls.py:8 / views.py:34 |
| **favorites** | | | | |
| /api/v1/favorites/ | GET, POST, DELETE | FavoriteListView | IsAuthenticated | favorites/urls.py:6 / views.py:11 |
| /api/v1/favorites/status/ | GET | FavoriteStatusView | IsAuthenticated | urls.py:7 / views.py:61 |
| **saved-searches** | | | | |
| /api/v1/saved-searches/ | GET, POST | SavedSearchListView | IsAuthenticated | saved_searches/urls.py:6 / views.py:11 |
| /api/v1/saved-searches/<pk>/ | PATCH, DELETE | SavedSearchDetailView | IsAuthenticated | urls.py:7 / views.py:25 |
| **reports** | | | | |
| /api/v1/reports/ | POST | ReportCreateView | IsAuthenticated | reports/urls.py:6 / views.py:6 |
| **deals** | | | | |
| /api/v1/deals/ | GET, POST | DealListCreateView | IsAuthenticated | deals/urls.py:13 / views.py:18 |
| /api/v1/deals/<pk>/confirm/ | POST | DealConfirmView | IsAuthenticated | urls.py:14 / views.py:40 |
| /api/v1/deals/<pk>/cancel/ | POST | DealCancelView | IsAuthenticated | urls.py:15 / views.py:52 |
| /api/v1/deals/<pk>/review/ | POST | DealReviewView | IsAuthenticated | urls.py:16 / views.py:64 |
| /api/v1/deals/seller-rating/<user_id>/ | GET | SellerRatingView | AllowAny | urls.py:17 / views.py:83 |
| /api/v1/deals/listing-buyers/<listing_id>/ | GET | ListingBuyersView | IsAuthenticated | urls.py:18 / views.py:91 |
| **telegram** | | | | |
| /api/v1/telegram/link-token/ | GET | TelegramLinkTokenView | IsAuthenticated | telegram_bot/urls.py:6 / views.py:21 |
| /api/v1/telegram/link/ | DELETE | TelegramUnlinkView | IsAuthenticated | urls.py:7 / views.py:47 |
| /api/v1/telegram/webhook/ | POST | TelegramWebhookView (Django View, csrf_exempt) | нет DRF; проверка `TELEGRAM_WEBHOOK_SECRET` | urls.py:8 / views.py:63-76 |
| **legacy cars** | | | | |
| /api/calculate/ | GET | cars.CustomsCalculatorView | (дефолт) AllowAny | cars/urls.py:6 / views.py:26 |
| /api/list/ | GET | cars.CarListView | (дефолт) AllowAny | cars/urls.py:7 / views.py:58 |

Эндпоинты без явных permission_classes (работают на дефолтном AllowAny): vehicles list/detail, VIN decode, pricing calculate/rates, listings list/detail, schema/docs/redoc, cars calculate/list. Для публичного каталога и калькулятора это ожидаемо; для `/api/docs/`, `/api/schema/` и legacy `cars` — стоит решить отдельно.

Бэкенд-эндпоинты, которые фронт не вызывает: `/api/v1/vehicles/*` (включая VIN report/decode/registry), `/api/v1/shipments/*` (фронт идёт через `/auth/me/shipments/`), `/api/v1/auth/token/logout/` (фронтовый logout не блеклистит refresh), `/api/v1/payments/liqpay/checkout/` (продвижение идёт через `/local/listings/<pk>/promote/`), `/api/v1/listings/create/`, `/api/v1/lots/import/` (админ), legacy `/api/calculate/`, `/api/list/`.

---

## 5. Роуты фронтенда

`client` = файл с `'use client'`. Нет `middleware.ts` — защита `/me/*`, `/b2b`, `/dealers/apply` только на клиенте через `useAuth` (auth-context). Токены — в auth-context (`/api/v1/auth/token/`, `/token/refresh/`, `/profile/`), refresh ещё в `api/client.ts`.

Итого: **28** страниц (`page.tsx`) + `robots.ts`, `sitemap.ts`; `route.ts` нет.

| URL | Файл | Тип | Данные / API |
|---|---|---|---|
| / | app/page.tsx | server (ISR) | fetch `/api/v1/listings/?channel=retail`, `/api/v1/pricing/rates/` (revalidate 3600) |
| /listings | app/listings/page.tsx (+loading, ListingsGrid, WholesaleHint) | server | `serverGet /api/v1/listings/?…` |
| /listings/[id] | app/listings/[id]/page.tsx (+loading) | server, generateMetadata | fetch `/api/v1/listings/{id}/`; ListingDetail |
| /ua | app/ua/page.tsx (+LocalCatalogGrid) | server | `serverGet /api/v1/local/listings/?…`; SaveSearchButton, LocalListingFilters |
| /local/[id] | app/local/[id]/page.tsx + LocalListingDetail.tsx (client) | server + client | fetch `/api/v1/local/listings/{id}/`; `localApi.getContact`, избранное, сообщения, жалоба, рейтинг |
| /local/new | app/local/new/page.tsx | client | LocalListingForm (localApi: create, regions, cities, vin-prefill, images) |
| /local/[id]/edit | app/local/[id]/edit/page.tsx | client | `localApi.detail` + LocalListingForm |
| /calculator | app/calculator/page.tsx (+layout server — metadata) | client | `pricingApi.calculate` |
| /b2b | app/b2b/page.tsx | client | `listingsApi.b2bBoard` |
| /dealers/apply | app/dealers/apply/page.tsx | client | `dealersApi.apply` / status |
| /login | app/login/page.tsx (+layout) | client | auth-context `login` |
| /register | app/register/page.tsx (+layout) | client | `apiFetch /api/v1/auth/register/` |
| /me | app/me/page.tsx (+layout, loading) | client | меню кабинета |
| /me/calculations | app/me/calculations/page.tsx | client | `pricingApi.myCalculations` |
| /me/deals | app/me/deals/page.tsx | client | `dealsApi.list/confirm/cancel/review` |
| /me/favorites | app/me/favorites/page.tsx | client | `getFavorites`, `removeFavorite` |
| /me/local-listings | app/me/local-listings/page.tsx | client | `localApi.my/remove`, `dealsApi.listingBuyers/propose`, PromoteModal (tariffs, promote) |
| /me/messages | app/me/messages/page.tsx | client | `getConversations`, `getConversation`, `sendMessage` |
| /me/notifications | app/me/notifications/page.tsx | client | `getNotifications`, `markRead`, `markAllRead` |
| /me/saved-searches | app/me/saved-searches/page.tsx | client | `getSavedSearches`, `patchSavedSearch`, `deleteSavedSearch` |
| /me/shipments | app/me/shipments/page.tsx | client | `meApi.shipments` |
| /me/telegram | app/me/telegram/page.tsx | client | `apiFetch /api/v1/telegram/link-token/`, `/link/` (DELETE) |
| /me/trusted-shops | app/me/trusted-shops/page.tsx | client | `meApi.trustedShops` (+CRUD) |
| /cookies | app/cookies/page.tsx | server | CookieSettings (client) |
| /privacy, /refund, /rules, /terms | app/*/page.tsx | server | статический текст |
| (404) | app/not-found.tsx | server | — |
| (ошибки) | app/error.tsx, app/global-error.tsx | client | — |
| /robots.txt | app/robots.ts | server | allow `/`, `/listings`, `/calculator`; disallow `/me/`, `/b2b/`, `/dealers/`, `/login`, `/register`, `/admin/`, `/api/` |
| /sitemap.xml | app/sitemap.ts | server | статические URL + `serverGet /api/v1/listings/?status=in_stock|in_transit…` и `/api/v1/local/listings/?page=1` (revalidate 3600) |

Компоненты, использующие API напрямую: HeartButton (favorites status/add/remove), WriteSellerButton (`startConversation`), ReportButton (`reportsApi`), SaveSearchButton (`createSavedSearch`), PromoteModal (`localApi.tariffs/promote`), PhotoUploadBlock (images upload/delete/patch), Header (unread-count messages/notifications).

Все внутренние ссылки (`href`/`router.push`) указывают на существующие страницы; битых роутов не найдено. `/local` без id отдельной страницы не имеет (каталог — `/ua`), ссылки на голый `/local` нет.

---

## 6. Celery, расписания, management-команды

Celery: `core/celery.py` (autodiscover), в dev `CELERY_TASK_ALWAYS_EAGER=True` + broker `memory://` если нет Redis (settings.py:359-365). Scheduler — `django_celery_beat.schedulers:DatabaseScheduler` (settings.py:368), при этом расписание задаётся в `CELERY_BEAT_SCHEDULE` (settings.py:373). В docker-compose — сервисы `celery_worker` и `celery_beat`.

### Задачи

| Задача | Файл:строка | Кто вызывает |
|---|---|---|
| `pricing.tasks.fetch_nbu_rates_task` | pricing/tasks.py:18 | beat |
| `saved_searches.tasks.check_saved_searches` | saved_searches/tasks.py:9 | beat |
| `local_listings.tasks.warn_expiring_listings` | local_listings/tasks.py:8 | beat |
| `local_listings.tasks.expire_listings` | local_listings/tasks.py:45 | beat |
| `integrations.tasks.send_notification` (Telegram-сообщение пользователю) | integrations/tasks.py:53 | `.delay` из deals/services.py:17, local_listings/services.py:76, local_listings/tasks.py:33,69, messaging/services.py:175, saved_searches/tasks.py:50 |
| `integrations.tasks.import_lot_task` | integrations/tasks.py:16 | **нигде в продовом коде** (только тесты); LotImportView и команда `import_lot` зовут `importer.import_lot` синхронно |
| `telegram_bot.tasks.post_listing_to_channel` | telegram_bot/tasks.py:19 | `.delay` из telegram_bot/signals.py:13 (post_save Listing) |

### Периодические расписания (CELERY_BEAT_SCHEDULE, Europe/Kyiv)

| Имя | Задача | Время |
|---|---|---|
| fetch-nbu-rates-daily | pricing.tasks.fetch_nbu_rates_task | 09:00 |
| warn-expiring-listings-daily | local_listings.tasks.warn_expiring_listings | 09:15 |
| expire-listings-daily | local_listings.tasks.expire_listings | 09:20 |
| check-saved-searches-daily | saved_searches.tasks.check_saved_searches | 10:00 |

### Management-команды

| Команда | Файл | Назначение |
|---|---|---|
| import_lot | integrations/management/commands/import_lot.py | Импорт лота Copart/IAAI (JSON/файл) в Vehicle + Listing |
| upload_lot_photos | integrations/management/commands/upload_lot_photos.py | Скачать фото лотов по source_url в хранилище (S3/local) |
| seed_regions | local_listings/management/commands/seed_regions.py | Сид областей и ~300 городов Украины (неполный КАТОТТГ) |
| fetch_nbu_rates | pricing/management/commands/fetch_nbu_rates.py | Курсы USD/UAH, EUR/UAH из НБУ → ExchangeRate |
| seed_auction_fees | pricing/management/commands/seed_auction_fees.py | Baseline-сетки buyer fee Copart/IAAI |
| seed_rates | pricing/management/commands/seed_rates.py | Начальные тарифы (плейсхолдеры растаможки) |
| run_bot | telegram_bot/management/commands/run_bot.py | Запуск бота в polling (сервис `bot` в compose) |
| set_webhook | telegram_bot/management/commands/set_webhook.py | Установить Telegram webhook (прод) |
| unset_webhook | telegram_bot/management/commands/unset_webhook.py | Снять webhook |

`docker/entrypoint.sh` при каждом старте бэкенда выполняет migrate + seed_regions + seed_rates + seed_auction_fees + collectstatic.

---

## Заметные странности (для следующих фаз)

1. **Legacy `cars`** жив в INSTALLED_APPS и URL (`/api/calculate/`, `/api/list/`, AllowAny); калькулятор на `float` с захардкоженными ставками (cars/views.py:26-40) — прямо нарушает правила CLAUDE.md; фронт его не использует.
2. **`import_lot_task`** — мёртвая Celery-задача (вызывается только из тестов).
3. **Корневой `Dockerfile`** (node, `CMD node server.js`) не используется compose/CI — вероятно, мёртвый.
4. **Неиспользуемые фронтом эндпоинты**: vehicles/*, VIN report/decode/registry, shipments/*, token/logout, payments checkout, listings/create.
5. **Нет Next `middleware.ts`** — приватные страницы защищены только клиентским редиректом.
6. **DEFAULT_PERMISSION_CLASSES = AllowAny** — безопасность держится на явных permission_classes каждой вью; без них: VinDecode (бесплатный NHTSA, но только throttle expensive), pricing, listings, vehicles, docs/schema, cars.
7. **Смешанный Scheduler**: DatabaseScheduler + статический CELERY_BEAT_SCHEDULE (django-celery-beat синхронизирует его в БД, но правки в админке и в коде могут расходиться).
8. **Цикл импортов** local_listings ↔ deals; Telegram-нотификатор `send_notification` живёт в `integrations`.
9. Пустые `tests.py` в vehicles и cars; нет тестов у notifications/favorites/saved_searches внутри приложений (есть в корневом tests/).
10. Копия репо в `.claude/worktrees/agent-a0e9aa80` (git worktree) засоряет поиск.
