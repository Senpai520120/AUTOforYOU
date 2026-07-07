# PROGRESS.md — Живой журнал прогресса

## Статус: ФАЗА 2 ✓ | C2C 1–7 ✓ ЗАВЕРШЕНО | Docker ✓ | Безкоштовна підготовка ✓ | 404-фікс ✓ | Черга: деплой на Railway

---

## Фікс 404 на сторінці оголошення (2026-07-05) — ЗАВЕРШЕНО

### Причина
Next.js SSR при серверному рендері запитує бекенд напряму по Docker-мережі (`http://backend:8000/...`).
Django відхиляв ці запити з помилкою `DisallowedHost` (HTTP 400) — бо `backend` не був у `ALLOWED_HOSTS`.
Браузерні запити через nginx давали 200 (nginx проставляв `Host: localhost`), тому API-тести в браузері виглядали ОК.
Next.js SSR отримував 400, повертав `null`, викликав `notFound()` → сторінка показувала 404.

### Фікс
- `.env`: `ALLOWED_HOSTS=localhost,127.0.0.1,backend` (додано `backend`)
- `.env.docker.example`: те саме (щоб при наступному деплої не повторилось)
- `docker compose up -d --no-deps backend` — перезапущено контейнер з новим env (дані НЕ зачеплені)

### Перевірка після фіксу
- `fetch('http://backend:8000/api/v1/local/listings/1/')` з frontend-контейнера → **HTTP 200** ✅
- Оголошення id=1 (active, make=weqw, city=Лубни) відкривається ✅
- Всі 7 сервісів Docker-стеку running/healthy ✅

### Стан бази даних
- LocalListing: 1 (active) — дані власника збережені, нічого не видалялось
- Регіони: 25, Міст: 96 (до дозасіву seed_regions з новим переліком ~310 міст)
- Наступний крок: `docker compose exec backend python manage.py seed_regions` — дозасіяти міста

### Наступний крок
Деплой на Railway + перенесення даних SQLite→Postgres (якщо є локальна SQLite-база з dev-даними).

---

## Безкоштовна підготовка до запуску (2026-07-05) — ЗАВЕРШЕНО

### A1 — Регіони
- [x] seed_regions розширено: 25 областей + місто Київ, ~300+ міст (більші та середні)
- [x] Виправлено помилку: Рівне перенесено до Рівненської обл. (раніше помилково у Волинській)
- [x] Ідемпотентно: повторний запуск не плодить дублів (get_or_create)
- [!] Неповний КАТОТТГ: для повного переліку потрібен офіційний CSV Мінцифри

### A2 — SECRET_KEY
- [x] На проді (DEBUG=False) без SECRET_KEY в env → ImproperlyConfigured (зрозуміла помилка)
- [x] Для dev — залишено insecure-fallback (локальна розробка не сломана)
- [x] .env.example оновлено: команда генерації SECRET_KEY

### A3 — DEBUG/ALLOWED_HOSTS
- [x] DEBUG з env, дефолт false (прод безпечний за замовчуванням)
- [x] ALLOWED_HOSTS=[] без env на проді → Django DisallowedHost (зрозуміла помилка, не мовчання)
- [x] Локальний запуск (DEBUG=true) — не сломано

### A4 — Email
- [x] Dev: console backend (листи у консоль, SMTP не потрібен)
- [x] Прод: EMAIL_HOST/PORT/TLS/USER/PASSWORD читаються з env — вписати SMTP-провайдер
- [x] .env.example і .env.docker.example оновлено з коментарем «вписати SMTP-провайдер на проді»

### A5 — Swagger
- [x] Додано @extend_schema_field до SerializerMethodField у local_listings/serializers.py: get_owner_name (CharField), get_seller_has_badge (BooleanField), get_seller_avg_rating (FloatField), get_seller_deal_count (IntegerField)
- [x] Додано @extend_schema_field у listings/serializers.py: get_is_express_active (BooleanField)
- [x] Додано @extend_schema_field у shipments/serializers.py: get_vehicle_count (IntegerField), get_next_statuses (ListField)
- [x] ENUM_NAME_OVERRIDES розширено: LocalListingFuelTypeEnum, CustomsExciseFuelTypeEnum, LocalListingStatusEnum, DealStatusEnum, PromotionTariffTypeEnum, ReportStatusEnum, PaymentStatusEnum, DealerApplicationStatusEnum, NotificationTypeEnum, UserRoleEnum
- [x] ENUM_GENERATE_CHOICE_DESCRIPTION=False додано до SPECTACULAR_SETTINGS
- [!] Залишилось 5 попереджень (не критично, не помилки):
  - 1x fuel_type collision (FuelType94dEnum) — складно вирішити через нетривіальні хеші drf-spectacular
  - 3x status collision (Status4ef/StatusC94/Status7fcEnum) — аналогічно, потребує @extend_schema на views
  - 1x operationId collision на /api/v1/messages/conversations/ — потребує рефакторингу URL або @extend_schema(operation_id=...)
  - Всі warnings не є помилками, схема генерується успішно

### A6 — Тести та Telegram-бот
- [x] 365 тестів — OK (DATABASE_URL="" REDIS_URL="" TELEGRAM_BOT_TOKEN="" python manage.py test)
- [!] Примітка для тестів: .env для Docker містить DATABASE_URL та REDIS_URL з docker-hostname. Для локального запуску тестів треба скидати через env: DATABASE_URL="" REDIS_URL="" TELEGRAM_BOT_TOKEN="" python manage.py test
- [x] Telegram-бот налаштовано: токен задано в .env (TELEGRAM_BOT_TOKEN)
- [x] Канал знайдено і доступний: @AUTO_F_Y (канал AUTO_FOR_YOU)
- [x] Бот: @AUTO_F_Y_bot (AUTO_FOR_YOU), ID 8785926220
- [x] Webhook очищено (deleteWebhook: ok — старих вебхуків не було)
- [x] Бот готовий до polling: python manage.py run_bot
- [x] В Docker — окремий сервіс `bot` у docker-compose.yml (вже є)

---

## C2C-промт 1 — Місцеві оголошення (завершено 2026-07-01)

### Backend
- [x] Новий Django-додаток `local_listings` (Region, City, LocalListing, LocalListingImage)
- [x] 25 областей + 96 міст, management-команда `seed_regions` (# неповний КАТОТТГ)
- [x] DRF-ендпоінти: CRUD /api/v1/local/listings/, /vin-prefill/<vin>/, /regions/, /cities/
- [x] Ліміт активних оголошень: LOCAL_LISTING_MAX_ACTIVE (env, дефолт 10)
- [x] contact_phone відсутній у публічному списку (захист — C2C-промт 6)
- [x] Фільтри: make, model, year range, price range, fuel, transmission, body_type, region, city, mileage_max, search, ordering
- [x] Індекси БД: status, make, year, price, region, fuel_type
- [x] VIN-prefill: GET /api/v1/local/vin-prefill/<vin>/ — NHTSA vPIC (бесплатно, без ключа), кеш VinReport
- [x] Статуси: draft/active (C2C-1), pending/rejected/expired/sold/hidden (заглушки — C2C-2/5)
- [x] 18 нових тестів, **217 тестів всього — OK**

### Frontend
- [x] `/ua` — Каталог Україна: список з фільтрами (панель критеріїв), карточки, пусте стан
- [x] `/local/new` — форма подачі (авторизований): VIN-поле + кнопка «Заповнити за VIN», виладушки область→місто
- [x] `/local/[id]` — деталь: галерея, характеристики, кнопка «Показати телефон» (заглушка — C2C-6)
- [x] `/local/[id]/edit` — редагування свого оголошення
- [x] Header: навігація розділена «Пригін/аукціон» (існуючий) / «Каталог Україна» (новий)
- [x] api/local.ts, types.ts, компоненти LocalListingCard/Filters/Form
- [x] **22 Next.js роути, 0 TS-помилок, npm run build OK**

### Архітектурне рішення
- `LocalListing` — окремий Django-додаток, НЕ розширення `listings.Listing`
- Існуючий імпортний каталог (Listing + Vehicle) не зачеплений

---

## C2C-промт 2 — Модерація місцевих оголошень (завершено 2026-07-01)

### Backend
- [x] Нові поля `LocalListing`: `rejection_reason`, `moderated_by` FK, `moderated_at`, `agreed_to_rules` (bool), `agreed_to_rules_at`
- [x] Міграція `0002_moderation_fields`
- [x] `local_listings/services.py`: `approve_listing()` → active + email + Telegram; `reject_listing()` → rejected + причина + сповіщення
- [x] Серіалізатор: новий запис → `status=pending`; `agreed_to_rules=True` — обов'язково; `rejection_reason` прихований від чужих
- [x] Ремодерація: суттєва правка `active` → `pending`; будь-яка правка `rejected` → `pending`; суттєві поля: `{make, model, year, price, description}`
- [x] `GET /api/v1/local/my-listings/` — усі оголошення власника (всі статуси, пагінація)
- [x] `PendingLocalListingProxy` — окрема секція «Черга модерації» в Django Admin
- [x] Дії адміна: «Одобрити» (bulk, без форми) та «Відхилити з причиною» (intermediate TemplateResponse + POST confirm)
- [x] Email + Telegram сповіщення власнику через `integrations.tasks.send_notification`
- [x] **233 тести всього — OK**

### Frontend
- [x] `/me/local-listings` — «Мої оголошення»: статус-бейджі (active/pending/rejected/hidden/sold/expired/draft)
- [x] Причина відхилення: виводиться власнику у вигляді червоного блоку
- [x] Кнопки дій залежно від статусу: «Редагувати і надіслати знову» (rejected), «Редагувати» (active/pending/hidden), «Видалити»
- [x] Форма `/local/new`: чекбокс «Погоджуюсь з правилами» (required), після submit → екран «На модерації» замість redirect
- [x] `/me` — додано пункт «Мої оголошення» у меню кабінету
- [x] **23 Next.js роути, 0 TS-помилок, npm run build OK**

### Архітектурне рішення
- Proxy-модель `PendingLocalListingProxy` → окрема адмін-секція без дублювання реєстрації моделі
- `TemplateResponse` + POST `confirm` — intermediate форма для причини відхилення (без окремого view)
- `agreed_to_rules_at = timezone.now()` — патерн з промту 13 (`agreed_to_terms_at`)

---

## C2C-промт 3 — Повідомлення (завершено 2026-07-02)

### Backend
- [x] `messaging` Django-додаток: Conversation + Message моделі
- [x] Один діалог на пару (ініціатор, оголошення) — UniqueConstraint
- [x] Місцеве: покупець ↔ автор; імпортне: покупець ↔ перший адмін (всі адміни бачать)
- [x] Заборона писати самому собі по своєму оголошенню
- [x] `mark_as_read` при відкритті діалогу
- [x] `unread_count_for_user` для бейджа
- [x] Сповіщення через `send_notification.delay` при кожному новому повідомленні
- [x] Anti-spam throttle scope `messages` 30/год + заглушка фільтра посилань (`# C2C-промт 6`)
- [x] 5 ендпоінтів: start, list, detail, post, unread-count
- [x] ConversationAdmin + MessageInline в Django Admin
- [x] **23 тести всього для messaging — OK; 256 тестів по всьому проекту — OK**

### Frontend
- [x] `api/messages.ts`: getConversations, getConversation, sendMessage, startConversation, getUnreadCount
- [x] `lib/types.ts`: ConversationSummary, ConversationDetail, ChatMessage, MessageParticipant
- [x] `app/me/messages/` — split-pane месенджер: список діалогів + тред + поле вводу
- [x] Polling 15 с на активний тред, polling 30 с на бейдж (без WebSocket)
- [x] `WriteSellerButton.tsx` — модальне вікно для першого повідомлення → redirect до треду
- [x] «Написати продавцю» на сторінці місцевого оголошення (не власник, active)
- [x] «Написати менеджеру» на сторінці імпортного оголошення
- [x] Бейдж непрочитаних у Header (іконка чату з лічильником)
- [x] «Повідомлення» у меню кабінету `/me`
- [x] **24 Next.js роути, 0 TS-помилок, npm run build OK**

---

## C2C-промт 4 — Обране + центр сповіщень + збережені пошуки (завершено 2026-07-02)

### Backend
- [x] `notifications` app: Notification(user, type, title, text, link, is_read, created_at) — 5 типів
- [x] `notifications/services.py`: `create_notification()`, `unread_count()`
- [x] 3 ендпоінти: GET /api/v1/notifications/, POST mark-read, GET unread-count
- [x] `favorites` app: Favorite(user, local_listing nullable, imported_listing nullable) + UniqueConstraint
- [x] GET/POST/DELETE /api/v1/favorites/ + GET /api/v1/favorites/status/
- [x] `saved_searches` app: SavedSearch(user, name, filters JSON, notify, last_notified_at)
- [x] CRUD /api/v1/saved-searches/ + <id>/
- [x] Celery task `check_saved_searches` щодня о 10:00: нові оголошення → Notification + send_notification. Ідемпотентно через last_notified_at
- [x] messaging/services.py → також створює NEW_MESSAGE Notification для отримувача
- [x] local_listings/services.py → approve/reject також створює LISTING_APPROVED/REJECTED Notification
- [x] **28 нових тестів; 284 тести всього — OK**

### Frontend
- [x] `api/notifications.ts`, `api/favorites.ts`, `api/saved-searches.ts`
- [x] `app/me/notifications/` — центр сповіщень (list, mark-read, mark-all, icons per type)
- [x] `app/me/favorites/` — список обраного з кнопкою «Прибрати»
- [x] `app/me/saved-searches/` — список збережених пошуків, toggle notify, delete, «Відкрити пошук»
- [x] `HeartButton.tsx` — серце на картках/деталях (local + imported), polling статусу
- [x] `SaveSearchButton.tsx` — «Зберегти пошук» на /ua (видно тільки при активних фільтрах)
- [x] Header: колокольчик сповіщень + бейдж (polling 30с) поряд з іконкою чату
- [x] **27 Next.js роутів, 0 TS-помилок, npm run build OK**

### Допущення (C2C-4)
- Saved searches перевіряються щодня о 10:00 Kyiv time (Celery beat, EAGER у dev/тестах)
- Сповіщення зберігаються останні 50 (лімітовано в API); архівація/пагінація — майбутня ітерація
- HeartButton для авторизованих: не-авторизований → redirect to /login

---

## C2C-Extra — Фото LocalListing (завершено 2026-07-02)

### Backend
- [x] `POST /api/v1/local/listings/<pk>/images/` — завантаження одного/кількох фото (multipart)
- [x] `DELETE /api/v1/local/listings/<pk>/images/<img_id>/` — видалення; авто-просування наступного в головне
- [x] `PATCH /api/v1/local/listings/<pk>/images/<img_id>/` — призначити головним (знімає з решти)
- [x] Валідація: jpg/png/webp, ≤8 МБ, ≤15 фото; env-overridable (`LOCAL_LISTING_MAX_PHOTOS`, `LOCAL_LISTING_PHOTO_MAX_SIZE_MB`)
- [x] Перше фото авто-primary якщо жодного немає
- [x] Тільки власник або адмін; чужий → 403
- [x] 14 нових тестів (upload/delete/set-primary/limit/type/403); **298 тестів всього — OK**

### Frontend
- [x] `api/client.ts`: `apiUpload()` — multipart POST без Content-Type header (дозволяє браузеру встановити boundary)
- [x] `api/local.ts`: `uploadImages()`, `deleteImage()`, `setPrimaryImage()`
- [x] `PhotoUploadBlock.tsx` — блок для edit mode: сітка превью, hover-кнопки «Гол.» / «✕», авто-рефреш
- [x] `CreateModePhotoPicker` (inline в LocalListingForm) — буферує файли до submit, превью з blob URL
- [x] `LocalListingForm.tsx` — edit mode: `<PhotoUploadBlock>` з існуючими фото; create mode: `<CreateModePhotoPicker>`, фото завантажуються після create
- [x] **27 Next.js роутів, 0 TS-помилок, npm run build OK**

---

## C2C-промт 5 — Lifecycle + платне просування (завершено 2026-07-02)

### Backend
- [x] `LocalListing`: `expires_at` (created_at + 30 дн., `LOCAL_LISTING_EXPIRY_DAYS`), `expiry_warned`, `promoted_until`, `bumped_at`
- [x] `PromotionTariff(code, name, type[renew/bump/top], price, currency, duration_days)` — редагується в адмінці
- [x] Data migration: 4 seed-тарифи (заглушки ціни; підігнати перед продом)
- [x] Celery beat: `warn_expiring_listings` (за 3 дні, один раз) о 9:15 + `expire_listings` (авто-зняття) о 9:20
- [x] `Payment`: +`local_listing` FK, +`tariff` FK, +`LOCAL_LISTING_PROMOTE` purpose
- [x] `POST /api/v1/local/listings/<pk>/promote/` → Payment + LiqPay checkout (тільки власник)
- [x] `GET /api/v1/local/tariffs/` — список активних тарифів
- [x] LiqPay callback: застосовує ефект тарифу (renew→extends expires_at, top→promoted_until, bump→bumped_at); idempotent
- [x] Сортування /ua: TOP (promoted_until > now) → bumped_at → created_at; фільтри не зламані
- [x] 16 нових тестів; **314 тестів всього — OK**

### Frontend
- [x] `types.ts`: `expires_at`, `expiry_warned`, `promoted_until`, `bumped_at`, `PromotionTariff`, `PromoteCheckout`
- [x] `api/local.ts`: `tariffs()`, `promote()`
- [x] `LocalListingCard`: ТОП-бейдж (золота рамка + мітка «ТОП»)
- [x] `PromoteModal`: вибір тарифу → redirect на LiqPay checkout; **sandbox-попередження** жирним
- [x] `/me/local-listings`: термін дії, ⚠️ за 3 дні, кнопки «Продовжити» (expired/expiring) / «Підняти» / «ТОП»
- [x] **27 Next.js роутів, 0 TS-помилок, npm run build OK**

### Архітектурне рішення
- Тарифи в БД (не хардкод) — ціни змінюються без деплою
- `_apply_local_listing_promote()` у `payments/views.py` — логіка callback у одному місці
- Idempotency: повторний COMPLETED-колбек ігнорується (Payment вже COMPLETED)
- **SANDBOX**: `LIQPAY_SANDBOX=true` за замовчуванням. LiqPay не достукається до localhost — повноцінний тест тільки на публічному URL

---

## C2C-промт 6 — Захист контактів + антиспам + скарги + баны (завершено 2026-07-03)

### Backend
- [x] `CustomUser`: `is_banned` + `is_email_verified` (мітка; повноцінна email-верифікація — окремо)
- [x] `LocalListing`: `has_contact_in_text` (BooleanField, db_index) — прапор антиспаму
- [x] `local_listings/antispam.py`: `detect_contacts(text)` — детект телефону, URL, месенджерів
  - **Що вважається контактом**: `+380...` / `0XX-XXX-XX-XX`, `http(s)://`, `www.`, `.com/.ua/.net` TLD, `telegram/viber/whatsapp + @username/link`
  - **НЕ спрацьовує** на: рік (4 цифри), пробіг (ціле без телефонного формату), ціну, об'єм двигуна
- [x] Режим антиспаму: `ANTISPAM_MODE=soft` (дефолт env) — прапор без блокування; `hard` — ValidationError; `off` — вимкнено
- [x] Оголошення з контактом у тексті → `has_contact_in_text=True` (лишається pending на модерацію)
- [x] Повідомлення з контактом → попередження в відповіді (`warning` ключ), повідомлення надсилається
- [x] `GET /api/v1/local/listings/<id>/contact/` — телефон тільки авторизованому (rate-limit 20/год, scope `contact`)
- [x] `contact_phone` ЗАВЖДИ `null` у публічному detail та list (тільки через /contact/)
- [x] `reports` app: `Report(reporter, listing?, reported_user?, reason, comment, status[new|reviewed|dismissed])`
- [x] `POST /api/v1/reports/` — авторизований; один активний звіт на (reporter, об'єкт)
- [x] Django Admin: черга скарг — дії «Сховати оголошення», «Забанити користувача», «Відхилити»
- [x] Ban: `is_banned=True` + `is_active=False` + активні оголошення → `hidden`; забанений не може увійти
- [x] Users Admin: `ban_users` / `unban_users` bulk actions
- [x] Throttle scope `contact`: 20/год (env `THROTTLE_CONTACT_RATE`)
- [x] **334 тести всього — OK**

### Frontend
- [x] `api/local.ts`: `getContact(id)` — GET /contact/ ендпоінт
- [x] `api/reports.ts`: `reportsApi.create()`
- [x] `lib/types.ts`: `ReportReason`, `ReportPayload`
- [x] `LocalListingDetail.tsx`: «Показати телефон» → клік → GET /contact/ (авторизованому показує номер; анониму → /login)
- [x] `ReportButton.tsx` — модальне вікно з вибором причини і коментарем; z'являється для не-власників
- [x] **0 TS-помилок, npm run build OK**

### Архітектурне рішення
- Контакт НЕ повертається в жодному серіалізаторі (list/detail/owner) — тільки через окремий /contact/ ендпоінт
- Rate-limit на /contact/ захищає від масового витягу телефонів скриптом
- Антиспам «м'який»: підозріле оголошення не блокується, а іде на модерацію з прапором `has_contact_in_text` — рішення за адміном
- Бан реалізований через Django's `is_active=False` (JWT автоматично відхиляє неактивних)

---

## C2C-промт 7 — Угоди + відгуки + рейтинги + юридичні доповнення (завершено 2026-07-03)

### Backend
- [x] `deals` Django-додаток: `Deal(listing FK, seller FK, buyer FK, status[proposed|confirmed|cancelled], confirmed_at)`
- [x] UniqueConstraint `(listing, buyer)` — один запит покупця на одне оголошення
- [x] `Review(deal OneToOne, author FK, target FK, rating 1-5, text)` — тільки після підтвердженої угоди; `clean()`: автор = покупець по угоді
- [x] `deals/services.py`:
  - `propose_deal(listing, seller, buyer_id)` — перевірка власника, покупець має бути учасником діалогу, без дублів; нотифікація `deal_proposed`
  - `confirm_deal(deal, buyer)` — тільки покупець, перехід у `confirmed`, оголошення → `sold`; нотифікація `deal_confirmed`
  - `cancel_deal(deal, user)` — будь-яка сторона, лише з `proposed`; нотифікація `deal_cancelled`
  - `create_review(deal, author, rating, text)` — тільки покупець, угода `confirmed`, один відгук; нотифікація `review_received`
  - `seller_rating(seller_id)` → `{confirmed_deal_count, review_count, avg_rating, has_badge, badge_threshold}`
- [x] 6 ендпоінтів `/api/v1/deals/`: list+create, confirm, cancel, review, seller-rating, listing-buyers
- [x] `notifications/models.py`: 4 нові типи — `deal_proposed`, `deal_confirmed`, `deal_cancelled`, `review_received`
- [x] `SELLER_BADGE_THRESHOLD = 3` (env, дефолт 3) — бейдж «✓ Перевірений продавець» після ≥3 підтверджених угод
- [x] `LocalListingListSerializer`: `seller_has_badge` (SerializerMethodField)
- [x] `LocalListingDetailSerializer`: `seller_avg_rating`, `seller_deal_count` (SerializerMethodFields)
- [x] Міграція `deals/0001_initial`, `notifications/0002_deal_types`
- [x] **31 новий тест; 365 тестів всього — OK**

### Frontend
- [x] `api/deals.ts`: list, propose, confirm, cancel, review, sellerRating, listingBuyers
- [x] `lib/types.ts`: `DealStatus`, `DealUser`, `DealListing`, `DealReview`, `Deal`, `ReviewPayload`, `SellerRating`; нові типи нотифікацій
- [x] `app/me/deals/page.tsx` — «Угоди та відгуки»: угоди як покупець (confirm/cancel/зірковий відгук) + як продавець (cancel). `DealCard` з умовними кнопками
- [x] `app/me/local-listings/page.tsx`: «✅ Позначити проданим» (active) → модальне вікно → вибір покупця з діалогів → `propose_deal`
- [x] `app/local/[id]/LocalListingDetail.tsx`: бейдж «✓ Перевірений продавець» + зірки + рейтинг продавця в синій панелі
- [x] `app/rules/page.tsx` — Правила розміщення: 8 розділів, бурштинове попередження «Шаблон — потребує перевірки юристом», C2C-застереження (платформа — посередник, не сторона угоди)
- [x] `components/layout/Footer.tsx`: посилання `/rules` між /terms і /privacy
- [x] `components/local/LocalListingForm.tsx`: checkbox «Погоджуюсь з правилами» → справжнє посилання `/rules`
- [x] `app/me/page.tsx`: «🤝 Угоди та відгуки» в меню кабінету
- [x] **0 TS-помилок, npm run build OK**

### Архітектурне рішення
- Anti-nakrutka: відгук прив'язаний до `Deal` OneToOne + `buyer_id == author.pk` → неможливо залишити відгук самому собі або без реальної угоди
- Бейдж `seller_has_badge` — обчислюється в серіалізаторі через SQL COUNT (≥threshold confirmed deals) без кешу — актуально в реальному часі
- Бейдж `SELLER_BADGE_THRESHOLD` — env-переопределяємо без деплою
- Всі юридичні тексти `robots: {index: false}` і позначені «Шаблон — потребує перевірки юристом»
- C2C-застереження: «Платформа є посередником, а не стороною угоди» — у `/rules` розділ 6 та `/terms`

---

## Дальше (C2C-черга)

| # | Промт | Що робити |
|---|-------|-----------|
| ~~C2C-3~~ | ~~Повідомлення~~ | ~~Non-realtime чат~~ ✓ |
| ~~C2C-4~~ | ~~Обране + сповіщення~~ | ✓ |
| ~~C2C-5~~ | ~~Lifecycle + просування~~ | ✓ (SANDBOX) |
| ~~C2C-6~~ | ~~Захист контактів + антиспам~~ | ✓ |
| ~~C2C-7~~ | ~~Рейтинги/відгуки + юридичні доповнення~~ | ✓ ЗАВЕРШЕНО |

**C2C-блок 1–7 повністю завершено. Далі — деплой на Railway.**

---

## Промт 15 — Docker Compose: повний стек (завершено 2026-07-03)

### Що створено
- [x] `Dockerfile.backend` — multi-stage (python:3.12-slim): builder → runtime; gunicorn 26.0.0
- [x] `Dockerfile.frontend` — multi-stage (node:20-alpine): deps → builder → runtime; `npm start`
- [x] `.dockerignore` — виключає venv, __pycache__, .env, media, db.sqlite3, frontend/ з бекенд-контексту
- [x] `frontend/.dockerignore` — виключає node_modules, .next, .env.local з фронтенд-контексту
- [x] `docker-compose.yml` — 7 сервісів: db, redis, backend, frontend, bot, celery_worker, celery_beat, nginx
- [x] `nginx/nginx.conf` — reverse proxy: `/api`, `/admin` → backend:8000; `/static/`, `/media/` → volumes; `/` → frontend:3000. Місце для SSL (коментар)
- [x] `docker/entrypoint.sh` — backend startup: migrate → collectstatic → gunicorn
- [x] `docker/bot_entrypoint.sh` — перевіряє TELEGRAM_BOT_TOKEN; без токену → exit 0 (без restart-loop)
- [x] `.env.docker.example` — робочі дефолти (сайт піднімається без ручного редагування)
- [x] `core/settings.py`: додано `STATIC_ROOT` + виправлено `STATIC_URL='/static/'`
- [x] SSR-fix: `INTERNAL_API_URL` в 3 серверних компонентах (`local/[id]/page.tsx`, `listings/[id]/page.tsx`, `sitemap.ts`) — SSR-запити через Docker-мережу `http://backend:8000`
- [x] `requirements.txt`: `gunicorn==26.0.0`

### Перевірка (результат)
- [x] `docker compose build` — обидва образи зібрані без помилок
- [x] `docker compose up -d` — 7 сервісів запущені
- [x] `http://localhost/` → **200** (фронтенд через nginx) ✅
- [x] `http://localhost/api/v1/local/listings/` → **200** (DRF API) ✅
- [x] `http://localhost/admin/` → **302** (Django admin → login) ✅
- [x] Bot: exit 0 без TELEGRAM_BOT_TOKEN (не перезапускається) ✅
- [x] Звичайна розробка (runserver / npm run dev) — не зачеплена ✅

### Архітектурне рішення
- `NEXT_PUBLIC_API_URL=http://localhost` — бекується у клієнтський JS (браузер → nginx → backend)
- `INTERNAL_API_URL=http://backend:8000` — runtime env для SSR (Next.js сервер → backend напряму по Docker-мережі)
- Бот: `restart: on-failure` — не перезапускується при exit 0; при крашу (exit non-0) — перезапускується
- Спільні Docker-volumes: `static` і `media` між backend і nginx

---

## Фікс 502 Bad Gateway (2026-07-04)

### Причина 502
nginx стартував одразу після запуску контейнера backend — але gunicorn слухає порт 8000
лише ПІСЛЯ того, як відпрацюють `migrate` + `collectstatic`. На свіжій БД це займає 20-60 секунд.
Поки gunicorn не піднявся, nginx повертав `502 Bad Gateway` на всі запити.

Друга проблема: `celery_worker` і `celery_beat` використовували `memory://` брокер замість Redis,
бо Django-налаштування обирають `memory://` при `DEBUG=true` (налаштування `core/settings.py`).

### Що виправлено (`docker-compose.yml`)
- [x] Додано `healthcheck` до сервісу `backend` — Python socket-перевірка порту 8000:
  `python -c "import socket; s=socket.create_connection(('localhost',8000),2); s.close()"`
- [x] `nginx` тепер залежить від `backend: condition: service_healthy` — стартує лише після
  того, як gunicorn реально слухає порт (не просто "контейнер запущений")
- [x] `celery_worker` і `celery_beat` отримали `environment: DEBUG=false` — примусово
  використовують Redis-брокер (`redis://redis:6379/0`) незалежно від `.env`

### Перевірка після фіксу
- [x] `docker compose down && docker compose up -d` — nginx чекає `backend: Healthy` перед стартом ✅
- [x] `http://localhost/` → **200** ✅
- [x] `http://localhost/admin/` → **302** ✅
- [x] `http://localhost/api/v1/local/listings/` → **200** ✅
- [x] `celery_worker` → `Connected to redis://redis:6379/0` ✅

---

## Дальше (очередь задач до продакшена)

| # | Блокер | Что делать |
|---|--------|------------|
| 1 | ~~Ставки растаможки~~ | ✅ Снят — акциз/мито/НДС/ПФ актуальны на янв–июнь 2026 |
| 2 | ~~Тарифы Copart/IAAI~~ | Baseline готов (seed_auction_fees, 50 тиров). ⚠ Калибровать под реальный тариф брокера |
| 3 | **Тарифы фрахта** | UsLandRoute, OceanFreight, EuToUa — реальные котировки от брокера |
| 4 | ~~Живой курс НБУ~~ | ✅ Снят — `fetch_nbu_rates --date YYYYMMDD` обновляет ExchangeRate из bank.gov.ua |
| 5 | **Платные API для истории** | Carfax/BidFax (история ДТП и торгов) — договоры. ~~Opendatabot~~ — ✅ реализован |
| 6 | ~~**Верификация дилеров**~~ | ✅ Снят — DealerApplication + apply/approve/reject + B2B гейтинг |
| 7 | ~~Платёжный шлюз~~ | ✅ Снят — LiqPay sandbox готов; для продакшена: LIQPAY_SANDBOX=false + реальные ключи |
| 8 | **Прожиточный минимум 2026** | Проверить `LIVING_WAGE_UAH` в `seed_rates.py` на дату деплоя |
| 9 | ~~**S3 + PostgreSQL**~~ | ✅ Снят — dj-database-url + django-storages, включаются env-переменными |
| 10 | **Apify-токен** | Подключить реальный актор Copart/IAAI для `ApifyLotProvider` |
| 11 | ~~**Безопасность**~~ | ✅ Снят — промт 8: throttling, JWT blacklist, security headers |
| 12 | ~~**Кэш и производительность**~~ | ✅ Снят — промт 9: Redis/кэш тарифов, индексы, N+1 |
| 13 | ~~**Celery — фоновые задачи**~~ | ✅ Снят — промт 10: Celery+beat, fetch_nbu_rates_task (daily, cache invalidate), import_lot_task, send_notification stub |
| 14 | ~~**Telegram-уведомления**~~ | ✅ Снят — промт 11: telegram_bot, deep-link привязка, send_notification, автопостинг |
| 15 | ~~**Фронтенд: продакшн-полировка, SEO**~~ | ✅ Снят — промт 12: SEO, OG-карточки, sitemap, 404/error, скелетоны, DemoBanner-флаг |
| 16 | ~~**Юридические страницы**~~ | ✅ Снят — промт 13: /terms, /privacy, /cookies + cookie-баннер + consent |
| 17 | ~~**QA E2E-тесты**~~ | ✅ Снят — промт 14: 38 E2E-тестов + Playwright + PRODUCTION_ROADMAP.md |
| ~~18~~ | ~~**DevOps: Docker Compose**~~ | ✅ Знятий — docker-compose.yml, Dockerfile.backend/frontend, nginx, entrypoint. Сайт на http://localhost |
| **19** | **Деплой на Railway** | Переиспользує Dockerfile'и. railway.toml + env → push → prod |

---

## Промт 14 — QA E2E-тесты (завершено 2026-06-24)

### Backend E2E (tests/test_e2e.py — 38 тестов)
- [x] **Auth chain**: регистрация (с consent) → JWT → профиль → agreed_to_terms_at записан
- [x] Без токена → 401; неверный пароль → 401; без consent → 400
- [x] **Калькулятор API**: POST /api/v1/pricing/calculate/ → 201 → все поля breakdown; total_usd = сумма компонентов; is_estimate=true; known auction_fee=$504; customs_value=$6800; сохраняется в Calculation
- [x] **LiqPay checkout**: создаёт Payment(pending), возвращает checkout_url; duplicate order_id → 400; без auth → 401
- [x] **LiqPay callback валидный**: статус → completed, listing → in_stock
- [x] **LiqPay callback невалидная подпись**: 400, статус остаётся pending, listing не трогается
- [x] **LiqPay идемпотентность**: двойной callback → payment не задваивается, listing = in_stock ровно один раз
- [x] **B2B гейтинг**: anon → 401/403; buyer → 403 /b2b/board/ и 404 wholesale detail; dealer → 200; admin → 200; каталог anon — wholesale не виден
- [x] **Dealer flow**: apply → 403 перед одобрением → approve → is_verified_dealer=True → 200 на B2B
- [x] **Throttle**: ScopedRateThrottle deny → 429; anon → 401 (не throttle)
- [x] `LiqPayClient.from_settings()` исправлен: читает из Django settings (override_settings работает в тестах)

### Frontend E2E (Playwright)
- [x] `@playwright/test` установлен как devDependency
- [x] `playwright.config.ts` — baseURL localhost:3000, chromium
- [x] `e2e/catalog.spec.ts`: каталог загружается; demo-banner; калькулятор form; 404-страница
- [x] `e2e/register.spec.ts`: чекбокс consent есть, required, ссылки /terms /privacy; footer-ссылки
- [x] `package.json`: scripts `test:e2e`, `test:e2e:ui`

### Документация
- [x] `docs/PRODUCTION_ROADMAP.md` — простым языком для владельца:
  - Таблица «что проверяется автоматически»
  - Пошаговая инструкция ручной проверки LiqPay sandbox (ключи, ngrok, тестовая карта 4242...)
  - Финальный чеклист «GO LIVE» (12 пунктов)
  - Что дальше: промт 15 (DevOps)

### Итог
- [x] 199 backend-тестов OK (`python manage.py test`)
- [x] 38 новых E2E-тестов
- [x] TypeScript 0 ошибок (`npx tsc --noEmit`)

---

## Промт 13 — Юридические страницы (завершено 2026-06-24)

### Бэкенд
- [x] `CustomUser.agreed_to_terms_at` (DateTimeField, null=True, blank=True) + миграция 0006
- [x] `RegisterSerializer`: новое поле `agreed_to_terms` (bool, write_only); валидация — 400 если False/отсутствует; при success `agreed_to_terms_at = timezone.now()`
- [x] Тесты (4): без поля → 400; False → 400; True → 201; `agreed_to_terms_at` устанавливается

### Frontend — страницы
- [x] `/terms` — «Умови використання» (шаблон, 7 разделов, предупреждение «перевірки юристом»)
- [x] `/privacy` — «Політика конфіденційності» (шаблон, 8 разделов, ЛЗПД ссылка)
- [x] `/cookies` — «Політика щодо файлів cookie» (шаблон, таблица cookie, 4 раздела)
- [x] Все три: `robots: { index: false }`, начинаются с янтарного баннера «Шаблон — потребує перевірки юристом»

### Frontend — cookie-баннер
- [x] `CookieBanner.tsx` — клиентский компонент; показывается при первом визите
- [x] Две кнопки: «Лише необхідні» и «Прийняти всі» → запись в `localStorage('cookie_consent')`
- [x] После выбора баннер скрывается; при повторном визите — не появляется
- [x] Добавлен в `app/layout.tsx` (работает на всех страницах)

### Frontend — Footer
- [x] Добавлены ссылки: «Умови використання», «Конфіденційність», «Cookie» с `<Link>` (Next.js)
- [x] `<nav aria-label="Юридичні документи">` для семантики

### Frontend — форма регистрации
- [x] Чекбокс «Погоджуюсь з Умовами використання та Політикою конфіденційності» (required)
- [x] Ссылки /terms и /privacy открываются в новой вкладке (`target="_blank"`)
- [x] Фронтенд-валидация: кнопка submit недоступна только по HTML required; сообщение об ошибке на уровне JS
- [x] `agreed_to_terms: true` включается в тело запроса к API

### Build
- [x] `npx tsc --noEmit` — 0 ошибок
- [x] `python manage.py test` — 161 тест OK

---

## Промт 12 — Frontend SEO + продакшн-полировка (завершено 2026-06-24)

### SEO — мета и шеринг
- [x] `layout.tsx`: `metadataBase`, title template `%s | AUTOforYOU`, OpenGraph defaults, Twitter card
- [x] `listings/[id]/page.tsx` → Server Component: `generateMetadata` с OG-тегами
  (og:title, og:description, og:image = фото авто, og:url canonical)
  → красивая превью-карточка при шеринге ссылки в Telegram
- [x] Metadata на всех страницах: каталог, главная, калькулятор, кабинет, login, register
- [x] Slug URL листингов: `/listings/42-toyota-camry-2020` (parseInt-совместим с `/listings/42`)
- [x] Canonical URL на базе `NEXT_PUBLIC_SITE_URL`

### Sitemap и robots
- [x] `app/sitemap.ts` — динамический: статические маршруты + активные листинги с бэкенда (revalidate 1h)
- [x] `app/robots.ts` — Allow `/`, `/listings`, `/calculator`; Disallow `/me/`, `/b2b/`, `/admin/`, `/api/`

### Состояния загрузки и ошибок
- [x] `app/not-found.tsx` — кастомная 404 с брендингом и ссылкой на каталог
- [x] `app/error.tsx` + `app/global-error.tsx` — «Щось пішло не так» + кнопка «Повторити»
- [x] `components/ui/Skeleton.tsx` + `ListingCardSkeleton` + `ListingsGridSkeleton`
- [x] `app/listings/loading.tsx`, `app/listings/[id]/loading.tsx`, `app/me/loading.tsx`
- [x] ListingsGrid: скелетон вместо спиннера; кнопка «Спробувати ще раз» при ошибке API
- [x] Пустое состояние с иконкой 🚗 и подсказкой «Спробуйте змінити фільтри»

### Изображения и производительность
- [x] ListingCard + ListingDetail: `image || source_url` с SVG-плейсхолдером (нет эмодзи в alt)
- [x] `next.config.ts`: паттерны для AWS S3, Cloudflare R2, Copart/IAAI CDN, CloudFront
- [x] `VehicleImage.source_url` добавлен в TypeScript-типы
- [x] `sizes`, `priority` на главном фото; `fill` + `object-cover` на всех карточках

### DemoBanner
- [x] `NEXT_PUBLIC_DEMO_MODE=false` скрывает баннер на проде (реальные тарифы)
- [x] По умолчанию включён (`=true`). `is_estimate` в ответе API остаётся всегда.

### Доступность и адаптив
- [x] `focus:ring` на всех интерактивных элементах (кнопки, ссылки, тумбнейлы)
- [x] `aria-label`, `role=alert`, `role=group`, `<nav aria-label>`, `<article>` в ListingCard
- [x] `aria-hidden` на декоративных иконках; SVG-плейсхолдер вместо эмодзи
- [x] Пагинация в `<nav>`, семантические заголовки `<h1>`/`<h2>`

### Build
- [x] `npm run build` — 16 роутов, 0 ошибок TypeScript
- [x] `python manage.py test` — 157 тестов OK

---

## Промт 11 — Telegram-бот (завершено 2026-06-24)

### App telegram_bot
- [x] `aiogram==3.29.0` добавлен в requirements.txt
- [x] Django-приложение `telegram_bot` (отдельный процесс, включается `TELEGRAM_BOT_TOKEN`)

### Привязка аккаунта (deep-link)
- [x] `CustomUser.telegram_id` (BigIntegerField, nullable, unique) + миграция 0005
- [x] `TelegramLinkToken(token UUID, user FK, expires_at, used)` + миграция 0001
- [x] `GET /api/v1/telegram/link-token/` — JWT-защищённый, генерирует токен и deep-link (30 мин)
- [x] `/start link_<uuid>` → записывает `telegram_id`, помечает токен `used=True`
- [x] Просроченный / уже использованный → вежливый отказ

### Middleware
- [x] `UserBindingMiddleware`: по `telegram_id` → Django User в `data['telegram_user']` + `is_linked`

### Команды бота (v1)
- [x] `/start` (с deeplink и без)
- [x] `/help`
- [x] `/latest` — 3–5 свежих retail-листингов (in_stock/in_transit) с фото/ценой/ссылкой

### Уведомления
- [x] `integrations.tasks.send_notification` реализован через `aiogram Bot.send_message`
- [x] Без токена / не привязан → `{sent: False}` (no-op)
- [x] Поддержка inline-кнопок (параметр `buttons=[{text, url}]`)

### Автопостинг в канал
- [x] `telegram_bot.tasks.post_listing_to_channel` (Celery-задача)
- [x] Retail-листинг → `TELEGRAM_CHANNEL_ID`; `is_express_buyout` → `TELEGRAM_B2B_CHANNEL_ID`
- [x] Throttling: пауза 3 с между постами, ретрай на `TelegramRetryAfter`
- [x] Сигнал `post_save(Listing, created=True)` → `.delay()` задачи

### Webhook (прод)
- [x] `POST /api/v1/telegram/webhook/` с проверкой `X-Telegram-Bot-Api-Secret-Token`
- [x] `python manage.py set_webhook <url>` — установить webhook; `--delete` — удалить
- [x] В dev — polling (`python manage.py run_bot`)

### Management commands
- [x] `python manage.py run_bot` — polling; без токена — понятное сообщение, сайт не ломается
- [x] `python manage.py set_webhook <url>` — установить/удалить webhook для прод

### Тесты (20 новых, 157 всего)
- [x] `TelegramLinkToken`: valid / expired / used
- [x] Link-token API: 401 без auth, 200 с токеном
- [x] Link flow: токен помечается used, telegram_id записывается
- [x] `send_notification`: нет токена → no-op; не привязан → no-op; привязан → отправка (мок)
- [x] `post_listing_to_channel`: нет токена / листинг не найден / нет channel_id → no-op
- [x] Сигнал: retail → delay() вызван; wholesale+express → delay() вызван; обычный wholesale → нет; update → нет

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

---

## Промт 9 — Кэш и производительность (завершено 2026-06-23)

### Кэш-бэкенд
- [x] `django-redis==5.4.0` добавлен в requirements.txt
- [x] `CACHES`: `REDIS_URL` задан → django-redis; не задан → LocMemCache (dev без Redis)
- [x] `.env.example`: `REDIS_URL` плейсхолдером с объяснением

### Кэширование тарифных справочников (с инвалидацией)
- [x] `pricing/cache.py`: 8 геттеров (AuctionFeeTier, AuctionFixedFee, UsLandRoute, OceanFreight, EuToUa, ExchangeRate, CustomsExcise, PensionBracket) — TTL 24ч
- [x] `pricing/signals.py`: `post_save` + `post_delete` на все 8 моделей → `cache.delete(key)`
- [x] `pricing/apps.py`: `ready()` регистрирует сигналы
- [x] `pricing/views.py`: `CalculateView` использует in-memory фильтрацию по кэшу — 0 запросов к БД на cache hit (было 8+)
- [x] Инвалидация мгновенная: правка ставки в админке → следующий расчёт сразу использует новую

### DB-индексы
- [x] `Listing`: индексы на `status`, `channel`, составной `(channel, status)`, `price` → миграция 0005
- [x] `Vehicle`: индекс на `fuel_type` → миграция 0003 (VIN уже уникальный = индекс)

### Устранение N+1
- [x] `ShipmentListSerializer.get_vehicle_count`: заменён `obj.vehicles.count()` (N DB-хитов) → prefetch cache (`len` из `_prefetched_objects_cache`)
- [x] Листинги: `select_related('vehicle','seller') + prefetch_related('vehicle__images')` уже было — подтверждено тестом
- [x] **Доказательство**: `assertNumQueries(3)` для каталога — 3 запроса для любого числа листингов (COUNT + JOIN + prefetch_images), не растёт при 5 или 15 объектах

### Тесты (10 новых, 133 всего)
- [x] Кэш тарифов: save → invalidate; delete → invalidate; переcчитывает из БД с новым значением
- [x] `TestListingListQueryCount`: 5 листингов = 3 запроса; 15 листингов = 3 запроса (N+1 отсутствует)

---

## Промт 8 — Безопасность (завершено 2026-06-23)

### Throttling (защита платных API)
- [x] DRF `AnonRateThrottle` (60/hr) + `UserRateThrottle` (300/hr) — дефолты, env-overridable
- [x] `ScopedRateThrottle` scope `expensive` (10/hr) на `/registry/` и `/decode/`
- [x] `/vehicles/<vin>/registry/` — только `IsAuthenticated` (Opendatabot платный)
- [x] Кэш RegistryReport проверяется ДО внешнего вызова (подтверждено в views.py)
- [x] Тесты: анон → 401/403; throttle deny → 429

### CORS / ALLOWED_HOSTS
- [x] `CORS_ALLOW_ALL_ORIGINS = DEBUG` (dev только)
- [x] `CORS_ALLOWED_ORIGINS` env-overridable: `CORS_ALLOWED_ORIGINS=https://yourdomain.com,...`
- [x] `ALLOWED_HOSTS` из env; при DEBUG=True → `['*']`; prod без env → `[]`

### JWT
- [x] Access: 15 мин (было 1 час), Refresh: 7 дней (было 30)
- [x] `rest_framework_simplejwt.token_blacklist` добавлен в INSTALLED_APPS + миграция
- [x] `BLACKLIST_AFTER_ROTATION = True`
- [x] `POST /api/v1/auth/token/logout/` — кладёт refresh в blacklist
- [x] Тест: отозванный refresh → 401 при попытке обновить access

### Security-заголовки (только при DEBUG=False)
- [x] `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS`
- [x] `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`
- [x] `X_FRAME_OPTIONS = 'DENY'`, `SECURE_CONTENT_TYPE_NOSNIFF`
- [x] В dev (DEBUG=True) — все выключены, localhost работает по HTTP

### Аудит
- [x] `python manage.py check --deploy` — 0 ошибок, 13 warnings (2 безопасности: SECRET_KEY и ALLOWED_HOSTS — оба устраняются env-переменными перед продом)
- [x] `.gitignore` проверен: `.env`, `*.sqlite3`, `backups/`, `*.log` не в git. В git только `.env.example`
- [x] LiqPay callback: подпись SHA1 проверяется в `decode_callback()`. Идемпотентный guard добавлен — повторный COMPLETED-колбэк пропускается, листинг не разблокируется дважды

### Тесты (10 новых, 127 всего)
- [x] Анон на registry → 401; auth → 200
- [x] ScopedRateThrottle deny → 429 (registry и decode)
- [x] Logout → ok; blacklisted refresh → 401 на /token/refresh/; logout без auth → 401; logout без refresh → 400

---

## Промт 7 — PostgreSQL + S3 + разделение настроек (завершено 2026-06-22)

### Безопасность данных
- [x] git push (4 коммита отправлены на GitHub до начала работы)
- [x] Резервная копия БД: `backups/db_20260622.sqlite3` + `backups/data_20260622.json`
- [x] `.gitignore` дополнен: `backups/`, `*.env` — никогда не попадут в git

### Настройки через env (core/settings.py переписан)
- [x] `SECRET_KEY` — из env; старый insecure-ключ остаётся только если ключ не задан (dev fallback)
- [x] `DEBUG` — `False` по умолчанию; для dev: `DEBUG=true` в `.env`
- [x] `ALLOWED_HOSTS` — из env; при `DEBUG=true` → `['*']`
- [x] `CORS_ALLOW_ALL_ORIGINS` — только при `DEBUG=True` (prod: явный список)

### База данных (dj-database-url)
- [x] `DATABASE_URL` не задан → SQLite (dev, без настройки, локальная разработка не сломана)
- [x] `DATABASE_URL=postgres://...` → PostgreSQL (любой провайдер: Railway, Heroku, VPS)
- [x] `conn_max_age=600` — connection pooling для Postgres

### S3-хранилище (django-storages + boto3)
- [x] S3-переменные (`S3_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) не заданы → `media/` локально
- [x] S3-переменные заданы → `DEFAULT_FILE_STORAGE = S3Boto3Storage`
- [x] `S3_ENDPOINT_URL` — поддержка Cloudflare R2 / MinIO (S3-совместимые)
- [x] `AWS_DEFAULT_ACL = 'private'` + подписанные URL

### Management command upload_lot_photos
- [x] Скачивает фото из `VehicleImage.source_url` → сохраняет в хранилище (S3 или media/)
- [x] `--dry-run` — показать список без скачивания
- [x] `--limit N` — обработать первые N фото

### requirements.txt
- [x] `dj-database-url==2.3.0`
- [x] `django-storages[s3]==1.14.4`
- [x] `boto3==1.38.38`

### .env.example
- [x] Полный шаблон: SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_URL, S3_*, LiqPay, интеграции, Email

### DEPLOY_NOTES.md
- [x] Пошаговая инструкция простым языком (без жаргона): бэкап, Postgres, S3, откат

### Тесты
- [x] 119 тестов зелёные на SQLite (без DATABASE_URL и S3-переменных)
- [x] `python manage.py check` — 0 ошибок

---

## Промт 6 — Импорт лотов аукционов (завершено 2026-06-22)

### AuctionLotProvider (за интерфейсом)
- [x] ABC `AuctionLotProvider.fetch_lot(lot_url_or_data)` → нормализованный dict лота
- [x] `_normalize_lot()` — приведение полей: VIN→upper, auction/fuel_type → choices, final_bid→Decimal
- [x] `ManualLotProvider` — нормализует переданный dict, без внешних зависимостей, рабочий MVP
- [x] `ApifyLotProvider` — заглушка под Apify-актор; без APIFY_TOKEN → demo=True, не падает
- [x] Фабрика `get_lot_provider()` — читает `APIFY_TOKEN` из settings
- [x] `APIFY_TOKEN` в settings.py (env) + плейсхолдер в .env.example

### Маппинг лот → доменные модели (integrations/importer.py)
- [x] `import_lot(lot_data, seller)` — возвращает `(Vehicle, Listing, created)`
- [x] `Vehicle.update_or_create(vin=...)` — идемпотентно, upsert
- [x] `VehicleImage.get_or_create(vehicle, source_url)` — URL фото, is_primary для первого
- [x] `vehicles.VehicleImage`: добавлен `source_url` CharField, `image` стал nullable (миграция 0002)
- [x] `# фото в S3 — промт 7` — пометки в коде
- [x] `Listing.get_or_create(vehicle, status=in_transit)` — retail, цена из final_bid
- [x] Повторный импорт того же VIN: Vehicle обновляется, Listing — обновляется цена, дублей нет

### Эндпоинт + команда
- [x] POST /api/v1/lots/import/ (IsAdminUser)
- [x] `LotImportRequestSerializer`: source=manual/apify, lot_data или lot_url
- [x] Возвращает 201 при создании, 200 при обновлении, 400 при ошибке провайдера/VIN
- [x] Management command `import_lot` — `--json`, `--file`, `--source apify --url`, `--seller-email`
- [x] ⚠ Импорт по расписанию — Celery (промт 10)

### Тесты (22 новых, 119 всего)
- [x] ManualLotProvider: valid → нормализованный dict, missing VIN → error, short VIN → error, not dict → error
- [x] ManualLotProvider: vin uppercased, unknown auction → 'other', photos preserved
- [x] ApifyLotProvider: без токена → demo=True, не бросает
- [x] import_lot: создаёт Vehicle/Listing, сохраняет photo URLs, первое фото is_primary=True
- [x] import_lot: повтор → 1 Vehicle, 1 Listing, created=False
- [x] import_lot: error в lot_data → ValueError
- [x] POST /api/v1/lots/import/: admin→201, non-admin→403, unauth→401, bad VIN→400, repeat→200
- [x] POST с apify без токена: не 500

### Следующий шаг (промт 7)
PostgreSQL + разделение настроек + S3 (перекладывание фото)

---

## Промт 5 — Opendatabot: реальный реестр авто UA (завершено 2026-06-22)

### Закрытые пробелы гейтинга (ревью промта 4)
- [x] B2B board 403 неверифицированным — уже был закрыт (IsVerifiedDealerOrAdmin + тест)
- [x] GET /api/v1/listings/<id>/ wholesale → 404 для неверифицированных (queryset фильтр уже был)
- [x] Добавлен тест `TestWholesaleListingDetailGating` (5 кейсов): anon/buyer→404, dealer/admin→200, retail→доступен всем

### RegistryReport (кэш UA реестров)
- [x] Модель `RegistryReport`: vin (nullable), plate (nullable), provider, payload (JSONField), demo, created_at
- [x] Миграция 0002_registryreport
- [x] `RegistryReportAdmin` в admin.py

### RealOpendatabotProvider
- [x] Реализован `RealOpendatabotProvider(OpendatabotProvider)` — httpx-клиент
- [x] Без ключа (`OPENDATABOT_API_KEY=''`) → demo=True, no 500, понятный fallback
- [x] С ключом → GET `_ODB_VIN_URL` или `_ODB_NUMBER_URL` (см. комментарий: сверить с актуальной документацией Opendatabot)
- [x] Парсинг ответа: vin, plate, brand, model, year, color, fuel, engine_volume, stolen, restrictions, owners, odometer, raw
- [x] Ошибка HTTP → dict с `error`, не исключение, не 500
- [x] Фабрика `get_opendatabot_provider()` — возвращает `RealOpendatabotProvider` (с ключом или без)
- [x] `StubOpendatabotProvider` сохранён для совместимости с legacy `/report/`

### Эндпоинт
- [x] GET /api/v1/vehicles/<vin>/registry/ → отчёт через RealOpendatabotProvider + кэш RegistryReport
- [x] `?plate=` — поиск по госномеру (vin в пути = `_`)
- [x] Кэш: повторный запрос по тому же VIN/номеру — из БД, без HTTP-запроса
- [x] OPENDATABOT_API_KEY в settings.py (env) + плейсхолдер в .env.example

### Тесты (20 новых, 97 всего)
- [x] Без ключа → demo=True, не падает (VIN и plate)
- [x] С ключом (замокан httpx): успешный VIN → парсинг всех полей
- [x] С ключом: plate-запрос → plate в ответе
- [x] HTTP-ошибка → dict с error, без исключения
- [x] VIN в запросе приводится к UPPER
- [x] Повторный запрос по VIN → провайдер вызван 1 раз (кэш)
- [x] Второй запрос → cached=True
- [x] Невалидный VIN (< 17 символов) → 400
- [x] `_` без ?plate= → 400
- [x] ?plate=AA1234BB → провайдер вызван с plate, vin=None
- [x] Сохранение в RegistryReport после первого запроса

---

## Промт 4 — Верификация дилеров (завершено 2026-06-20)

### Модель и сервис
- [x] `DealerApplication`: user/company_name/full_name/contact_phone/documents/status(pending|approved|rejected)/reviewed_by/review_notes/created_at/reviewed_at
- [x] `users/services.py`: `apply_for_dealer` (DuplicatePendingError на pending), `approve_application` (is_verified_dealer=True+role=dealer+email), `reject_application` (review_notes+email)
- [x] Email-уведомление: `EMAIL_BACKEND=console` в dev, env-переопределяемо; пометка «позже Telegram (промт 11)»

### API
- [x] POST /api/v1/dealers/apply/ — создаёт pending; 409 при наличии pending
- [x] GET /api/v1/dealers/application/ — статус собственной заявки (404 если нет)
- [x] `dealer_urlpatterns` в `users/urls.py`, подключены в `core/urls.py` под `/api/v1/dealers/`

### Админка
- [x] `DealerApplicationAdmin`: list_filter по status, actions «Одобрить» / «Отклонить»
- [x] При одобрении: `approve_application` → is_verified_dealer=True, role=dealer, email
- [x] При отклонении: `reject_application` → review_notes сохраняются

### B2B гейтинг
- [x] `IsVerifiedDealerOrAdmin` (listings/permissions.py) — DRF permission, перепроверен
- [x] /api/v1/b2b/board/ → 403 для неверифицированных, 401 для неавторизованных
- [x] `ListingListView`: verified dealers видят wholesale + retail; остальные только retail

### Frontend
- [x] `/dealers/apply` — форма заявки (company_name, full_name, contact_phone, documents)
- [x] `api/dealers.ts` — API клиент (apply, getApplication)
- [x] `lib/types.ts` — тип `DealerApplication`
- [x] B2B-страница: CTA «Подати заявку на B2B» → /dealers/apply для неверифицированных
- [x] Header: меню «B2B» для дилеров/admin; «B2B-доступ» (CTA) для авторизованных без верификации

### Тесты (19 новых)
- [x] Сервис: create pending, DuplicatePendingError, allow after rejection, approve→is_verified_dealer, reviewed_by/at, reject saves notes
- [x] API: 201 apply, 409 duplicate, 401 unauth, 400 missing fields, 404 no application, 200 status
- [x] B2B гейтинг: 401 unauth, 403 regular user, 200 verified dealer, 200 admin
- [x] Wholesale фильтр: anon/buyer не видит wholesale, dealer видит; 77 тестов OK

### Следующий шаг (промт 6)
Импорт лотов с аукционов, наполнение каталога «в пути»

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

---

## Bug: UnicodeDecodeError при подключении к БД (2026-07-07) — ДИАГНОСТИКА ЗАВЕРШЕНА

### Причина (двойная)

1. **.env — UTF-8 BOM + битые комментарии на кириллице**
   Файл начинался с BOM `\xef\xbb\xbf` и содержал Cyrillic-комментарии в двойной/некорректной кодировке.
   `load_dotenv(..., encoding='utf-8')` падал, не дойдя до KEY=VALUE строк.
   **ИСПРАВЛЕНО**: файл перезаписан как чистый UTF-8 без BOM, все комментарии — латиница/English.

2. **Windows PostgreSQL 16.14 — Russian locale (CP1251 error messages)**
   После чистки .env выяснилось, что реальная ошибка — **password authentication failed for user "autoforyou"**,
   но Windows Postgres отдаёт сообщение об ошибке в кодировке CP1251 (Russian locale, `lc_messages`).
   psycopg2 пытается декодировать его как UTF-8, падает на байте `0xc2` в позиции 83 — это
   первый байт кириллицы "В" (из слова "ВАЖНО") в CP1251, за которым идёт `0xc0` (не валидный
   UTF-8 continuation byte).
   Настоящая ошибка сервера (декодирована вручную): `FATAL: пользователь "autoforyou" не прошёл проверку подлинности (по паролю)`.

### Статус подключения

**DB НЕ OK** — auth failure. psycopg2 не может подключиться.

### Что нужно сделать владельцу в pgAdmin

**Шаг A — Проверить пользователя и пароль:**
1. pgAdmin → Login/Group Roles → найти `autoforyou`
2. Properties → Definition → Password: убедиться, что пароль = `autopass123`
   Если не совпадает — изменить или обновить `POSTGRES_PASSWORD` + `DATABASE_URL` в `.env`
3. Если пользователя нет — создать: `CREATE USER autoforyou WITH PASSWORD 'autopass123';`

**Шаг B — Проверить базу данных:**
1. Databases → найти `db_autoforyou`
2. Если нет — создать: `CREATE DATABASE db_autoforyou OWNER autoforyou ENCODING 'UTF8';`
3. Если есть — убедиться, что owner = `autoforyou` или у него CONNECT privilege

**Шаг C (опционально, устранить CP1251 навсегда):**
В `postgresql.conf` добавить/изменить:
```
lc_messages = 'en_US.UTF-8'
```
Или если нет en_US.UTF-8 locale: `lc_messages = 'C'`
Затем перезапустить PostgreSQL сервис на Windows.

**Шаг D — После исправления перезапустить backend:**
```
docker compose up -d --force-recreate backend
docker compose exec backend python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print('DB OK')"
```

---

## Перенос БД на Windows-Postgres — ЗАВЕРШЕНО (2026-07-07)

### Финальные параметры подключения к БД

| Параметр     | Значение                            |
|--------------|-------------------------------------|
| Host         | host.docker.internal (из Docker)    |
| Host (DBeaver/pgAdmin) | localhost                  |
| Port         | 5432                                |
| Database     | **autoforyou**                      |
| User         | **postgres**                        |
| Password     | autopass123                         |
| Engine       | PostgreSQL 18 (Windows)             |

### Что было путаницей

- `.env` ссылался на `db_autoforyou` — такой базы НЕ существует
- Пользователь `autoforyou` — НЕ существует в Windows-Postgres
- Реальная база с 56 таблицами: **autoforyou**, доступная через суперпользователя `postgres`
- Passwords хранились верно (`autopass123`), но у несуществующего пользователя

### Что сделано

1. Диагностика: перебор комбинаций user/db — найдена база `autoforyou` (56 таблиц), user=postgres
2. `.env` обновлён: `DATABASE_URL=postgresql://postgres:autopass123@host.docker.internal:5432/autoforyou`
3. `seed_regions` — засіяно 25 областей + 310 міст
4. `docker compose up -d` — весь стек запущен, все контейнеры Up

### Статус

- **DB OK** — подключение работает
- Миграций не применяли (0 unapplied) — все 56 таблиц уже были в базе
- listings: 0 (данных пользователей нет, БД чистая)
- regions: 25 (засіяно seed_regions)
- http://localhost → 200 OK
- http://localhost/api/v1/listings/ → 200 OK

### Креды для DBeaver / pgAdmin

```
Host:     localhost
Port:     5432
Database: autoforyou
User:     postgres
Password: autopass123
```

---

## QA — Полное тестирование (2026-07-07) — ЗАВЕРШЕНО

### Итог: 22 PASS, 2 FAIL → исправлено → **299 тестов зелёные**

| Блок | Статус |
|------|--------|
| Инфраструктура (Docker, DB, nginx) | PASS |
| Автотесты backend (299 тестов) | PASS (было 17 ошибок → исправлено) |
| Frontend build (0 TS-ошибок, 29 страниц) | PASS |
| Auth (регистрация/логин/refresh/logout/бан) | PASS |
| Калькулятор (is_estimate, breakdown) | PASS |
| Listings create/search (сигнал не крашит) | PASS |
| Messenger, Favorites, B2B gating | PASS |
| Local listings, регионы | PASS |
| Все 23 фронт-роута → 200 | PASS |
| Безопасность (SECRET_KEY не в git, JWT, throttle) | PASS |
| Media файлы (volume nginx) | PASS |
| Telegram binding /me/telegram | PASS |

### Критические баги — исправлено

**БАГ 1 — Listing creation → 500** (`telegram_bot/tasks.py`)
Сигнал `post_listing_to_channel` не перехватывал `TelegramBadRequest` при `SITE_URL=http://localhost`.
Исправление: добавлен `except Exception` с `logger.warning` вместо краша. Теперь ошибка
Telegram логируется, листинг создаётся успешно.

**БАГ 2 — Калькулятор → "Відсутні активні тарифи"** (`docker/entrypoint.sh`)
Тарифы не сидировались при fresh deploy.
Исправление: `entrypoint.sh` теперь вызывает `seed_regions`, `seed_rates`, `seed_auction_fees`
автоматически при каждом старте (команды идемпотентны).

### Не тестируется без ключей/публичного URL
- LiqPay webhook (нужен публичный HTTPS-адрес)
- VIN decode (нужен `APIFY_TOKEN`)
- Реальный автопост в Telegram (нужен `SITE_URL` с валидным HTTPS)
- Email-верификация (нужен SMTP)
