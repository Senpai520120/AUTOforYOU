# Аудит: 13 — Тесты

Ветка `finish-site` @ `d4cbfab`, 2026-09-25. Тесты **не запускались** (их прогоняет основной агент). Всё ниже получено чтением кода.

## Состав

### Django-тесты (433 теста, число посчитано по `def test_`)

| Файл | Строк | Тестов | Классов |
|---|---:|---:|---:|
| `local_listings/tests.py` | 1092 | 87 | 22 |
| `pricing/tests.py` | 917 | 64 | 22 |
| `integrations/tests.py` | 590 | 46 | 12 |
| `telegram_bot/tests.py` | 515 | 41 | 13 |
| `users/tests.py` | 397 | 38 | 9 |
| `tests/test_e2e.py` | 572 | 38 | 6 |
| `deals/tests.py` | 321 | 31 | 6 |
| `tests/test_favorites_notifications_saved_searches.py` | 303 | 28 | 6 (+ `SetupMixin`) |
| `messaging/tests.py` | 213 | 23 | 7 (+ `SetupMixin`) |
| `listings/tests.py` | 166 | 12 | 3 |
| `shipments/tests.py` | 99 | 10 | 1 |
| `payments/tests.py` | 66 | 8 | 1 |
| `reports/tests.py` | 106 | 7 | 1 |
| `cars/tests.py` | 2 | 0 | — пустая заглушка «Create your tests here» |
| `vehicles/tests.py` | 2 | 0 | — пустая заглушка |
| `tests/__init__.py` | 0 | — | — |

В приложениях `favorites`, `notifications`, `saved_searches` и `core` своего `tests.py` нет. Их покрывает `tests/test_favorites_notifications_saved_searches.py`.

В `.claude/worktrees/agent-a0e9aa80/` лежит старая копия репозитория со своими `tests.py` и `frontend/e2e/`. Каталог в `.gitignore:44`, у `.claude` нет `__init__.py`, поэтому `manage.py test` его, скорее всего, не подхватывает (не проверено прогоном). Но это источник путаницы при grep.

### Playwright (33 теста в 6 файлах)

| Файл | Строк | Тестов |
|---|---:|---:|
| `frontend/e2e/catalog.spec.ts` | 92 | 5 |
| `frontend/e2e/home.spec.ts` | 69 | 5 |
| `frontend/e2e/negative.spec.ts` | 144 | 9 |
| `frontend/e2e/register.spec.ts` | 74 | 5 |
| `frontend/e2e/ssr.spec.ts` | 55 | 4 |
| `frontend/e2e/test-1.spec.ts` | 59 | 5 (имя файла оставлено по решению владельца) |
| `frontend/playwright.config.ts` | 46 | — один проект `chromium` (Desktop Chrome), `workers: 1`, без `globalSetup`, `storageState` и `webServer` |

### Документы

- `docs/BACKEND_TESTS.md`, 171 строка.
- `docs/TEST_CASES.md`, 235 строк.
- CI: `.github/workflows/ci-cd.yml:58` запускает `manage.py test` на PostgreSQL. `:106-163` поднимает стек через `docker compose up` и запускает `npx playwright test` из `frontend/`.

## Функции (покрытие тестами)

### Django: модуль → покрытие

| Модуль | Тестов | Что покрыто | Что не покрыто |
|---|---:|---|---|
| `users` | 38 | Сервис заявки дилера и API: 201/409/401/400, статус заявки. B2B-доска для аноним/юзер/дилер/админ. Wholesale в каталоге. JWT logout и blacklist. Согласие при регистрации. Эскалация через `role`/`is_staff` (`users/tests.py:280-359`). Согласие на обработку ПД (`:364-397`) | `me/calculations`, `me/shipments`, `me/trusted-shops` (+`<pk>`): нет ни одного теста. `dealers/application/`: нет теста анонима и изоляции от чужого. Не проверяются смена пароля, сброс, лимит попыток входа, удаление аккаунта, выгрузка данных: этих функций нет |
| `local_listings` | 87 | Подача → pending, модерация и ремодерация, лимит активных объявлений, права владельца PATCH/DELETE (403), «мои объявления», фильтры, VIN-prefill (NHTSA замокан), регионы, загрузка/удаление/primary фото (401/403, тип, лимит 15), срок действия и Celery-задачи, продвижение и колбэк LiqPay, сортировка TOP, контакт (401, pending → 404), антиспам, бан, видимость по статусам, N+1 | Лимит размера фото (`local_listings/views.py:280-295`) без теста. Нет подмены содержимого (не-картинка с `image/jpeg`) и нет EXIF. `images/<img_id>` от чужого листинга не проверен. Нет анонима на PATCH/DELETE/promote. Троттлинг `contact` не проверен. Фальшиво-зелёный `test_phone_not_in_list_response` (13-Q5) |
| `pricing` | 64 | Коэффициент возраста, акциз бензин/дизель/EV/PHEV, пошлина, НДС, итог, только `Decimal`, аукционные сборы на stub-тирах, границы IAAI по seed (`:570-607`), дефолты сериализатора, сквозной расчёт на seed (через внутренние функции), инвалидация кэша, задача НБУ с моком `urlopen` | «Границы тиров» в `TestAuctionFeeBoundary` на деле не проверяются (13-Q6). Пенсионный сбор по брекетам не проверяется отдельно. Не проверено, что `Calculation` хранит снимок входов/ставок (CLAUDE.md п.3). Не проверено, что при пустых тарифах отдаётся честное «не настроено». Эндпоинт `pricing/rates/` без тестов |
| `integrations` | 46 | Opendatabot без ключа → demo, с ключом → мок `httpx.get`, кэш RegistryReport, импорт лотов (Manual/Apify без токена, сервис, API 401/403/400), троттлинг (мок `allow_request`), идемпотентность `import_lot_task`, VIN-отчёт 401 | Разбор ответа `VinDecodeView`/NHTSA не проверен: есть только 429. Apify с токеном не проверен. Два теста без мока внешнего API (13-S9). Реальные лимиты троттлинга не проверены (13-Q11) |
| `telegram_bot` | 41 | Модель токена привязки, `link-token` 401/200, рантайм бота через настоящий webhook+Dispatcher (`Bot.__call__` замокан), `/start`, `/help`, `/latest`, deep-link привязки (повтор, просрочка, мусор), middleware, `run_bot`, `send_notification`, `post_listing_to_channel`, сигнал автопоста, секрет webhook, пустой токен в тестах | `DELETE /api/v1/telegram/link/` (отвязка) без тестов. Нет уведомления брокеру о заявке: функции нет. Нет отправки в канал с успешным исходом (замоканным) |
| `tests/test_e2e.py` | 38 | Цепочка регистрация → JWT → профиль. Калькулятор через API на seed (`:150-257`). LiqPay: checkout, валидный/невалидный колбэк, идемпотентность. B2B-гейтинг. Поток дилера. Троттлинг registry | Сумма чекаута приходит от клиента, и тесты считают это нормой (13-S6). `test_rates_date_in_response` проверяет `warning` (13-Q9). `test_within_limit_responds_normally` работает без мока провайдера (13-S9) |
| `deals` | 31 | Сервис: propose/confirm/cancel/review, рейтинг и бейдж. API: список (401), propose, confirm, cancel, review, публичный рейтинг | **`listing-buyers/<id>/` отдаёт email покупателей и не имеет ни одного теста** (13-S1). Посторонний на confirm/cancel/review через API не проверен (есть только на уровне сервиса). `assertRaises(msg=)` не сверяет текст ошибки (13-Q7) |
| `tests/test_favorites…` | 28 | Уведомления: сервис, API (401, изоляция), mark-read, уведомления из модерации и сообщений. Избранное: 401, изоляция, дубль, статус. Сохранённые поиски: 401, изоляция, удаление чужого (404), задача | `mark-read` с чужим `id`, `unread-count` 401, `favorites/status` 401, GET/PATCH чужого saved-search — без тестов. Тест «не дублирует» зелёный и при нуле уведомлений (13-Q8) |
| `messaging` | 23 | Сервис переписки, непрочитанные, API: start (401/201/200/400), список (401, изоляция), деталь (403 чужому на GET и POST), mark read, unread-count 401 | Аноним на `conversations/<pk>/` не проверен. Переписка по импортным листингам (`listing_type='import'`) не проверена. Троттлинг `messages` не проверен |
| `listings` | 12 | Wholesale-деталь → 404, N+1 каталога, CHECK-ограничения статуса/канала/валюты | `listings/create/`: кто может создать импортный листинг, не проверено (13-S12) |
| `shipments` | 10 | 401 аноним, посторонний → пустой список / 404, VIN не утекает через shipments, watcher и staff | VIN утекает через `/api/v1/vehicles/`: этот путь не покрыт (13-S5) |
| `payments` | 8 | Валидация checkout: сумма (нечисловая, 0, отрицательная), валюта, purpose, несуществующий листинг | Нет теста «сервер сам считает сумму» (issue #24). Нет теста на чужой листинг/purpose. Колбэк проверяется только в `local_listings` и `tests/test_e2e.py` |
| `reports` | 7 | Жалоба на листинг/пользователя, 401, дубль, без цели, обе цели, на себя | Админ-действия `hide_listing`/`ban_reported_user` (признано в `BACKEND_TESTS.md:169`) |
| `vehicles` | 0 | — | `VehicleListView`/`VehicleDetailView` (AllowAny, отдают VIN) — `vehicles/views.py:11-23` |
| `cars` (legacy) | 0 | — | Известно: legacy, `/api/calculate/` на хардкод-ставках. Тестов нет |
| `favorites`/`notifications`/`saved_searches`/`core` | — | через `tests/` | нет собственных `tests.py` |

### Playwright: spec → сценарии → может ли реально упасть

| Spec-файл | Тестов | Сценарии | Может ли реально упасть |
|---|---:|---|---|
| `catalog.spec.ts` | 5 | `/listings` 200 + h1. Демо-баннера нет на каталоге. Форма калькулятора с подписанными полями + баннер. Расчёт даёт полную разбивку и итог. 404 на неизвестный маршрут | **Да**, все 5. Проверка отсутствия баннера (`:28`) мгновенная, но баннер SSR, так что допустимо. Расчёт зависит от seed-тарифов стека (`docker/entrypoint.sh:20-22`), это данные, а не сеть |
| `home.spec.ts` | 5 | Hero → `/calculator`. «Два напрямки» → `/listings` и `/ua`. 4 шага. Блок стоимости → калькулятор. Футер | **Да**. Проверки видимых текстов и `href`, переходы реальные |
| `negative.spec.ts` | 9 | Регистрация: невалидный email, разные пароли, повторный email, простой пароль. Калькулятор: отрицательная цена, буквы, объём > max, год < 1990, пустая форма | **Частично.** «Разные пароли» падает честно. «Повторный email» и «простой пароль» проверяют только `.text-red-600` (13-Q4). Четыре теста калькулятора падают только при снятии `min`/`max`/`type`: отсутствие результата проверяется мгновенно, отправку при `noValidate` они не заметят (13-Q3). **«Пустая форма» (`:136-143`) фальшиво-зелёный** (13-Q2) |
| `register.spec.ts` | 5 | Поля и чекбокс. Без согласия не отправляется. Ссылки на `/terms` и `/privacy` (новая вкладка). Футер с 4 юр. ссылками | **4 из 5 да.** **«Без згоди» (`:22-34`) фальшиво-зелёный**: `toHaveURL(/register/)` выполняется мгновенно, `not.toBeChecked` тривиален, email фиксированный (13-Q1) |
| `ssr.spec.ts` | 4 | `/ua` и `/listings` без JS (нет скелетона), главная без JS, sitemap | **Да.** Sitemap проверяется подстрокой `'/ua'` (`:51`), это слабо (13-Q16) |
| `test-1.spec.ts` | 5 | Лого → `/`. Три ссылки навигации. Гостю видны вход и регистрация. Гостю не видны кабинетные ссылки. Переход в `/ua` | **Да**. «Не показаны разделы кабинета» — проверка отсутствия, но в паре с «показаны вход/регистрация» осмысленна |

Нет ни одного авторизованного e2e-сценария: `globalSetup`/`storageState` отсутствуют (`playwright.config.ts:10-46`). Мобильного проекта нет (`playwright.config.ts:40-45`). Нет `webServer`: стек поднимается вручную. Playwright нужно запускать из `frontend/`: в корне нет ни `package.json`, ни конфига. Ловушка описана в `TEST_CASES.md:24-31` и в шапке `catalog.spec.ts:4-6`.

### 401/403 на эндпоинтах с личными данными (бриф, раздел 3)

Список собран по `core/urls.py:12-38` и `*/urls.py`. «✓» означает, что тест есть.

| # | Эндпоинт | Личные данные | 401 аноним | 403/404 чужой |
|---|---|---|---|---|
| 1 | `GET/PATCH /api/v1/auth/profile/` | email, телефон, роль | ✓ `tests/test_e2e.py:134` | н/п (свой объект). Смена `role`/`is_staff`: ✓ `users/tests.py:310,352` |
| 2 | `GET /api/v1/auth/me/calculations/` | расчёты пользователя | **нет** | **нет** |
| 3 | `GET /api/v1/auth/me/shipments/` | контейнеры, VIN | **нет** | **нет** |
| 4 | `GET/POST /api/v1/auth/me/trusted-shops/` | список магазинов | **нет** | **нет** |
| 5 | `GET/PATCH/DELETE /api/v1/auth/me/trusted-shops/<pk>/` | запись владельца | **нет** | **нет** (IDOR не проверен) |
| 6 | `POST /api/v1/dealers/apply/` | компания, ФИО, телефон | ✓ `users/tests.py:100` | н/п |
| 7 | `GET /api/v1/dealers/application/` | заявка дилера | **нет** | **нет** |
| 8 | `GET/PATCH/DELETE /api/v1/local/listings/<pk>/` | неактивное объявление, причина отказа | create ✓ `local_listings/tests.py:102`. PATCH/DELETE аноним — **нет** | ✓ `:285,293,160,990` |
| 9 | `GET /api/v1/local/listings/<pk>/contact/` | телефон продавца | ✓ `:856` | pending → 404 ✓ `:1008` |
| 10 | `POST /api/v1/local/listings/<pk>/images/` | — (запись) | ✓ `:502` | ✓ `:497` |
| 11 | `DELETE/PATCH …/images/<img_id>/` | — | **нет** | ✓ `:556,583`. Фото чужого листинга по своему `pk` — **нет** |
| 12 | `POST /api/v1/local/listings/<pk>/promote/` | платёж | **нет** | ✓ `:701` |
| 13 | `GET /api/v1/local/my-listings/` | все свои объявления | ✓ `:332` | ✓ `:336` |
| 14 | `POST /api/v1/messages/start/` | — | ✓ `messaging/tests.py:102` | н/п |
| 15 | `GET /api/v1/messages/conversations/` | переписка | ✓ `:142` | ✓ `:135` |
| 16 | `GET/POST /api/v1/messages/conversations/<pk>/` | сообщения | **нет** | ✓ `:164,187` |
| 17 | `GET /api/v1/messages/unread-count/` | — | ✓ `:211` | н/п |
| 18 | `GET/POST /api/v1/deals/` | сделки | ✓ `deals/tests.py:256` | посторонний не видит чужие — **нет** |
| 19 | `POST /api/v1/deals/<pk>/confirm\|cancel\|review/` | сделка | **нет** | только сервис (`deals/tests.py:114,141,170`). API — **нет** |
| 20 | `GET /api/v1/deals/listing-buyers/<listing_id>/` | **email, имя, фамилия покупателей** (`deals/views.py:101-106`) | **нет** | **нет** |
| 21 | `GET/POST/DELETE /api/v1/favorites/` | избранное | ✓ `tests/test_favorites…py:144` | ✓ `:174` |
| 22 | `GET /api/v1/favorites/status/` | — | **нет** | н/п |
| 23 | `GET /api/v1/notifications/` | уведомления | ✓ `:75` | ✓ `:86` |
| 24 | `POST /api/v1/notifications/mark-read/` | — | **нет** | чужой `id` — **нет** |
| 25 | `GET /api/v1/notifications/unread-count/` | — | **нет** | н/п |
| 26 | `GET/POST /api/v1/saved-searches/` | фильтры поиска | ✓ `:203` | ✓ `:223` |
| 27 | `GET/PATCH/DELETE /api/v1/saved-searches/<pk>/` | — | **нет** | DELETE ✓ `:236`. GET/PATCH — **нет** |
| 28 | `POST /api/v1/payments/liqpay/checkout/` | платёж | ✓ `tests/test_e2e.py:314` | н/п |
| 29 | `GET /api/v1/shipments/`, `/<pk>/` | VIN, контейнер | ✓ `shipments/tests.py:210,213` | ✓ `:218,224,243` |
| 30 | `POST /api/v1/reports/` | — | ✓ `reports/tests.py:68` | н/п |
| 31 | `GET /api/v1/telegram/link-token/` | токен привязки | ✓ `telegram_bot/tests.py:55` | н/п |
| 32 | `DELETE /api/v1/telegram/link/` | `telegram_id` | **нет** | н/п |
| 33 | `GET /api/v1/vehicles/<vin>/report/`, `/registry/` | платные API | ✓ `integrations/tests.py:579,478` | н/п |
| 34 | `GET /api/v1/b2b/board/`, `/listings/<pk>/` (wholesale) | опт | ✓ | ✓ |
| 35 | `POST /api/v1/listings/create/` | — | **нет** | ограничение по роли не проверено |
| 36 | `GET /api/v1/vehicles/`, `/<pk>/` | VIN всех авто, AllowAny | **нет** | **нет** (13-S5) |

Итог: из 36 строк полностью закрыты (401 и изоляция, где применимо) 15. Не закрыто ни одним тестом 9: №2, 3, 4, 5, 7, 20, 32, 35, 36. Требование брифа «на каждый эндпоинт с личными данными» **не выполнено**.

## Сверка с BRIEF.md

| Пункт брифа | Статус | Комментарий |
|---|---|---|
| §3 «на каждый эндпоинт с личными данными — тест на 401/403 для чужого» | **противоречит** | См. таблицу выше: 9 эндпоинтов без тестов, среди них `listing-buyers` с email покупателей |
| §3 cookie httpOnly + CSRF, email-подтверждение, капча, сброс/смена пароля, отзыв сессий, лимит попыток входа, удаление/выгрузка аккаунта, EXIF, роль broker | **не хватает** | Ни одного теста. Большинства функций нет в коде (подробно в пакете 01). grep `exif`, `password_reset`, `axes`/`ratelimit` в `.py` ничего не находит |
| §3 «нет утечек через списки, сериализаторы» | частично | Телефон в списке/детали и VIN в shipments проверены. `vehicles/` и `listing-buyers` — нет |
| §5 п.1 «`manage.py test` зелёный» | не проверено здесь | Прогон делает основной агент |
| §5 п.3 «Playwright: успех + ошибка/обход на каждую функцию» | **противоречит** | E2E покрывает только публичные страницы, регистрацию и калькулятор. Для C2C-подачи, сообщений, избранного, сделок, кабинета, B2B, заявки дилера, VIN-отчёта, привязки Telegram, оплаты нет ни одного сценария. Нет ни одного сценария обхода (гость на `/cabinet`, чужое объявление) |
| §5 п.3 «для функций без UI — Django-тесты с моками внешних API» | частично | Замоканы НБУ, Opendatabot, NHTSA-prefill, Telegram, `.delay` автопоста. **Не замоканы** VIN-отчёт и registry «в пределах лимита» (13-S9). SMTP не проверяется. carVertical и источник лотов (Apify) с ключом не проверены (реального адаптера carVertical нет, `integrations/providers.py:244-245` всегда отдаёт Stub) |
| §1 главный сценарий «расчёт → заявка брокеру → Telegram + админка» | **не хватает** | Модели заявки (Lead) нет (grep по `models.py`). Нет ни Django-, ни e2e-теста |
| §2 «честный статус "не настроено"» | частично | Проверяется demo без ключа (Opendatabot, Apify, Telegram 503). Калькулятор без тарифов не проверяется |
| §2 «тестовые данные помечены» | совпадает | `is_estimate` проверяется (`pricing/tests.py:276,746`, `tests/test_e2e.py:216`). Демо-баннер — e2e `catalog.spec.ts:50` |
| §4 этап 0 «базовые Playwright-тесты, стабильная тестовая среда» | частично | Базовые есть, CI гоняет их на docker-стеке. Но нет авторизованных, мобильных и изолированных от данных стека тестов (регистрации копятся в БД) |
| §4 этап 6 «мобильная версия» | **не хватает** | В `playwright.config.ts:40-45` только Desktop Chrome |

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 13-S1 | критично | `GET /deals/listing-buyers/<id>/` отдаёт email/ФИО покупателей, и нет ни одного теста (ни 401, ни 403 чужому, ни staff) | `deals/views.py:91-107`, `deals/urls.py:18`, `deals/tests.py` | Добавить тесты: аноним → 401, посторонний → 403, владелец → свои покупатели, staff → 200 |
| 13-S2 | важно | `me/calculations`, `me/shipments`, `me/trusted-shops`, `me/trusted-shops/<pk>`, `dealers/application` без тестов 401 и изоляции | `users/urls.py:32-35,40`, `users/views.py:63-111,147-151` | Тест на каждый: аноним → 401, чужой объект → 404/пустой список |
| 13-S3 | важно | confirm/cancel/review сделки посторонним через API не проверены (только сервис). Список `/deals/` чужого не проверен | `deals/tests.py:236-321` | API-тесты: outsider → 403/404, чужие сделки не видны в списке |
| 13-S4 | важно | `notifications/mark-read` с чужим `id`, GET/PATCH чужого saved-search, `DELETE telegram/link/`, `favorites/status` и `unread-count` без 401 | `tests/test_favorites…py:99-112,236-240`; `telegram_bot/views.py:47-60` | Тесты на чужой id (статус чужого уведомления не меняется), 401 для каждого |
| 13-S5 | важно | `/api/v1/vehicles/` (AllowAny) отдаёт VIN всех авто, включая оптовые и те, что в контейнерах. Тест утечки VIN есть только для shipments, `vehicles/tests.py` пуст. Сама проблема — в пакет 04 | `vehicles/views.py:11-23`, `core/settings.py:223-224`, `vehicles/tests.py:1-2` | Тест: аноним/покупатель не получают VIN wholesale/shipment-авто |
| 13-S6 | важно | Тесты закрепляют поведение issue #24: сумма checkout от клиента считается корректной. Теста «сервер игнорирует `amount` клиента» нет | `payments/tests.py:30-35`, `tests/test_e2e.py:291-298` | После исправления #24 — тест: клиентская сумма игнорируется, берётся серверная цена |
| 13-S7 | важно | Нет ни одного теста на требования §3: cookie/CSRF, подтверждение email, капча, сброс/смена пароля, отзыв сессий, блокировка перебора, удаление/выгрузка аккаунта, EXIF, роль broker. Функции в основном отсутствуют (пакет 01) | — | Писать тесты вместе с функциями этапа 1 |
| 13-S8 | важно | Загрузка фото: нет тестов лимита размера, подмены содержимого (текст с `image/jpeg`), удаления EXIF, безопасного имени файла. Тип проверяется только GIF по content-type | `local_listings/views.py:280-295`, `local_listings/tests.py:506-510` | Тесты: >N МБ → 400, не-изображение → 400, EXIF GPS отсутствует после загрузки |
| 13-S9 | важно | Тесты без мока платного внешнего API: `VinReportAccessTest.test_authenticated_allowed` (реальный `get_opendatabot_provider`), `test_within_limit_responds_normally` (registry), `test_apify_no_token_returns_demo_true` (зависит от отсутствия `APIFY_TOKEN`). `.env` подгружается в тестах (`core/settings.py:14`), обнуляется только Telegram (`:406-407`). Если в локальном `.env` есть ключ, будут реальные платные запросы. Наличие ключей в `.env` не проверено: чтение `.env` заблокировано | `integrations/tests.py:582-585,452-462`; `tests/test_e2e.py:555-567` | Мокать провайдеры в этих тестах или обнулять `OPENDATABOT_API_KEY`/`APIFY_TOKEN`/`LIQPAY_*` при `_testing`, как Telegram |
| 13-S10 | желательно | E2E регистрирует реальных пользователей в БД стека и не чистит их. С `E2E_BASE_URL` на проде это мусорные аккаунты в боевой БД | `frontend/e2e/negative.spec.ts:16,49-61`, `playwright.config.ts:21` | Отдельная тестовая БД/стек или очистка через API в `globalTeardown`. Запрет запуска на прод-URL |
| 13-S11 | желательно | Админ-действия `hide_listing`, `ban_reported_user` через админку не тестируются (признано) | `docs/BACKEND_TESTS.md:169` | Тесты через `Client` с логином админа |
| 13-S12 | желательно | `POST /listings/create/` (импортный листинг): право создания не проверено, достаточно `IsAuthenticated` | `listings/views.py:84-86` | Тест: обычный buyer → 403 (если так задумано) |

## Готовность к конфигурации

| ID | Что захардкожено / зависит от окружения | Файл:строка | Куда вынести |
|---|---|---|---|
| 13-C1 | Тесты наследуют `.env` (`load_dotenv`, `override=False`). Кроме Telegram, ключи внешних API не обнуляются, и результат тестов зависит от локального `.env` | `core/settings.py:14,302,328,331,406-407` | Под `_testing` обнулять все ключи провайдеров. Отдельный `settings_test` |
| 13-C2 | При `REDIS_URL` и `DEBUG=false` (например, `docker compose exec backend python manage.py test`) кэш — живой Redis, и `cache.clear()` в тестах сотрёт боевой кэш. Celery перестаёт быть eager, и `.delay` уйдёт в брокер | `core/settings.py:145-156,358-365`; `cache.clear()`: `pricing/tests.py:768,856`, `integrations/tests.py:137,476,499`, `tests/test_e2e.py:536` | В тестах принудительно `LocMemCache`/`DummyCache` и `CELERY_TASK_ALWAYS_EAGER=True` |
| 13-C3 | Числа тестов привязаны к placeholder-значениям seed: us_land $500, eu_to_ua $350, сборы Copart. Правка seed владельцем сломает тесты. Это нормально, но нигде не описано | `pricing/tests.py:711-758`, `tests/test_e2e.py:222-239`, `pricing/management/commands/seed_auction_fees.py:15` | Отметить в `LAUNCH_CHECKLIST.md`/`BACKEND_TESTS.md`, что тесты используют собственный seed, а не данные админки |
| 13-C4 | E2E зависят от данных стека: seed тарифов для расчёта (`catalog.spec.ts:53-83`), лоты для «Свежих авто» не проверяются. Нет фикстур — тесты работают только на «чистом» стеке с seed | `docker/entrypoint.sh:20-22`, `frontend/e2e/home.spec.ts:4-7` | Фикстуры через API в `globalSetup` (с помеченными тестовыми данными) |
| 13-C5 | `baseURL` по умолчанию `http://localhost`, нет `webServer` | `frontend/playwright.config.ts:21` | Ок для CI. Добавить `webServer` или явную проверку готовности стека |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 13-Q1 | важно | **Фальшиво-зелёный e2e «без згоди форма не відправляється».** `toHaveURL(/register/)` выполняется мгновенно, до возможной навигации. `not.toBeChecked()` тривиален. Email фиксированный `e2e-consent@example.com`: если убрать `required`, упадёт только первый прогон, дальше email уже занят, форма остаётся на `/register`, и тест снова зелёный. Нужно проверять `validity.valueMissing` у чекбокса и отсутствие запроса к `/auth/register/` | `frontend/e2e/register.spec.ts:22-34` |
| 13-Q2 | важно | **Фальшиво-зелёный e2e «порожня форма».** Проверяется только следствие `toHaveCount(0)` сразу после клика, а результат приходит асинхронно, так что проверка проходит мгновенно. Противоречит собственному правилу файла (`negative.spec.ts:4-7`) и `TEST_CASES.md:205-212` | `frontend/e2e/negative.spec.ts:136-143` |
| 13-Q3 | желательно | Остальные негативные тесты калькулятора: «результата нет» проверяется мгновенно, а `validity.*` доказывает наличие атрибута `min`/`max`, но не блокировку отправки. `noValidate` на форме они не поймают. Нужно следить за отсутствием запроса к `/pricing/calculate/` | `frontend/e2e/negative.spec.ts:91-134` |
| 13-Q4 | желательно | Ошибка сервера проверяется по CSS-классу `.text-red-600`, текст не сверяется | `frontend/e2e/negative.spec.ts:67,79` |
| 13-Q5 | важно | **Фальшиво-зелёный Django-тест.** `test_phone_not_in_list_response`: объявление в `pending`, список всегда пуст, `if results:` — проверка не выполняется никогда. В `TestContactEndpoint.test_phone_not_in_list` нет проверки, что список не пуст | `local_listings/tests.py:112-119,847-850` |
| 13-Q6 | важно | `TestAuctionFeeBoundary` заявлен как проверка границ тиров, но передаёт готовый stub-тир: bid на выбор не влияет, тест не может упасть из-за ошибки границы. `test_percent_fee_rounding` не проверяет ROUND_HALF_UP (8333×0.06 = 499.98 точно). Реальные границы проверяет только `TestIAAITierBoundaryDB` | `pricing/tests.py:523-543` |
| 13-Q7 | желательно | `assertRaises(ValueError, msg='…')`: `msg` — это текст при провале, текст исключения не сверяется. Тест зелёный при любой `ValueError` | `deals/tests.py:77,86,91` |
| 13-Q8 | желательно | «Повторный запуск не дублирует»: зелёный и при `count_first == 0`, то есть когда задача вообще не работает | `tests/test_favorites_notifications_saved_searches.py:269-287` |
| 13-Q9 | желательно | `test_rates_date_in_response` проверяет ключ `warning`, а не дату ставок | `tests/test_e2e.py:241-244` |
| 13-Q10 | желательно | Слишком широкие ассерты: `assertIn(status, (200, 201, 400))`, `assertNotEqual(…, 429)`, `assertIn(…, [400, 401])` | `integrations/tests.py:460`, `tests/test_e2e.py:563`, `local_listings/tests.py:941,954` |
| 13-Q11 | желательно | Троттлинг-тесты мокают `allow_request=False`, то есть проверяют только подключение класса. Реальный лимит `expensive` и лимиты `messages`/`contact` не проверяются, хотя заголовок обещает «>10 запросов → 429» | `integrations/tests.py:501-516`, `tests/test_e2e.py:529-553`, `core/settings.py:233-239` |
| 13-Q12 | желательно | Дублирование. B2B-гейтинг: `users/tests.py:129-153`, `tests/test_e2e.py:406-449`, `listings/tests.py:34-75`. Wholesale в каталоге: `users/tests.py:158-198` и `tests/test_e2e.py:451-458`. Согласие: `users/tests.py:252-261` и `tests/test_e2e.py:128-132`. 409 дилера: `users/tests.py:95-98` и `tests/test_e2e.py:516-525`. Registry 401/429: `integrations/tests.py:478-516` и `tests/test_e2e.py:540-572`. Хелперы `_make_user`/`_make_listing`/`_auth` скопированы в 9 файлов, общей `tests/factories.py` нет | см. строки |
| 13-Q13 | важно | Возможная зависимость от порядка. Кэш тарифов (LocMem) переживает откат транзакции `TestCase`, а `_lookup_tier` читает тиры из кэша (`pricing/views.py:53`). Классы, сидирующие тарифы в `setUpClass`, оставляют в кэше объекты удалённых строк. `cache.clear()` есть только в отдельных классах. Сейчас ни один тест не ожидает пустых тарифов, поэтому риск скрытый (не проверено прогоном) | `pricing/tests.py:576-579,645-649`, `tests/test_e2e.py:157-161` |
| 13-Q14 | желательно | Тесты зовут приватные `pricing.views._lookup_tier/_lookup_fixed_fees/_active_on`. Бизнес-логика живёт во views (CLAUDE.md п.1), тесты привязаны к приватным именам. Сквозной «расчёт» дублирует сборку снимка вручную, а не вызывает сервис | `pricing/tests.py:584,602,669-709` |
| 13-Q15 | желательно | `setUpClass` + `call_command` вместо `setUpTestData` | `pricing/tests.py:576-579,645-649`, `tests/test_e2e.py:157-161` |
| 13-Q16 | желательно | Sitemap проверяется подстрокой `'/ua'`, а не `<loc>…/ua</loc>` | `frontend/e2e/ssr.spec.ts:51-53` |
| 13-Q17 | желательно | Пустые `tests.py`-заглушки | `cars/tests.py:1-2`, `vehicles/tests.py:1-2` |
| 13-Q18 | важно | Нет авторизованных e2e (`globalSetup`/`storageState`), нет мобильного проекта, нет Firefox/WebKit | `frontend/playwright.config.ts:10-46` |
| 13-Q19 | желательно | Документация расходится с кодом. `TEST_CASES.md:5` — «394 шт.» и «Issue #7» (факт 433, разбор уже есть в `BACKEND_TESTS.md`). `BACKEND_TESTS.md:65`: `TestLandedCostE2ECopartBroker` — «сквозной расчёт через API», но на деле вызываются внутренние функции (`pricing/tests.py:651-709`), через API считает `tests/test_e2e.py:150`. `BACKEND_TESTS.md:62,118` — «границы тиров» для `TestAuctionFeeBoundary` (см. 13-Q6). `BACKEND_TESTS.md:120` — класса `TestTokenDisabledInTests` нет, есть `TelegramTokenDisabledInTestsTest` (`telegram_bot/tests.py:500`). `BACKEND_TESTS.md:15` — «переменных окружения не нужно», но `.env` подгружается (13-C1). `BACKEND_TESTS.md:75` — `TestAntispamListing` не про телефон в списке. `BACKEND_TESTS.md:102` — «после лимита 429» (см. 13-Q11). `tests/test_e2e.py:3` — «in-memory SQLite», а в CI PostgreSQL. `TEST_CASES.md:221` — «кабинет покрыт backend-тестами», но `me/*` не покрыты. Число тестов по приложениям (`BACKEND_TESTS.md:29-43`) и e2e (`TEST_CASES.md:50-65`) **совпадает** с фактом. Покрытие 83% (`:137`) и время 4,5 мин (`:23`) не проверены |

## Тесты

**Что есть.** 433 Django-теста в 13 файлах и 33 Playwright-теста в 6 файлах (раздел «Состав»). Сильные стороны:

- калькулятор: `Decimal`, акциз, НДС, EV/PHEV, seed-границы IAAI;
- права на локальные объявления и видимость по статусам;
- рантайм Telegram-бота через настоящий webhook;
- N+1 для двух каталогов;
- CHECK-ограничения;
- идемпотентность колбэка LiqPay и импорта.

**Нужные Django-тесты (приоритет).**
1. `deals/listing-buyers/<id>/`: 401, чужой → 403, владелец и staff → 200 (13-S1).
2. `auth/me/calculations|shipments|trusted-shops(<pk>)`, `dealers/application/`: 401 и изоляция (13-S2).
3. API сделок: посторонний на confirm/cancel/review → 403/404, `/deals/` не показывает чужие (13-S3).
4. `notifications/mark-read` с чужим id, `saved-searches/<pk>` GET/PATCH чужим, `DELETE telegram/link/`, 401 для `favorites/status` и `unread-count` (13-S4).
5. `vehicles/`: VIN wholesale/shipment-авто не отдаётся посторонним (13-S5).
6. Checkout: сервер игнорирует `amount` клиента (после issue #24) (13-S6).
7. Фото: размер, подмена содержимого, EXIF GPS удалён (13-S8).
8. Калькулятор: пустые тарифы → честное «не настроено», а не 500 и не фейковые цифры. `Calculation` хранит снимок входов и ставок.
9. Реальные лимиты троттлинга (`override_settings` с `'expensive': '2/min'` → третий запрос 429). Лимит попыток входа — после появления функции.
10. Все §3-функции этапа 1 по мере реализации: сброс пароля (одноразовая ссылка, срок), смена пароля с отзывом refresh, удаление и выгрузка аккаунта, cookie-JWT + CSRF.
11. Моки для VIN-отчёта и registry «в пределах лимита» (13-S9). Обнуление ключей провайдеров под тест-раннером (13-C1).
12. Исправить фальшиво-зелёные: 13-Q5, 13-Q6, 13-Q8.

**Нужные Playwright-сценарии.**
- `globalSetup`: логин через API и `storageState` для buyer, dealer и staff. Тестовые данные помечены и удаляются в `globalTeardown`.
- Кабинет: гость на `/cabinet` (и другие закрытые страницы) → редирект на `/login`; авторизованный видит свои объявления.
- C2C: подача объявления → pending → модерация через API админом → появление в `/ua`. Обход: чужое объявление нельзя редактировать (нет кнопки, прямой URL → ошибка).
- Сообщения: начать переписку, ответ, счётчик непрочитанных. Чужая переписка по URL → 403/404.
- Избранное и сохранённый поиск: добавить/удалить, пустые состояния.
- B2B: обычный пользователь → нет доступа, верифицированный дилер → доска.
- Заявка дилера: без согласия → ошибка, с согласием → pending.
- Калькулятор → заявка брокеру (после появления функции, бриф §1).
- Мобильный проект (например, `devices['Pixel 7']`) для главной, каталогов, калькулятора и шапки.
- Исправить 13-Q1 и 13-Q2: проверять отсутствие сетевого запроса, `validity.valueMissing` у чекбокса, уникальный email.

## Итог (≤15 строк)

- Готовность пакета «Тесты» — **около 55%**. Бэкенд покрыт широко (433 теста, числа в `BACKEND_TESTS.md` сходятся с фактом), e2e узкие: 33 теста, только публичные страницы, без авторизации и мобильного проекта.
- **13-S1 (критично):** `deals/listing-buyers/<id>/` отдаёт email/ФИО покупателей, тестов нет вообще.
- Требование брифа §3 «401/403 на каждый эндпоинт с личными данными» не выполнено. Из 36 эндпоинтов 9 без единого теста (`me/*`, `dealers/application`, `listing-buyers`, `telegram/link`, `listings/create`, `vehicles/`), ещё 12 закрыты частично (13-S2…S5).
- Тесты на §3 (cookie/CSRF, сброс пароля, лимит входа, удаление/выгрузка, EXIF) отсутствуют вместе с функциями (13-S7). Тесты закрепляют issue #24 (13-S6).
- Фальшиво-зелёные: e2e `register.spec.ts:22-34` и `negative.spec.ts:136-143` (13-Q1, Q2), Django `local_listings/tests.py:112-119` (13-Q5). Кроме того, `TestAuctionFeeBoundary` не проверяет границы (13-Q6).
- Сеть и окружение: три теста без мока платного API при ключе в `.env` (13-S9, 13-C1). `cache.clear()` при `REDIS_URL` сотрёт живой Redis (13-C2). Кэш тарифов переживает откат транзакции — скрытая зависимость от порядка (13-Q13).
- Моки внешних API есть для НБУ, Opendatabot, NHTSA-prefill и Telegram. Для SMTP, Apify с токеном, NHTSA decode — нет.
- Документы: `TEST_CASES.md:5` устарел (394 → 433). В `BACKEND_TESTS.md` четыре неточности (13-Q19).
- Ловушка «Playwright запускать из `frontend/`» задокументирована (`TEST_CASES.md:24-31`). Имя `test-1.spec.ts` оставлено по решению владельца.
