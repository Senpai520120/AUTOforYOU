# AUTOforYOU — Архитектура

## Docker Compose — повний стек (промт 15)

### Сервіси (`docker-compose.yml`)
| Сервіс | Образ | Роль |
|---|---|---|
| `db` | postgres:16-alpine | PostgreSQL + health-check |
| `redis` | redis:7-alpine | Кеш + брокер Celery |
| `backend` | Dockerfile.backend | Gunicorn + міграції + collectstatic |
| `frontend` | Dockerfile.frontend | Next.js production (`npm start`) |
| `bot` | Dockerfile.backend | Telegram polling (exit 0 без токену) |
| `celery_worker` | Dockerfile.backend | Celery worker |
| `celery_beat` | Dockerfile.backend | Celery beat (DatabaseScheduler) |
| `nginx` | nginx:alpine | Reverse proxy, порт 80 на хості |

### Маршрутизація nginx
- `/static/` → Docker volume `static` (collectstatic output)
- `/media/` → Docker volume `media` (user uploads)
- `/api/*`, `/admin/*` → `backend:8000` (Gunicorn)
- `/` → `frontend:3000` (Next.js)

### SSR та мережа Docker
- Браузерний JS: `NEXT_PUBLIC_API_URL=http://localhost` (baked at build, через nginx)
- Next.js SSR: `INTERNAL_API_URL=http://backend:8000` (runtime, Docker internal network)
- Три серверні компоненти оновлені: `local/[id]/page.tsx`, `listings/[id]/page.tsx`, `sitemap.ts`

### Запуск
```bash
cp .env.docker.example .env          # або залиш дефолти
docker compose up --build            # перший запуск (довго — збирає образи)
# Сайт: http://localhost
# API:  http://localhost/api/v1/
# Admin: http://localhost/admin/
docker compose down                  # зупинити (дані в volumes зберігаються)
docker compose down -v               # зупинити + видалити дані БД
```

### Обмеження локального Docker
- Бот без `TELEGRAM_BOT_TOKEN`: exit 0, не рестартує, решта стеку працює
- LiqPay sandbox: потребує публічного URL для webhook (ngrok у dev)
- SSL: nginx.conf містить закоментований SSL-блок — для деплою з реальним сертифікатом

---

## ✅ C2C-блок ЗАВЕРШЕНО (C2C-промт 1–7)

C2C-функціонал повністю реалізований. Блокери перед запуском:
1. **Юридична перевірка** — `/rules`, `/terms`, `/privacy`, `/cookies` позначені «Шаблон». Потрібен юрист.
2. **Реальні ціни тарифів** — `PromotionTariff` у БД містить плейсхолдери. Встановити перед продом.
3. **Реальні тарифи логістики** — `UsLandRoute`, `OceanFreight`, `EuToUa` — котировки від брокера.
4. **Платні API-ключі** — Carfax/BidFax (ДТП/торги), Apify (import лотів), реальні ключі LiqPay.

---

## Угоди + відгуки + рейтинги продавця (C2C-промт 7)

### deals app

#### Deal
```
listing FK(LocalListing), seller FK(CustomUser), buyer FK(CustomUser)
status: proposed | confirmed | cancelled
confirmed_at (DateTimeField, nullable)
UniqueConstraint(listing, buyer)
clean(): seller_id != buyer_id
```

#### Review
```
deal OneToOneField(Deal, related_name='review')
author FK(CustomUser, related_name='reviews_written')
target FK(CustomUser, related_name='reviews_received')
rating PositiveSmallIntegerField (1–5)
text TextField (blank=True)
clean(): author_id == deal.buyer_id (анти-накрутка)
```

### Сервіси (deals/services.py)
- `propose_deal(listing, seller, buyer_id)` — власник оголошення пропонує угоду; покупець має бути учасником хоча б одного діалогу по оголошенню; нотифікація `deal_proposed`.
- `confirm_deal(deal, buyer)` — тільки покупець; `status → confirmed`, `listing.status → sold`, `confirmed_at = now()`; нотифікація `deal_confirmed`.
- `cancel_deal(deal, user)` — будь-яка сторона; тільки з `proposed`; нотифікація `deal_cancelled`.
- `create_review(deal, author, rating, text)` — тільки покупець; `deal.status == confirmed`; один відгук (`OneToOneField`); нотифікація `review_received`.
- `seller_rating(seller_id)` → `{confirmed_deal_count, review_count, avg_rating, has_badge, badge_threshold}`.

### Бейдж «✓ Перевірений продавець»
- `SELLER_BADGE_THRESHOLD = 3` (env, `core/settings.py`).
- `seller_has_badge`: `Deal.objects.filter(seller=owner, status='confirmed').count() >= threshold`.
- Обчислюється в серіалізаторі при кожному запиті (без кешу — актуальне значення).
- Показується в `LocalListingCard` і `LocalListingDetail` (синя панель продавця).

### Ендпоінти `/api/v1/deals/`
```
GET/POST  /api/v1/deals/                        # мої угоди / propose
POST      /api/v1/deals/<id>/confirm/           # buyer confirms
POST      /api/v1/deals/<id>/cancel/            # either party cancels
POST      /api/v1/deals/<id>/review/            # buyer leaves review
GET       /api/v1/deals/seller-rating/<user_id>/ # public seller rating
GET       /api/v1/deals/listing-buyers/<listing_id>/ # seller: who to propose to
```

### Юридичні сторінки
- `/rules` — Правила розміщення (8 розділів). Розділ 6 = C2C-застереження: «Платформа є посередником, а не стороною угоди».
- Усі юридичні тексти позначені «Шаблон — потребує перевірки юристом» і `robots: {index: false}`.
- Footer: `/rules` між `/terms` і `/privacy`.
- `LocalListingForm.tsx`: checkbox погодження → справжнє посилання `/rules`.

---

## Захист контактів / Скарги / Баны / Антиспам (C2C-промт 6)

### Захист контактів
- `contact_phone` НЕ повертається в жодному публічному серіалізаторі (list, detail, owner — завжди `null`).
- `GET /api/v1/local/listings/<id>/contact/` — єдиний спосіб отримати телефон; тільки авторизований.
- Rate-limit scope `contact`: 20/год (env `THROTTLE_CONTACT_RATE`). Захищає від скриптового збору.
- Frontend: кнопка «Показати телефон» → GET /contact/ → показує номер або веде на /login для аноніма.

### Антиспам (`local_listings/antispam.py`)
- `detect_contacts(text)` → список типів: `phone`, `url`, `messenger`. Порожній список = чисто.
- **Що є контактом**: `+380...` / `0XX-XXX-XX-XX` (UA-формат), `http(s)://` / `www.` / домен із TLD, `telegram/viber/whatsapp + @username`.
- **НЕ спрацьовує** на: рік (4 цифри), пробіг/ціна/об'єм без телефонного шаблону.
- Режим (env `ANTISPAM_MODE`, дефолт `soft`):
  - `soft` — оголошення позначається прапором `has_contact_in_text=True` (залишається pending, іде на перевірку); у повідомленнях — відповідь містить `warning`, але повідомлення надсилається.
  - `hard` — ValidationError при створенні оголошення; повідомлення не надсилається.
  - `off` — детекція вимкнена.

### reports app
- `Report(reporter FK, listing nullable FK, reported_user nullable FK, reason, comment, status[new|reviewed|dismissed])`.
- Унікальна активна скарга: один `reporter` — одна `new`-скарга на кожен об'єкт.
- `POST /api/v1/reports/` — тільки авторизований. Валідація: тільки listing АБО reported_user, не обидва.
- Django Admin (`ReportAdmin`): фільтр за status/reason, три дії:
  - **«Сховати оголошення»** → `listing.status = hidden` + скарга `reviewed`.
  - **«Забанити користувача»** → `is_banned=True`, `is_active=False`, активні оголошення → `hidden` + скарга `reviewed`.
  - **«Відхилити»** → скарга `dismissed`.

### Бан користувача
- `CustomUser.is_banned` (bool) + `is_active=False` при бані. Django/JWT автоматично відхиляє неактивних.
- Users Admin: bulk actions `ban_users` / `unban_users`.
- При бані: всі `active`/`pending` оголошення → `hidden`.
- `CustomUser.is_email_verified` — заготовка для email-верифікації; повноцінна реалізація — окремо.

---

## Favorites / Notifications / Saved Searches (C2C-промт 4)

### favorites app
- `Favorite(user, local_listing nullable FK, imported_listing nullable FK, created_at)`. UniqueConstraint на (user, local_listing) та (user, imported_listing).
- API: GET/POST/DELETE `/api/v1/favorites/` + GET `/api/v1/favorites/status/`
- Frontend: `HeartButton` на деталях local/imported оголошень. Список у `/me/favorites`.

### notifications app
- `Notification(user, type, title, text, link, is_read, created_at)`.
- Типи: `new_message`, `listing_approved`, `listing_rejected`, `listing_expiring` (заглушка C2C-5), `saved_search_match`.
- `create_notification(user_id, type, title, text, link)` — сервісна функція; викликається з messaging та local_listings.
- API: GET `/api/v1/notifications/`, POST `mark-read/`, GET `unread-count/`
- Frontend: колокольчик у Header з бейджем (polling 30с). Сторінка `/me/notifications`.

### saved_searches app
- `SavedSearch(user, name, filters JSON, notify bool, last_notified_at, created_at)`.
- API CRUD: `/api/v1/saved-searches/` + `<id>/`
- Celery beat task `check_saved_searches` щодня о 10:00: для кожного SavedSearch(notify=True) знаходить LocalListing.created_at > last_notified_at → `create_notification()` + `send_notification.delay()`. Ідемпотентно — оновлює last_notified_at після обробки.
- Frontend: `SaveSearchButton` на `/ua` (видима тільки при активних URL-фільтрах). Список у `/me/saved-searches`.

---

## Messaging — non-realtime месенджер (C2C-промт 3)

### Моделі
- `Conversation`: initiator FK, local_listing FK (nullable), imported_listing FK (nullable), participants M2M, last_message_at, created_at. UniqueConstraint на (initiator, local_listing) та (initiator, imported_listing).
- `Message`: conversation FK, sender FK, text, created_at, read_at (nullable).

### Бізнес-логіка (messaging/services.py)
- `get_or_create_conversation(initiator, listing_type, listing_id, first_text)` — один діалог на пару (покупець, оголошення); повторний start відкриває той самий.
- Місцеве оголошення → participants: покупець + автор. Заборона писати самому собі.
- Імпортне оголошення → participants: покупець + перший admin. Всі адміни бачать через queryset.
- `mark_as_read(user, conv)` — позначає вхідні прочитаними при відкритті.
- `unread_count_for_user(user)` — для бейджа.
- `_add_message` → `_notify_recipients`: тригерить `send_notification.delay` для всіх отримувачів.
- `# Anti-spam (phone/link filter) — повноцінно C2C-промт 6` — заглушка в коді.

### Ендпоінти (messaging/urls.py → /api/v1/messages/)
```
POST /api/v1/messages/start/                   # почати/відкрити діалог
GET  /api/v1/messages/conversations/           # мої діалоги
GET  /api/v1/messages/conversations/<id>/      # читати + позначити прочитаними
POST /api/v1/messages/conversations/<id>/      # надіслати повідомлення
GET  /api/v1/messages/unread-count/            # бейдж
```
Throttle scope `messages`: 30/год (env `THROTTLE_MESSAGES_RATE`).

### Фронтенд
- `app/me/messages/` — split-pane месенджер: список діалогів (зліва) + тред + поле вводу (справа). Polling 15 с, без WebSocket.
- `components/messaging/WriteSellerButton.tsx` — модальне вікно з першим повідомленням → redirect до треду.
- Кнопка «Написати продавцю» на `/local/[id]` (не власник, статус active).
- Кнопка «Написати менеджеру» на `/listings/[id]` (імпортне оголошення).
- Бейдж непрочитаних у Header (polling 30 с).

### Real-time — можлива 2-я ітерація
WebSocket/SSE — не реалізовано. Поточна версія non-realtime: нові повідомлення з'являються при відкритті/оновленні діалогу або через polling.

---

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

## ⛔ ЗАПУСК ЗАБЛОКИРОВАН ДО (финальный список, стан на 2026-07-03):
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
