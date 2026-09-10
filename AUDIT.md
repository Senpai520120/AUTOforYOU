# AUDIT.md — аудит репозитория AUTOforYOU

**Дата:** 2026-09-03  •  **Ветка:** `main` @ `a47169c`  •  **Рабочее дерево:** чистое, код не изменялся
**Окружение проверки:** Python 3.12.10 (`.venv`), Node v24.14.1 / npm 11.11.0, Docker 29.5.3 / Compose v5.1.4

Все утверждения ниже — результат реального запуска команд. Где проверка не проводилась, это указано явно.

---

## ⚠ Актуальность

**Это снимок состояния на 2026-09-03, до начала работ.** Документ намеренно не переписывается: он фиксирует, с чего начинали, и по нему видно, что сделано.

Что закрыто с момента аудита:

| Находка в отчёте | Статус | Где |
|---|---|---|
| B-01 `DEBUG=true` в Docker, CORS открыт всем | Закрыто | PR #17 |
| B-02 Эскалация привилегий через `role` | Закрыто | PR #17 |
| B-03 Скрытые объявления читаются анонимом | Закрыто | PR #25 |
| B-04 LiqPay: сумма от клиента | Частично — добавлена валидация ввода; серверного прайса по-прежнему нет | PR #25, открыт Issue #24 |
| B-10 Celery в eager-режиме в Docker | Закрыто вместе с B-01 | PR #17 |
| B-11 CI не запускает тесты, `\|\| true` | Закрыто, добавлен джоб E2E против docker compose | PR #21 |
| B-13 Публичные `shipments` с VIN | Закрыто | PR #25 |
| Фальшиво-зелёные тесты, `label` не связан с полем | Закрыто | PR #15 |
| Каталоги не рендерятся на сервере | Закрыто | PR #28 |
| Пустая главная страница | Закрыто | PR #19 |
| Юридический блок: согласие, возврат, индексация | Закрыто | PR #12 |

Что остаётся открытым:

| Находка | Issue |
|---|---|
| B-05 Инвалидация кэша тарифов не работает между процессами без Redis | не заведено |
| B-06 README оставляет калькулятор нерабочим (нет `seed_auction_fees`) | не заведено |
| B-07 Тесты стучатся в боевой Telegram — в CI закрыто переменной, в коде нет | не заведено |
| B-08 `seed_rates` падает при недоступном Redis | не заведено |
| B-09 N+1 на каталоге: 23 запроса на 20 объявлений | не заведено |
| B-12 Telegram-webhook без проверки при пустом секрете | не заведено |
| B-14 `VinReportView` без auth и без «дорогого» throttle | не заведено |
| B-15 Легаси-калькулятор `cars/` расходится с настоящим на 25% | владелец решил не трогать |
| `openapi.yaml` описывает 13 путей из 60 | не заведено |
| README описывает 7 приложений из 16 | не заведено |
| Реквизиты компании | #10 |
| Авторские права на фото Copart/IAAI | #11 |
| Серверная фиксация согласия дилера | #13 |
| `Listing.status` принимает значения вне `choices` | #20 |

---

## 1. Краткое резюме

1. Проект **жив и полностью работоспособен**: 365 тестов зелёные, обе Docker-сборки проходят, весь стек из 8 сервисов поднимается и отвечает.
2. Блокеров сборки и запуска **нет ни одного**. `ruff check .`, `tsc --noEmit`, `npm run build` — чисто.
3. **Горит безопасность**: бэкенд в Docker стартует с `DEBUG=True` → `Access-Control-Allow-Origin: <любой>` + `Allow-Credentials: true` и debug-трейсбеки наружу. Проверено живым curl.
4. **Горит эскалация привилегий**: любой аноним регистрируется с `role:"admin"` и получает B2B-доску (200 вместо 403). Второй вектор — `PATCH /auth/profile/ {"role":"admin"}`. Оба воспроизведены.
5. **Горит модерация**: объявление в статусе `hidden` (забаненное админом по жалобе) отдаётся анониму по прямой ссылке с HTTP 200.
6. Продакшн-данные есть **только** в `local_listings` (2 строки). `cars`, `vehicles`, `listings`, `shipments`, `deals`, `favorites`, `payments` — 0 строк в дампе прода. Живой продукт — C2C-каталог Украины, а не импорт из США.
7. `cars` — мёртвый черновик: 0 внешних импортов, 0 тестов, 0 строк в БД, захардкоженные ставки, но эндпоинты публично достижимы и отдают цифры, расходящиеся с реальным калькулятором на 25%.
8. CI **не запускает тесты вообще**, а `manage.py check` в нём завершён `|| true` — пайплайн зелёный по построению.
9. Тесты делают **реальные сетевые вызовы к Telegram Bot API боевым токеном** — это 80% времени прогона (22.5 с → 4.5 с при пустом токене).
10. `openapi.yaml` описывает 13 путей из 60 и версию 1.0.0 вместо 2.0.0; блок «Структура проєкту» в README перечисляет 7 приложений из 16.

---

## 2. Блокеры

**Блокеров запуска и сборки нет.** Ниже — фактический вывод всех проверок.

| Проверка | Результат |
|---|---|
| `python manage.py check --deploy` | 39 issues, все — W-уровня (`.env` содержит `DEBUG=true`, поэтому SECURE_* не включены). Ошибок нет. |
| `python manage.py makemigrations --check --dry-run` | `No changes detected`, exit 0. Незакоммиченных изменений моделей нет. |
| `python manage.py migrate` на чистой БД | Проходит с нуля, 90 миграций, ошибок нет. |
| `python manage.py seed_rates` | Существует, отрабатывает, exit 0 (при доступном кэше — см. баг B-08). |
| `python manage.py test` | **Ran 365 tests in 265.073s — OK**. Падений нет. |
| coverage | **80%** (4374 stmts, 896 miss). |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | 144 из 171 файла были бы переформатированы (форматтер никогда не применялся). |
| `npm ci` | OK, 364 пакета. |
| `npm run lint` | 26 warnings, **0 errors**. |
| `npx tsc --noEmit` | 0 ошибок. |
| `npm run build` | Успешно, 29 маршрутов. |
| `docker compose config` | Валиден, exit 0. |
| `docker compose build backend / frontend` | Обе сборки успешны. |
| `docker compose up` (изолированный проект) | 8/8 сервисов подняты, `backend` и `db` — healthy. |

Smoke-тесты через nginx стека (порт 18080):

```
/                             -> 200      /api/docs/                    -> 200
/ua                           -> 200      /api/v1/local/listings/       -> 200
/listings                     -> 200      /api/v1/pricing/rates/        -> 200
/calculator                   -> 200      /admin/                       -> 302
/static/admin/css/base.css    -> 200
POST /api/v1/pricing/calculate/ -> 201, breakdown полный, total_usd=14134.00
```

Smoke-тесты прав доступа (dev-сервер, чистая БД):

```
POST /api/v1/auth/register/  -> 201     GET /api/v1/b2b/board/ (аноним)   -> 401
POST /api/v1/auth/token/     -> 200     GET /api/v1/b2b/board/ (buyer)    -> 403
GET  /api/v1/auth/profile/   -> 200     GET /api/v1/favorites/ (аноним)   -> 401
```

**Единственное, что ломает «чистую установку по README»** — см. баг B-06: README не упоминает `seed_auction_fees`, и без него калькулятор отдаёт 422. В Docker это уже вылечено в `docker/entrypoint.sh`.

---

## 3. Мусор на удаление

### 3.1 Файлы и каталоги в git

| Путь | Почему кандидат | Доказательства | Риск удаления |
|---|---|---|---|
| `cars/` (11 файлов, 210 строк) | Мёртвый черновик, полностью заменённый `vehicles` + `pricing` | 0 внешних импортов (`grep -rn "from cars"` → пусто); `cars/tests.py` — 2 строки заглушки; `cars_car`=0 и `cars_carimage`=0 строк и в dev-БД, и в проде; фронтенд не вызывает `/api/calculate/` и `/api/list/`; последний осмысленный коммит 2026-06-17 | **Средний** — эндпоинты `/api/calculate/` и `/api/list/` публично живы (200), внешние потребители неизвестны. Требуется удаление вместе с миграцией на удаление таблиц. |
| `Dockerfile` (корень, 138 байт) | Устаревший дубль `Dockerfile.frontend` | `docker-compose.yml` собирает только `Dockerfile.backend` и `Dockerfile.frontend`; корневой содержит `CMD ["node","server.js"]`, но `output: 'standalone'` в `next.config.ts` **не задан** — образ нерабочий | **Низкий** |
| `liqpay==1.0` в `requirements.txt` | Пакет не импортируется нигде | `grep` по всем `.py`: 0 вхождений `import liqpay`; протокол реализован вручную в `payments/liqpay_client.py:1-12` («Официальный SDK — Python 2 only») | **Низкий** |
| `cars/tests.py`, `shipments/tests.py`, `vehicles/tests.py` | Идентичные пустые заглушки `# Create your tests here.` (2 строки) | Совпадают по хешу содержимого; 0 тестов в каждом | **Низкий** (для `shipments`/`vehicles` — заменить реальными тестами, не удалять файл) |
| `api/client.ts:58 apiPut` | Неиспользуемый экспорт | `ts-prune`: единственная реальная находка среди 60+ (остальные — Next.js-конвенции) | **Низкий** |

### 3.2 Не в git, но занимает место на диске

| Путь | Размер | Почему кандидат | Риск |
|---|---|---|---|
| `venv/` | 110 МБ | Устаревший дубль. `venv/pyvenv.cfg` показывает, что он создан **из** `.venv`; в нём 79 пакетов против 184 в `.venv`. Рабочий — `.venv` | Низкий |
| `pgdata/` | 51 МБ | Осиротевший локальный PG-датадир. `grep pgdata` по `docker-compose.yml`, `deploy.sh`, `docker/`, `.github/` → 0 совпадений; Compose использует named volume `postgres_data` | Низкий (проверить, что данные перенесены — PROGRESS.md фиксирует перенос 2026-07-23) |
| `.claude/worktrees/agent-a0e9aa80/` | ~2 МБ | Заброшенный git-worktree на старом коммите `4ef27f4`; полная копия репозитория, засоряет `grep` | Низкий (`git worktree remove`) |
| `media/cars_photos/` | пусто | Пустой каталог от мёртвого приложения `cars` | Низкий |
| `dump.sql` | 352 КБ | Дамп прода в UTF-16 в корне; уже в `.gitignore` | Низкий (переместить в `backups/`) |

### 3.3 Чего в мусоре **нет** (проверено, ложные тревоги сняты)

- **Секретов в истории git нет.** `git log --all --diff-filter=A` по чувствительным именам находит только `.env.example` и `.env.docker.example`. Поиск по значениям даёт только тестовые пароли (`password='pass'`) и CI-заглушки (`autoforyou_ci`). `.env` никогда не коммитился.
- **Артефактов в git нет**: ни `*.log`, ни `db.sqlite3`, ни `*.bak`, ни `.DS_Store`, ни скриншотов, ни дампов среди отслеживаемых файлов.
- **Неиспользуемых npm-зависимостей нет.** `depcheck` помечает 4 devDependencies, все — ложные срабатывания (`tailwindcss`/`@tailwindcss/postcss` подключены через `postcss.config.mjs`, `@types/*` используются компилятором).
- **`reports`, `favorites`, `saved_searches`, `notifications`, `messaging`, `deals` — живые.** У всех подключены urls, все вызываются фронтендом (`frontend/api/reports.ts`, `favorites.ts`, `saved-searches.ts`, `notifications.ts`, `messages.ts`, `deals.ts`) и покрыты тестами.
- **Дублирования логики нет там, где его подозревали:**
  - `favorites` vs `saved_searches` — **не дубли**. Первое хранит избранные объявления, второе — сохранённые фильтры поиска с ежедневным алертом. Разные модели, разные страницы кабинета.
  - `listings` vs `local_listings` vs `deals` — **не дубли**. `listings` = импорт из США (Vehicle + Calculation), `local_listings` = C2C-объявления Украины, `deals` = сделки/отзывы поверх `local_listings`. Пересечений в моделях нет.
  - `cars` vs `vehicles` — **дубль, и `cars` — заброшенный**. Признаки перечислены в таблице 3.1.
- **Мёртвых импортов, переменных и функций нет**: `ruff check --select F` — чисто.
- **Закомментированного кода почти нет**: `ERA001` находит 4 места — `pricing/management/commands/seed_auction_fees.py:54,151`, `pricing/management/commands/seed_rates.py:100`, `tests/test_e2e.py:387`.
- **TODO/FIXME/HACK/XXX в коде — ноль.** Есть 4 осознанных маркера `# ПРОВЕРИТЬ по действующему законодательству` (`pricing/calculator.py:212`, `pricing/models.py:197`, `pricing/management/commands/seed_rates.py:25,127`) — это документированная политика проекта, а не долг.
- **Пустых пакетов и папок без `__init__.py` нет.**

---

## 4. Баги и ошибки

### B-01. Бэкенд в Docker работает с `DEBUG=True` — CORS открыт всем, HTTPS-заголовки выключены

**Симптом.** Поднятый `docker compose` бэкенд отдаёт CORS-заголовки любому origin с `Allow-Credentials: true` и печатает Django-трейсбеки с полным URLconf.

**Воспроизведение.**
```bash
docker compose up -d
curl -i -X OPTIONS http://127.0.0.1/api/v1/local/listings/ \
     -H "Origin: https://evil.example.com" -H "Access-Control-Request-Method: GET"
```
Фактический ответ:
```
HTTP/1.1 200 OK
access-control-allow-origin: https://evil.example.com
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, OPTIONS, PATCH, POST, PUT
```
```bash
curl http://127.0.0.1/api/v1/nonexistent-xyz/   # → страница Django Debug с "Using the URLconf", "Django tried these URL patterns"
docker compose exec backend python -c "from django.conf import settings; print(settings.DEBUG)"   # → True
```

**Причина.** `.env:8` содержит `DEBUG=true`; `docker-compose.yml:38` подключает его как `env_file: .env` без переопределения. Далее `core/settings.py:130` (`CORS_ALLOW_ALL_ORIGINS = DEBUG`) и `core/settings.py:390` (`if not DEBUG and not _TESTING:` — весь блок `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) не срабатывают. Тот же `DEBUG=true` зашит в коммиченный `.env.docker.example:22`. `deploy.sh:16-18` проверяет `SECRET_KEY`, `POSTGRES_PASSWORD` и `DATABASE_URL`, но **не проверяет `DEBUG`**.

Сервисы `celery_worker` и `celery_beat` в `docker-compose.yml:87,109` явно форсируют `DEBUG=false` — то есть проблема уже осознавалась, но `backend` пропустили.

**Фикс.** (1) Добавить в `deploy.sh` preflight `[[ "$DEBUG" == "false" ]] || exit 1`. (2) В `.env.docker.example` сменить дефолт на `DEBUG=false` и отдельно описать локальный dev-режим. (3) Развязать `CORS_ALLOW_ALL_ORIGINS` и `DEBUG` — сделать отдельной переменной `CORS_ALLOW_ALL_ORIGINS=false` по умолчанию.

---

### B-02. Эскалация привилегий: любой пользователь назначает себе `role="admin"`

**Симптом.** Аноним регистрируется с ролью `admin` и получает доступ к B2B-доске оптовых лотов.

**Воспроизведение** (dev-сервер, чистая БД):
```bash
curl -X POST /api/v1/auth/register/ -d '{"email":"e@t.com","password":"AuditPass123!","password2":"AuditPass123!","agreed_to_terms":true,"role":"admin"}'
# → 201 {"email":"e@t.com",...,"role":"admin"}
curl /api/v1/b2b/board/ -H "Authorization: Bearer <token>"   # → 200
# для обычного buyer тот же запрос → 403
```
Второй вектор — изменение роли после регистрации:
```bash
curl -X PATCH /api/v1/auth/profile/ -H "Authorization: Bearer <buyer token>" -d '{"role":"admin"}'
# → 200 {"role":"admin"}   → затем /api/v1/b2b/board/ → 200
```

**Причина.**
- `users/serializers.py:15` — `RegisterSerializer.Meta.fields` включает `'role'` без ограничения choices и без `read_only`.
- `users/serializers.py:35-37` — `UserProfileSerializer` включает `'role'` в `fields`, но **не** в `read_only_fields` (там только `id, email, is_verified_dealer, created_at, telegram_id`); `users/views.py:52` — `ProfileView(generics.RetrieveUpdateAPIView)` разрешает PATCH.
- Потребители роли: `listings/permissions.py:9-13`, `listings/views.py:62,75`, `messaging/views.py:27-29`, `messaging/services.py:98-100,158`.

`is_staff`/`is_superuser` при этом остаются `0` — доступа в Django-админку нет. Проверено запросом к БД.

**Дополнительное следствие.** `messaging/views.py:27-29` (`_can_access`) даёт `role=='admin'` чтение любой переписки по импортному листингу, а `messaging/services.py:156-161` рассылает копии всех таких сообщений всем `role='admin'`. В проде это пока не реализуемо: `listings_listing` = 0 строк, переписок по импортным листингам не существует. Уязвимость латентная, но реальная.

**Фикс.** (1) Убрать `role` из `RegisterSerializer.fields` (или задать `choices=['buyer','dealer']`) — форма регистрации на фронте и так предлагает только эти два (`frontend/app/register/page.tsx:61-62`). (2) Добавить `role` в `read_only_fields` `UserProfileSerializer`. (3) Заменить проверки `user.role == 'admin'` на `user.is_staff` — роль по смыслу является пользовательским атрибутом, а не привилегией. (4) Написать тест «buyer не может стать admin».

---

### B-03. Обход модерации: скрытые и отклонённые объявления читаются по прямой ссылке

**Симптом.** Объявление, скрытое админом по жалобе (`status='hidden'`), а также `pending` и `rejected` — отдаются анониму целиком с HTTP 200, хотя в каталоге их нет.

**Воспроизведение.**
```bash
# создаём объявление → оно уходит в pending, каталог его не показывает
curl /api/v1/local/listings/          # → {"count":0,...}
curl -o /dev/null -w "%{http_code}" /api/v1/local/listings/1/   # → 200, полное тело
# переводим в hidden (как делает админ-экшен по жалобе)
curl -o /dev/null -w "%{http_code}" /api/v1/local/listings/1/   # → 200, всё ещё видно
curl /api/v1/local/listings/1/contact/ -H "Authorization: ..."   # → 404 (эта вью фильтрует корректно)
```

**Причина.** `local_listings/views.py:107-108` — `LocalListingDetailView.get_queryset()` возвращает `_base_queryset()` **без фильтра по статусу**, тогда как список (`local_listings/views.py:81-82`) фильтрует `status=ACTIVE`, а `LocalListingContactView` (`local_listings/views.py:302-306`) — `status__in=[ACTIVE, PENDING]`. Три вью на одну сущность используют три разных правила видимости.

Практическое последствие: админ-экшен `reports/admin.py:10-17` (`hide_listing`) выставляет `status=HIDDEN`, и это **не скрывает объявление** ни от кого, у кого есть URL. То же для `ban_reported_user` (`reports/admin.py:35-38`), который переводит все объявления забаненного в `hidden`.

**Фикс.** В `LocalListingDetailView.get_queryset()` фильтровать `status=ACTIVE` для всех, кроме владельца и `is_staff`. Тест на каждый из статусов `pending/rejected/hidden/expired`.

---

### B-04. LiqPay-чекаут принимает сумму и чужой `listing_id` от клиента

**Симптом.** Авторизованный пользователь может создать платёж на произвольную сумму и привязать его к **чужому** листингу; после оплаты колбэк переводит этот листинг в `in_stock`.

**Причина.** `payments/views.py:69-101` — `LiqPayCheckoutView.post` читает `order_id`, `amount`, `currency`, `description`, `listing_id`, `purpose` напрямую из `request.data` без сериализатора, без валидации и **без проверки владельца** `listing_id`. Далее `payments/views.py:181` вызывает `payment.unlock_listing()`, а `payments/models.py:76-79` меняет статус листинга на `in_stock` без каких-либо проверок.

Сравните с корректной реализацией рядом: `local_listings/views.py:346-358` (`LocalListingPromoteView`) берёт сумму из `PromotionTariff` в БД и проверяет `listing.owner != request.user`.

**Текущая эксплуатируемость — низкая:** `listings_listing` = 0 строк в проде, `LIQPAY_PUBLIC_KEY`/`LIQPAY_PRIVATE_KEY` пусты в `.env`, фронтенд этот эндпоинт не вызывает (единственный платёжный путь во фронте — `frontend/api/local.ts:66` → `/local/listings/<id>/promote/`). Но код рабочий и достижимый.

Побочно: `amount` попадает в `DecimalField` без валидации — нечисловое значение даст 500 вместо 400.

**Фикс.** Ввести `LiqPayCheckoutSerializer`, определять `amount` на сервере по `purpose`+прайс-листу, проверять владение `listing_id`, либо (проще) убрать публичный generic-чекаут и оставить только специализированный `promote`.

---

### B-05. Инвалидация кэша тарифов не работает между процессами без Redis

**Симптом.** После изменения ставки (в админке, командой `seed_*`, из другого процесса) калькулятор до 24 часов возвращает старые тарифы или `422 Отсутствуют активные тарифы`.

**Воспроизведение** (реально наступило в ходе аудита):
```bash
# сервер запущен без REDIS_URL, первый запрос закэшировал пустой список тиров
curl -X POST /api/v1/pricing/calculate/ -d '{...}'   # → 422 "AuctionFeeTier для copart / broker/secured/salvage / $10000.00"
python manage.py seed_auction_fees                    # отдельный процесс, тиры записаны в БД
curl -X POST /api/v1/pricing/calculate/ -d '{...}'   # → всё ещё 422
# перезапуск сервера
curl -X POST /api/v1/pricing/calculate/ -d '{...}'   # → 201, total_usd=14134.00
```
Что данные в БД корректны, подтверждено отдельно: `_lookup_tier('copart', 10000, 'broker','secured','salvage', today)` в свежем процессе возвращает `tier pk=17 title_type=any fee_percent=0.0600`.

**Причина.** `core/settings.py:145-157` — без `REDIS_URL` используется `LocMemCache`, который живёт в памяти одного процесса. `pricing/signals.py` вызывает `pricing/cache.py:74-75 invalidate()` только в том процессе, где произошёл `post_save`. TTL — `pricing/cache.py:12` `_TTL = 60*60*24`.

**Последствие для прода:** при `GUNICORN_WORKERS=3` и **незаданном** `REDIS_URL` правка ставки в админке инвалидирует кэш только одного воркера из трёх — два оставшихся сутки считают по старым ставкам, без каких-либо признаков ошибки. С заданным `REDIS_URL` (текущая конфигурация) кэш общий и проблемы нет.

**Фикс.** Либо считать `REDIS_URL` обязательным при `DEBUG=false` (падать в `ImproperlyConfigured`), либо для `LocMemCache` снизить `_TTL` до десятков секунд.

---

### B-06. README-инструкция оставляет калькулятор нерабочим

**Симптом.** Разработчик, выполнивший «Швидкий старт» из README дословно, получает от калькулятора 422.

**Воспроизведение.** `migrate` → `seed_rates` → `runserver` → `POST /api/v1/pricing/calculate/` →
```json
{"error":"Отсутствуют активные тарифы в БД","missing":["AuctionFeeTier для copart / broker/secured/salvage / $10000.00"]}
```

**Причина.** `README.md:33` перечисляет только `python manage.py seed_rates`. Тиры аукционных сборов сеет **другая** команда — `pricing/management/commands/seed_auction_fees.py`, а справочники регионов — `local_listings/management/commands/seed_regions.py`. В Docker это уже исправлено (`docker/entrypoint.sh:7-9` вызывает все три), но ручной путь остался сломанным.

**Фикс.** Дописать в README `seed_regions` и `seed_auction_fees`; лучше — сделать одну команду `seed_all`, которую вызывают и README, и entrypoint.

---

### B-07. Тесты стучатся в боевой Telegram Bot API

**Симптом.** Прогон тестов делает аутентифицированные HTTP-запросы к `api.telegram.org` боевым токеном из `.env` и тратит на это большую часть времени.

**Воспроизведение.**
```bash
python manage.py test listings          # Ran 7 tests in 22.545s
# в выводе — ответ, пришедший ОТ серверов Telegram:
#   post_listing_to_channel: Telegram error for listing 2: Telegram server says -
#   Bad Request: inline keyboard button URL 'http://localhost/listings/2' is invalid: Wrong HTTP URL

TELEGRAM_BOT_TOKEN="" python manage.py test listings    # Ran 7 tests in 4.500s
```
Разница 22.5 с → 4.5 с — это сетевые round-trip'ы.

**Причина.** `telegram_bot/signals.py:5-13` — `post_save` на `listings.Listing` вызывает `post_listing_to_channel.delay()`. В тестах `core/settings.py:352-355` включает `CELERY_TASK_ALWAYS_EAGER = True`, поэтому задача выполняется синхронно и делает реальный `bot.send_message` (`telegram_bot/tasks.py:206-216`). Токен приезжает из `.env` через `load_dotenv` в `core/settings.py:14`. Собственные тесты `telegram_bot/tests.py` замоканы правильно — «пробивают» тесты **других** приложений, создающие `Listing` (`listings/tests.py`, `tests/test_e2e.py`, `users/tests.py`, `integrations/tests.py`).

При успешной отправке добавляется ещё и `time.sleep(_CHANNEL_THROTTLE_SECONDS)` = 3 с (`telegram_bot/tasks.py:249`).

**Фикс.** Добавить `conftest.py` / базовый `TestCase` с `@override_settings(TELEGRAM_BOT_TOKEN='')`, либо ранний выход из задачи при `settings.TESTING`. `ARCHITECTURE.md:44-48` уже документирует обходной путь `TELEGRAM_BOT_TOKEN="" python manage.py test` — значит, о проблеме знали, но лечили инструкцией, а не кодом.

---

### B-08. `seed_rates` падает с трейсбеком, если Redis недоступен

**Симптом.**
```bash
python manage.py seed_rates
# redis.exceptions.ConnectionError: Error 11001 connecting to redis:6379. getaddrinfo failed.
```

**Причина.** `pricing/cache.py:75` — `invalidate()` вызывает `cache.delete()` без обработки исключений; `django_redis` пробрасывает `ConnectionError` наружу. Наступает всегда, когда `.env` указывает на docker-хост `redis:6379`, а команду запускают вне Docker. В `docker/entrypoint.sh:8` последствие замаскировано `|| true` — то есть при недоступном Redis сиды тихо не применятся, и об этом никто не узнает.

**Фикс.** Обернуть `invalidate`/`invalidate_all` в `try/except` с `logger.warning` — инвалидация кэша не должна ронять сидинг.

---

### B-09. N+1 на главном живом каталоге: 23 запроса на 20 объявлений

**Симптом.** `GET /api/v1/local/listings/` выполняет по одному лишнему `COUNT(*)` на каждое объявление в выдаче.

**Воспроизведение** (измерено через `connection.queries` на 20 объявлениях):
```
GET /api/v1/local/listings/ (20 items) -> 200 | 23 SQL queries
  x20: SELECT COUNT(*) AS "__count" FROM "deals_deal" WHERE ("deals_deal"."se…
   x1: SELECT COUNT(*) FROM "local_listings_locallisting" …
   x1: SELECT "local_listings_locallisting"…
   x1: SELECT "local_listings_locallistingimage"…
Для сравнения: GET /api/v1/listings/ -> 200 | 1 query
```

**Причина.** `local_listings/serializers.py:69-75` — `get_seller_has_badge()` делает `Deal.objects.filter(seller=obj.owner, status='confirmed').count()` для каждого объекта. `_base_queryset()` (`local_listings/views.py:32`) корректно ставит `select_related`/`prefetch_related`, но агрегат по `deals` не покрывает.

Хуже в кабинете: `MyListingsView` использует `LocalListingOwnerSerializer`, наследующий `LocalListingDetailSerializer` с ещё двумя запросами на объект (`local_listings/serializers.py:88-99` — `Review.aggregate(Avg)` и `Deal.count()`), итого **3 лишних запроса на объявление**.

**Фикс.** Аннотировать queryset: `.annotate(confirmed_deals=Count('owner__deals_as_seller', filter=Q(...)), seller_rating=Avg(...))` и читать из аннотации.

---

### B-10. В Docker `backend` не отправляет задачи в Celery — они выполняются внутри HTTP-запроса

**Симптом.** Проверено в поднятом стеке:
```bash
docker compose exec backend python -c "…"
# CELERY_TASK_ALWAYS_EAGER = True
# CELERY_BROKER_URL = memory://
```

**Причина.** `core/settings.py:352` — `if _REDIS_URL and not DEBUG:` использует Redis-брокер, **иначе** eager. Поскольку `backend` наследует `DEBUG=true` из `.env` (см. B-01), условие ложно. Контейнеры `celery_worker` и `celery_beat` форсируют `DEBUG=false` и брокер Redis, но веб-процесс им ничего не отправляет — каждый `.delay()` из вью исполняется синхронно в воркере Gunicorn.

Практически это значит: создание листинга блокируется на сетевом вызове в Telegram, а при успешной отправке — ещё на `time.sleep(3)` (`telegram_bot/tasks.py:249`). Задачи по расписанию (`CELERY_BEAT_SCHEDULE`) при этом работают, так как beat/worker сконфигурированы правильно.

**Фикс.** Тот же, что B-01 — `DEBUG=false` для `backend`. Дополнительно развязать eager-режим от `DEBUG`: отдельная переменная `CELERY_TASK_ALWAYS_EAGER`.

---

### B-11. CI не запускает тесты и не может упасть на проверках Django

**Причина.** `.github/workflows/ci-cd.yml`:
- Джоб `backend` (строки 32-48) выполняет `ruff check`, `manage.py check` и `migrate`. **Шага с тестами нет вообще** — 365 тестов не запускаются ни разу.
- Строка 44: `python manage.py check --deploy --fail-level WARNING 2>&1 | grep -v "^System check" || true` — `|| true` гарантирует нулевой код возврата при любом результате.
- Джоб `deploy` (строка 91) вызывает на сервере `/opt/autoforyou/redeploy.sh`. Этого скрипта **нет в репозитории** (`git ls-files | grep redeploy` → пусто). В репозитории лежит `deploy.sh` с preflight-проверками секретов (добавлен коммитом `accb207 fix(security): fail loudly on missing secrets, add deploy preflight check`), но CI его не вызывает — то есть эти проверки в автоматическом деплое не работают.

**Фикс.** (1) Добавить шаг `python manage.py test` (с `TELEGRAM_BOT_TOKEN: ""` в env, см. B-07). (2) Убрать `|| true`. (3) Внести `redeploy.sh` в репозиторий и заставить его вызывать `deploy.sh` либо перенести preflight-проверки в CI.

---

### B-12. Telegram-webhook не аутентифицирован при пустом секрете

**Причина.** `telegram_bot/views.py:71-75`:
```python
secret = getattr(settings, 'TELEGRAM_WEBHOOK_SECRET', '')
if secret:                       # ← при пустом секрете проверка ПРОПУСКАЕТСЯ целиком
    incoming = request.META.get('HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN', '')
    if incoming != secret:
        return HttpResponse('Forbidden', status=403)
```
В `.env` `TELEGRAM_WEBHOOK_SECRET=` пуст, `TELEGRAM_BOT_TOKEN` задан. Значит `POST /api/v1/telegram/webhook/` от кого угодно попадает в `dp.feed_update()` и обрабатывается роутером бота как настоящее сообщение из Telegram.

Практическая эксплуатируемость ограничена: бот в текущей конфигурации работает в режиме polling (`docker/bot_entrypoint.sh` → `manage.py run_bot`), а привязка аккаунта требует знания UUID-токена (`telegram_bot/handlers.py:110`). Но эндпоинт открыт и исполняет код бота.

**Фикс.** Требовать непустой `TELEGRAM_WEBHOOK_SECRET`, если задан `TELEGRAM_BOT_TOKEN`; иначе отдавать 503.

---

### B-13. Публичные эндпоинты `shipments` раскрывают VIN

**Причина.** `shipments/views.py:11,27` — у `ShipmentListView` и `ShipmentDetailView` нет `permission_classes`, значит действует дефолт `AllowAny` (`core/settings.py:216`). `ShipmentSerializer` (`shipments/serializers.py:21`) вкладывает `VehicleSerializer(many=True)`, включающий `vin`. Проверено: `GET /api/v1/shipments/` → 200 для анонима.

При этом рядом существует приватная вью того же контента: `users/views.py:76-84` — `MyShipmentsView` с `IsAuthenticated` и фильтром `watchers=request.user`. То есть модель `watchers` (`shipments/models.py:47-50`) задумывалась как контроль доступа, но публичная вью её игнорирует.

**Текущая эксплуатируемость — нулевая:** `shipments_shipment` = 0 строк и в дампе прода, и в dev-БД.

**Фикс.** Ограничить публичные вью `IsAuthenticated` + фильтр по `watchers`, либо убрать `vin` из публичного представления.

---

### B-14. `VinReportView` — платный внешний API без аутентификации и без «дорогого» throttle

**Причина.** `integrations/views.py:34` — у `VinReportView` нет ни `permission_classes`, ни `throttle_scope='expensive'`. Внутри (`integrations/views.py:47`) вызывается `get_opendatabot_provider().get_vehicle_info(vin)` — платный Opendatabot. Соседняя `RegistryReportView` (`integrations/views.py:132-135`) те же данные защищает `IsAuthenticated` + `expensive` (10/час), а `VinDecodeView` (`integrations/views.py:84-85`) — `expensive`.

Без `OPENDATABOT_API_KEY` провайдер отдаёт демо-данные (расход нулевой). С ключом — аноним может жечь квоту на дефолтном anon-лимите 60/час на IP. Каждый неизвестный VIN дополнительно пишет строку в `integrations_vinreport` (`integrations/views.py:64`).

**Фикс.** Привести к тому же уровню защиты, что `RegistryReportView`.

---

### B-15. Легаси-калькулятор публично доступен и расходится с реальным на 25%

**Воспроизведение** (один и тот же автомобиль, $10 000, 2.0 л, 2018 г.):
```
GET  /api/calculate/?price=10000&engine=2000&age=8
     → {"auction_fee":1000.0,"delivery_to_ukraine":2200.0,"customs_total":4456.0,"total_cost":17656.0}
POST /api/v1/pricing/calculate/ {"auction_price_usd":"10000","engine_cc":2000,"fuel_type":"petrol","vehicle_year":2018}
     → total_usd = 14134.00
```
Расхождение 3 522 $ (~25%).

**Причина.** `cars/views.py:41-52` считает по захардкоженным константам: `auction_fee = price * 0.10`, `delivery = 2200.0`, `base_rate = 75.0/50.0`, `duty = price * 0.10`, `vat = ... * 0.20`. Это прямое нарушение `CLAUDE.md` §3 («Никакого хардкода ставок во views»). Маршрут подключён в `core/urls.py:34` (`path('api/', include('cars.urls'))`), доступен без аутентификации, ответ не содержит `is_estimate` и никакого предупреждения. `@extend_schema(deprecated=True)` в Swagger стоит, но это не мешает вызовам.

**Фикс.** Удалить приложение `cars` целиком (см. §3.1) или как минимум отключить `path('api/', include('cars.urls'))`.

---

## 5. Качество кода

### 5.1 Линтеры и формат

- `ruff check .` с текущим конфигом (`ruff.toml`: `select = ["E","F","I"]`, `ignore = ["E501"]`) — **чисто**.
- `ruff format --check .` — **144 из 171 файла** были бы переформатированы. Форматтер к проекту никогда не применялся; это одноразовое механическое изменение.
- При расширенном наборе правил (`F,ARG,ERA,B,SIM,N,UP,C4,DJ,S`) — 168 находок:

| Правило | Кол-во | Оценка |
|---|---|---|
| `S106`/`S105` hardcoded-password | 33 | Ложные срабатывания: тестовые пароли и dev-fallback `SECRET_KEY` |
| `ARG002`/`ARG001` unused-argument | 48 | Шум от сигнатур Django/DRF (`sender`, `**kwargs`) |
| `C408` unnecessary-collection-call | 13 | Косметика |
| `N806` non-lowercase-variable | 11 | Локальные `NotifModel`, `Model` — приемлемо |
| `B008` function-call-in-default | 10 | Шум от DRF-полей |
| `SIM105` + `S110` подавление исключений | 18 | **Требует внимания** — см. 5.2 |
| `B904` raise-without-from | 8 | Стоит починить |
| `DJ001` null=True на строковых | 4 | Все 4 — в мёртвом `cars/models.py:19-20` |
| `ERA001` закомментированный код | 4 | Точечно |
| `S324` sha1 | 3 | Ложное: SHA1 требуется протоколом LiqPay v3 |
| `S310` url-open | 1 | Ложное: `pricing/nbu.py:35`, URL захардкожен на `bank.gov.ua`, `timeout=10` |

### 5.2 Проглатывание ошибок

8 мест `try/except Exception: pass` без логирования:
`deals/services.py:13,18` • `local_listings/services.py:70,77` • `messaging/services.py:171,176` • `saved_searches/tasks.py:51` • `telegram_bot/tasks.py:90`

Все — вокруг отправки уведомлений (in-app + Telegram). Намерение понятно (уведомление не должно ронять бизнес-операцию), но в текущем виде полный отказ подсистемы уведомлений не оставляет ни одного следа в логах. Минимум — `logger.warning(..., exc_info=True)`.

### 5.3 Единообразие вью

**36 `APIView` против 22 `generics.*`, `ViewSet` — 0.** Раскол проходит по приложениям, а не по задачам:

| Стиль `generics.*` | Стиль `APIView` |
|---|---|
| `vehicles`, `listings`, `shipments`, `reports` (полностью) | `pricing`, `integrations`, `payments`, `telegram_bot`, `messaging`, `notifications`, `favorites`, `saved_searches`, `deals` (полностью) |
| `users` (6/3), `local_listings` (6/5) — смешанные | |

Последствия конкретные, а не стилистические:

1. **Пагинация не работает на `APIView`.** `PAGE_SIZE: 20` в `core/settings.py:229` применяется только к `generics.*`. Списочные `APIView` отдают всё сразу: `deals/views.py:22-26`, `favorites/views.py:15-24`, `saved_searches/views.py:15-17`, `messaging/views.py:60-73`, `deals/views.py:97-107`. Единственный, где стоит явный лимит — `notifications/views.py:16` (`[:50]`).
2. **drf-spectacular не может вывести схему** для 28 вью — `manage.py check` печатает 28 предупреждений `W002: unable to guess serializer`. Эти эндпоинты в Swagger описаны без тела ответа.
3. Обработка ошибок различается: где-то `raise_exception=True`, где-то ручной `Response({'detail': ...}, status=400)`, где-то `try/except ValueError`.

### 5.4 Бизнес-логика во вью

Соблюдение `CLAUDE.md` §1 неровное:

**Хорошо.** `pricing/calculator.py` — чистая функция, ни одного обращения к БД (проверено grep'ом по `objects.`/`models.`), все ставки приходят снаружи снимком. `deals/views.py` целиком делегирует в `deals/services.py`. `local_listings/services.py`, `messaging/services.py`, `users/services.py`, `notifications/services.py` — существуют и используются.

**Плохо.**
- `local_listings/views.py:330-395` — `LocalListingPromoteView` создаёт `Payment`, генерирует `order_id`, вызывает LiqPay-клиента прямо во вью. Сервиса нет.
- `payments/views.py:65-118` — та же логика продублирована во втором варианте, без валидации (см. B-04).
- `pricing/views.py:145-260` — `CalculateView.post` содержит ~115 строк подбора тарифов (`_lookup_tier`, поиск `us_land`, `ocean`, `eu_to_ua`, курсов, акциза, пенсионного брекета). Сам расчёт вынесен корректно, но сборка снимка ставок — во вью.
- `saved_searches/tasks.py:66-96` — `_apply_filters()` дублирует логику фильтрации `LocalListing`, уже реализованную в `local_listings/filters.py`.

### 5.5 Магические числа

`pricing` — **чисто**. Ставки пошлины и НДС берутся из БД: `pricing/calculator.py:273-274` читает `excise_rate.duty_rate` / `excise_rate.vat_rate` из модели `CustomsExciseRate`. Единственные литералы в `calculator.py` — `Decimal('0')`, `Decimal('0.01')` (округление) и `Decimal('100')` (перевод см³ в «на 100 см³» по формуле акциза). Замороженный снимок ставок в `Calculation` реализован (`rates_snapshot`, `inputs_snapshot`).

Нарушение ровно одно и оно в `cars/views.py:41-52` — см. B-15.

### 5.6 Язык

Смешение русского и украинского внутри одного файла — в 13 Python-файлах. Худшие: `core/settings.py` (53 русских / 21 украинских маркерных символа), `integrations/views.py` (23/44), `integrations/providers.py` (43/6), `pricing/views.py` (28/10). Тексты, видимые пользователю, тоже смешаны: `local_listings` и `deals` отвечают по-украински, `pricing` и `payments` — по-русски. Фронтенд последовательно украиноязычный, при этом `LANGUAGE_CODE = 'ru-ru'` (`core/settings.py:124`).

### 5.7 Фронтенд

**Сильные стороны.** `any` — **0 вхождений** во всём `app/`, `components/`, `lib/`, `api/`. `tsc --noEmit` — 0 ошибок. Fetch-логика не дублируется: единая обёртка `api/client.ts` с автоматическим refresh токена, все 12 файлов в `api/` идут через неё; единственные прямые `fetch()` вне `api/` — в `app/sitemap.ts` (SSR, оправданно). Все ответы API типизированы через `lib/types.ts`. Неиспользуемых зависимостей нет.

**Слабые стороны.**
1. **Каталоги не рендерятся на сервере.** `app/ua/page.tsx` и `app/listings/page.tsx` — серверные компоненты, но данные грузит клиентский `LocalCatalogGrid`/`ListingsGrid` в `useEffect` (`app/ua/LocalCatalogGrid.tsx:15-24`). Поисковые роботы получают пустую сетку, пользователь — вспышку скелетона. При этом `app/sitemap.ts` те же объявления запрашивает на сервере, а страницы деталей (`app/local/[id]/page.tsx`, `app/listings/[id]/page.tsx`) отрендерены серверно. Данные каталога публичные — авторизация не требуется, ничто не мешает SSR.
2. 26 warnings ESLint: `react-hooks/set-state-in-effect` ×10, `react/no-unescaped-entities` ×8, `react-hooks/exhaustive-deps` ×3, `@typescript-eslint/no-unused-vars` ×3, `@next/next/no-html-link-for-pages` ×2 (последнее — `<a href>` вместо `<Link>`, ломает клиентскую навигацию).
3. `npm audit`: **8 уязвимостей (7 high, 1 moderate)**, в т.ч. 9 advisories на `next@16.2.9` (SSRF в Server Actions, обход middleware, DoS в Image Optimization, раскрытие внутренних Server Function endpoints). Исправляется обновлением до `next@16.3.4`.
4. `api/client.ts:58` — экспорт `apiPut` не используется нигде.

### 5.8 Тесты

**365 тестов, все зелёные, покрытие 80%** (4374 инструкции, 896 непокрытых).

Полностью непокрытые модули (0%):

| Модуль | Строк |
|---|---|
| `telegram_bot/handlers.py` | 66 |
| `integrations/management/commands/import_lot.py` | 64 |
| `integrations/management/commands/upload_lot_photos.py` | 43 |
| `telegram_bot/management/commands/run_bot.py` | 27 |
| `telegram_bot/management/commands/set_webhook.py` | 27 |
| `pricing/management/commands/fetch_nbu_rates.py` | 25 |
| `telegram_bot/management/commands/unset_webhook.py` | 24 |
| `telegram_bot/middleware.py` | 18 |
| `core/asgi.py`, `core/wsgi.py` | 8 |

То есть **весь рантайм Telegram-бота не покрыт вообще** — при том что бот работает в проде и подтверждён (`ARCHITECTURE.md:31-40`).

Слабо покрытые: `cars/views.py` 36% (мёртвый), `telegram_bot/tasks.py` 39%, `reports/admin.py` 43%, `telegram_bot/views.py` 48%, `users/admin.py` 63%.

Файлов `tests.py` нет у `favorites`, `notifications`, `payments`, `saved_searches` — но они покрыты пакетом `tests/`. Пустые заглушки на 2 строки — у `cars`, `shipments`, `vehicles`; для `shipments` и `vehicles` это значит **0 собственных тестов на живой код** (косвенное покрытие идёт через `listings`/`integrations`).

Ни один из подтверждённых дефектов безопасности B-02, B-03, B-04, B-13 тестом не покрыт — иначе он бы упал.

Распределение: `local_listings` 77 тестов, `pricing` 64, `integrations` 43, `tests/test_e2e.py` 38, `deals` 31, `tests/test_favorites…` 28, `users` 27, `messaging` 23, `telegram_bot` 20, `listings` 7, `reports` 7.

`pytest` в проекте **не используется и не установлен**: нет `pytest.ini`, `pyproject.toml`, `conftest.py`, `setup.cfg`; в `requirements.txt` его нет. Используется штатный раннер Django. `coverage` также отсутствовал в окружении — для этого аудита установлен вручную в `.venv`.

---

## 6. Безопасность

### Сводка по важности

| # | Находка | Важность | Эксплуатируется сейчас |
|---|---|---|---|
| B-01 | `DEBUG=True` в Docker → CORS `*` + credentials, нет SECURE_*, debug-трейсбеки | **Критическая** | Да, проверено curl |
| B-02 | Самоназначение `role="admin"` при регистрации и через PATCH профиля | **Критическая** | Да, проверено (403 → 200) |
| B-03 | `hidden`/`rejected`/`pending` объявления читаются анонимом по прямой ссылке | **Высокая** | Да, проверено (HTTP 200) |
| B-04 | LiqPay-чекаут: сумма и чужой `listing_id` от клиента | **Высокая** | Латентно (0 листингов, ключи пусты) |
| — | Любой авторизованный публикует в Telegram-канал через `POST /api/v1/listings/create/` | **Средняя** | Да (гейт — только `IsAuthenticated`) |
| B-12 | Telegram-webhook без проверки при пустом `TELEGRAM_WEBHOOK_SECRET` | **Средняя** | Да (эндпоинт открыт) |
| B-07 | Тесты шлют запросы в Telegram боевым токеном | **Средняя** | Да |
| B-13 | `shipments` публичны, отдают VIN | **Средняя** | Латентно (0 строк) |
| B-15 | Легаси-калькулятор публичен, ставки захардкожены, расхождение 25% | **Средняя** | Да |
| B-14 | `VinReportView` без auth и без «дорогого» throttle на платном API | Низкая | Только с `OPENDATABOT_API_KEY` |
| — | `npm audit`: 7 high, включая 9 advisories на `next@16.2.9` | Средняя | Зависит от вектора |
| — | Аноним создаёт строки в `pricing_calculation` | Низкая | Да (60/час на IP) |
| — | `/local/listings/<id>/contact/` отдаёт телефон для `pending` объявлений | Низкая | Да, проверено |

### Отдельно: публикация в Telegram-канал любым пользователем

`POST /api/v1/listings/create/` защищён только `permissions.IsAuthenticated` (`listings/views.py:86`). `ListingCreateSerializer` (`listings/serializers.py:34-46`) принимает `channel` и `is_express_buyout` от клиента. Сигнал `telegram_bot/signals.py:5-13` постит в публичный канал `@AUTO_F_Y` любой новый `retail`-листинг и любой `is_express_buyout`. Модерации, в отличие от `local_listings` (там `pending` → ручное одобрение), нет. Любой зарегистрированный аккаунт может слать произвольный текст в публичный канал проекта.

### Секреты

**Утечек не обнаружено.**
- В истории git ни один файл с секретами не коммитился: `git log --all --diff-filter=A --name-only` по маске `\.env|secret|\.pem|\.key|credential|\.sqlite3|dump\.sql` даёт только `.env.example` и `.env.docker.example`.
- Поиск по значениям (`git log -p --all | grep -iE "^\+.*(SECRET_KEY|PASSWORD|TOKEN|API_KEY)"`) находит только тестовые пароли (`password='pass'`, `'testpassword123'`), CI-заглушки (`autoforyou_ci`) и мок-токены (`'fake-token'`).
- `.env` с боевым `TELEGRAM_BOT_TOKEN` есть на диске, но не отслеживается и покрыт `.gitignore`.
- Dev-fallback `SECRET_KEY` в `core/settings.py:27` — в истории есть, но применяется только при `DEBUG=true`; при `DEBUG=false` без переменной поднимается `ImproperlyConfigured` (`core/settings.py:29-32`). Это правильно.

### Права доступа на эндпоинтах

Инвентаризация выполнена по всем 16 приложениям. Дефолт — `AllowAny` (`core/settings.py:216`), поэтому вью без явного `permission_classes` открыты.

**Корректно закрыто (проверено live):** B2B-доска (`IsVerifiedDealerOrAdmin`, аноним 401 / buyer 403), `favorites`, `saved-searches`, `notifications`, `messages`, `deals`, `me/calculations`, `me/shipments`, `me/trusted-shops`, `dealers/*`, `local/my-listings`, загрузка и удаление фото объявления, `lots/import` (`IsAdminUser`), `registry` (`IsAuthenticated` + throttle `expensive`), `contact` (`IsAuthenticated` + throttle `contact` 20/час).

**Чужие расчёты защищены:** `Calculation` доступен только через `MyCalculationsView` с фильтром `user=request.user` (`users/views.py:68`); публичного read-эндпоинта для `Calculation` нет.

**Владение объектами проверяется** в `local_listings` (`IsOwnerOrAdmin` + явный `check_object_permissions`, `_get_owned_listing`), в `deals` (сервисный слой), в `TrustedShop` (фильтр по `owner`). Не проверяется в `payments` (B-04).

**Открыто по умолчанию без явного намерения:** `shipments` (B-13), `VinReportView` (B-14), `cars` (B-15), `pricing.CalculateView`/`ActiveRatesView`. Последние два, вероятно, задуманы публичными — но `CalculateView` при этом пишет в БД (`pricing/views.py:326`, `user=None` для анонима).

**Бан пользователя работает** через `is_active=False`: `rest_framework_simplejwt/authentication.py:138` отклоняет токен неактивного пользователя. Поле `is_banned` при этом **нигде в коде не читается** — только выставляется админ-экшенами (`users/admin.py:12-15`, `reports/admin.py:30-33`) и отображается. Тесты на бан есть: `local_listings/tests.py:935-946`.

### Конфигурация: `.env.example` / `.env.docker.example` vs код

Сверка выполнена автоматически (53 переменные, читаемые из кода в `.py`/`.ts`/`.sh`/`.yml`).

**Лишних переменных нет.** Единственный кандидат — `COMPOSE_PROJECT_NAME`, но он потребляется самим Docker Compose, а не кодом. Это корректно.

**Недостающие в `.env.example`** (у всех есть дефолт в коде, ничего не ломается — но настройки недокументированы):
`CORS_ALLOWED_ORIGINS` ← **важно, влияет на безопасность**, `THROTTLE_ANON_RATE`, `THROTTLE_USER_RATE`, `THROTTLE_EXPENSIVE_RATE`, `THROTTLE_MESSAGES_RATE`, `THROTTLE_CONTACT_RATE`, `ANTISPAM_MODE`, `SELLER_BADGE_THRESHOLD`, `AUCTION_DEFAULT_MEMBER_TYPE`, `LOCAL_LISTING_MAX_PHOTOS`, `LOCAL_LISTING_PHOTO_MAX_SIZE_MB`, `LOCAL_LISTING_EXPIRY_DAYS`, `NEXT_PUBLIC_DEMO_MODE`, `INTERNAL_API_URL`, `PORT`, `E2E_BASE_URL`.

**Недостающие в `.env.docker.example`** — то же плюс `LOCAL_LISTING_MAX_ACTIVE` и `S3_REGION`.

### `.gitignore`

Покрывает всё существенное: `__pycache__`, `venv/`, `.venv/`, `*.sqlite3`, `media/`, `staticfiles/`, `*.log`, `.idea/`, `.env`, `backups/`, `pgdata/`, `dump.sql`, `.claude/`. Проверено `git status --ignored`: неотслеживаемых артефактов, которые должны были попасть в git, нет.

Мелочи:
- `.ruff_cache/` в корневом `.gitignore` отсутствует. На практике игнорируется — ruff кладёт собственный `.ruff_cache/.gitignore`. Стоит добавить явно.
- `.claude/settings.local.json` **отслеживается** git'ом, хотя `.gitignore` содержит `.claude/`. Правило не действует на уже добавленные файлы (файл попал в индекс до появления правила). Он содержит длинный список локальных разрешений Claude Code со ссылками на несуществующий `venv/` — стоит убрать из индекса (`git rm --cached`).

---

## 7. Расхождения кода и документации

| Документ | Расхождение | Факт |
|---|---|---|
| `README.md:83-100` «Структура проєкту» | Перечислено **7** приложений: `users`, `vehicles`, `pricing`, `listings`, `shipments`, `integrations`, `core` | В `INSTALLED_APPS` **16** локальных приложений. Отсутствуют в README: `local_listings`, `cars`, `telegram_bot`, `messaging`, `notifications`, `favorites`, `saved_searches`, `reports`, `deals`, `payments`. **README устарел, лишние папки — не мусор** (кроме `cars`) |
| `README.md:66-74` «Функціонал» | Не упомянут C2C-каталог Украины | Это **единственная часть с продакшн-данными** (`local_listings_locallisting` = 2 строки в дампе; `listings_listing`, `vehicles_vehicle`, `cars_car`, `shipments_shipment` = 0) |
| `README.md` целиком | Нет ни слова о Docker, Celery, Redis, Telegram-боте, LiqPay, системе жалоб, сделках и отзывах, избранном, сохранённых поисках, сообщениях | Всё это реализовано и работает |
| `README.md:53-64` «URL-карта» | Нет `/ua`, `/local/*`, `/me/messages`, `/me/deals`, `/me/favorites`, `/me/notifications`, `/me/saved-searches`, `/me/telegram`, `/rules`, `/privacy`, `/terms`, `/cookies` | 29 маршрутов в прод-сборке |
| `README.md:33` «Швидкий старт» | Только `seed_rates` | Нужны ещё `seed_regions` и `seed_auction_fees`, иначе калькулятор отдаёт 422 (см. B-06) |
| `openapi.yaml` | **13 путей** из 60, `version: 1.0.0` | `manage.py spectacular` генерирует 60 путей, `version: 2.0.0` (`core/settings.py:271`). Отсутствуют целиком: `local`, `deals`, `messages`, `notifications`, `favorites`, `saved-searches`, `reports`, `payments`, `b2b`, `dealers`, `telegram`, `shipments`, `me/*`, `lots/import`, VIN-эндпоинты. Файл не перегенерировался с 2026-06-17 |
| `openapi.yaml` | — | `POST /api/v1/telegram/webhook/` не попадает в схему ни в старой, ни в новой версии: это обычный Django `View`, а не DRF-вью |
| `ARCHITECTURE.md` (622 строки) | Не журнал архитектуры, а хронологический changelog по «промтам»; дублирует `PROGRESS.md` (1339 строк) | Приложение `cars` не упомянуто **ни разу** (0 вхождений). Архитектурного описания слоёв, схемы данных и границ приложений нет |
| `docs/PRODUCTION_ROADMAP.md:9` | «199 тестов → все зелёные» | Фактически **365** тестов |
| `CLAUDE.md` §3 «Никакого хардкода ставок во views» | — | Соблюдается в `pricing`. **Нарушается** в `cars/views.py:41-52` — и это публично достижимый эндпоинт (B-15) |
| `CLAUDE.md` §1 «Бизнес-логика — в сервисном слое» | — | Соблюдается в `deals`, `local_listings` (модерация), `users`, `messaging`, `notifications`. Нарушается в `local_listings/views.py:330-395`, `payments/views.py:65-118`, `pricing/views.py:145-260` |
| `CLAUDE.md` таблица приложений | Перечислено 5 приложений, `cars` помечен «legacy, оставлен временно» | «Временно» длится с 2026-06-17. 11 других приложений в таблице отсутствуют |
| `.github/workflows/ci-cd.yml:91` | Деплой вызывает `/opt/autoforyou/redeploy.sh` | Этого файла нет в репозитории. Лежащий в репозитории `deploy.sh` с preflight-проверками секретов в автоматическом деплое **не участвует** |
| `ARCHITECTURE.md:44-48` | Документирует обходной путь `TELEGRAM_BOT_TOKEN="" python manage.py test` | Проблема (B-07) вылечена инструкцией вместо кода |

---

## 8. План работ

Порядок — по отношению «выгода / риск». Оценка в шагах = отдельных атомарных коммитах.

### Этап A — безопасность (5 шагов, высокая выгода, низкий риск)

| # | Задача | Шагов | Риск |
|---|---|---|---|
| A1 | **B-02**: убрать `role` из `RegisterSerializer.fields`, добавить в `read_only_fields` профиля, заменить проверки `role=='admin'` на `is_staff`. Сначала тест, фиксирующий текущее поведение | 2 | Низкий. Затрагивает `IsVerifiedDealerOrAdmin`, `messaging._can_access` — согласовать |
| A2 | **B-01/B-10**: `DEBUG=false` в `.env.docker.example`; развязать `CORS_ALLOW_ALL_ORIGINS` и `CELERY_TASK_ALWAYS_EAGER` от `DEBUG`; добавить в `deploy.sh` preflight на `DEBUG` | 1 | Низкий. Требует проверки, что после `DEBUG=false` стек поднимается (нужны `ALLOWED_HOSTS` и `CORS_ALLOWED_ORIGINS`) |
| A3 | **B-03**: фильтр по статусу в `LocalListingDetailView.get_queryset()`; тесты на `pending/rejected/hidden/expired` | 1 | Низкий |
| A4 | **B-04**: сериализатор для `LiqPayCheckoutView`, сумма с сервера, проверка владельца `listing_id` | 1 | Средний — трогает платежи. Тесты в `tests/test_e2e.py` уже покрывают колбэк |
| A5 | **B-12/B-14/B-13**: обязательный webhook-секрет; `IsAuthenticated`+`expensive` на `VinReportView`; закрыть `shipments` фильтром по `watchers` | 2 | Низкий (0 строк в `shipments`) |

### Этап B — блокирующие для процесса (3 шага, высокая выгода, низкий риск)

| # | Задача | Шагов | Риск |
|---|---|---|---|
| B1 | **B-11**: добавить в CI шаг `manage.py test` с `TELEGRAM_BOT_TOKEN: ""`; убрать `|| true` из `manage.py check` | 1 | Низкий. Тесты уже зелёные |
| B2 | **B-07**: заглушить Telegram в тестах на уровне кода (не инструкции) | 1 | Низкий. Прогон ускорится в ~5 раз |
| B3 | **B-11**: внести `redeploy.sh` в репозиторий или заставить CI вызывать `deploy.sh` | 1 | Средний — трогает боевой деплой, нужен доступ к серверу. **Не проверено:** содержимое `/opt/autoforyou/redeploy.sh` мне недоступно |

### Этап C — мусор и мёртвый код (4 шага, средняя выгода, разный риск)

| # | Задача | Шагов | Риск |
|---|---|---|---|
| C1 | Удалить `cars/` (**B-15**): убрать из `INSTALLED_APPS`, снять `path('api/', include('cars.urls'))`, добавить миграцию на удаление таблиц, удалить папку и `media/cars_photos/` | 3 (отдельный коммит на отключение маршрута, на удаление кода, на миграцию) | **Средний** — публичные эндпоинты гасятся. Требует явного подтверждения |
| C2 | Удалить корневой `Dockerfile`; убрать `liqpay==1.0` из `requirements.txt`; удалить `apiPut` | 1 | Низкий |
| C3 | Очистить диск: `git worktree remove .claude/worktrees/agent-a0e9aa80`, удалить `venv/` и `pgdata/`, перенести `dump.sql` в `backups/` | 1 | Низкий (всё вне git). `pgdata/` — сверить, что данные перенесены |
| C4 | `git rm --cached .claude/settings.local.json`; добавить `.ruff_cache/` в `.gitignore` | 1 | Низкий |

### Этап D — линтеры и формат (2 шага, средняя выгода, низкий риск)

| # | Задача | Шагов | Риск |
|---|---|---|---|
| D1 | Прогнать `ruff format .` (144 файла), добавить `ruff format --check` в CI | 1 | Низкий, но огромный diff — отдельным коммитом, чтобы не мешал `git blame` |
| D2 | Добавить логирование в 8 мест `except: pass`; починить 8 `B904`; удалить 4 `ERA001`; расширить `select` в `ruff.toml` до `E,F,I,B,SIM,UP,C4` | 2 | Низкий |

### Этап E — рефакторинг (5 шагов, средняя выгода, средний риск)

| # | Задача | Шагов | Риск |
|---|---|---|---|
| E1 | **B-09**: убрать N+1 через `annotate()` в `local_listings`; тест, считающий запросы | 1 | Низкий |
| E2 | **B-05/B-08**: обернуть `pricing/cache.invalidate` в try/except; требовать `REDIS_URL` при `DEBUG=false` | 1 | Низкий |
| E3 | Ввести пагинацию на списочных `APIView` (или перевести их на `generics.ListAPIView`) — 5 эндпоинтов | 2 | **Средний** — меняет форму ответа API, нужна правка фронтенда. Требует согласования |
| E4 | Вынести `LocalListingPromoteView` и подбор ставок из `CalculateView` в сервисный слой (`CLAUDE.md` §1) | 2 | Средний |
| E5 | Тесты на непокрытое: `telegram_bot/handlers.py`, `middleware.py`, `fetch_nbu_rates`; собственные тесты `vehicles` и `shipments` | 2 | Низкий |

### Этап F — фронтенд (3 шага)

| # | Задача | Шагов | Риск |
|---|---|---|---|
| F1 | `npm audit fix --force` → `next@16.3.4`; проверить `build` + `lint` + `tsc` | 1 | **Средний** — мажорный патч Next.js. Обязательно прогнать `npm run build` и e2e |
| F2 | Перевести `/ua` и `/listings` на серверный рендер каталога | 2 | Средний — меняет структуру страниц, важно для SEO |
| F3 | Убрать 26 ESLint-warnings, включая 2 `no-html-link-for-pages` | 1 | Низкий |

### Этап G — документация (4 шага, высокая выгода, нулевой риск)

| # | Задача | Шагов |
|---|---|---|
| G1 | Перегенерировать `openapi.yaml` (`manage.py spectacular`), добавить в CI проверку актуальности | 1 |
| G2 | Переписать `README.md`: 16 приложений, C2C-каталог, Docker/Celery/Redis/бот/платежи, полная URL-карта, корректный «Швидкий старт» с тремя seed-командами | 1 |
| G3 | Превратить `ARCHITECTURE.md` в описание архитектуры (слои, границы приложений, схема данных, поток расчёта), а хронологию оставить в `PROGRESS.md` | 1 |
| G4 | Обновить `CLAUDE.md` (таблица приложений) и `docs/PRODUCTION_ROADMAP.md` (365 тестов); дополнить `.env.example`/`.env.docker.example` 16 недостающими переменными | 1 |

---

## Что не проверено и почему

- **`/opt/autoforyou/redeploy.sh`** — файл существует только на боевом сервере, доступа к нему нет.
- **Реальный прогон LiqPay** — `LIQPAY_PUBLIC_KEY`/`LIQPAY_PRIVATE_KEY` пусты, публичного HTTPS-адреса для колбэка нет.
- **Opendatabot и Apify с настоящими ключами** — `OPENDATABOT_API_KEY` и `APIFY_TOKEN` пусты, провайдеры отдают демо-данные.
- **Playwright e2e (`frontend/e2e/`)** — не запускались: требуется одновременно поднятый бэкенд и фронтенд плюс установка браузеров Playwright.
- **`vulture`** — не запускался: `ruff --select F` уже дал 0 находок по мёртвым импортам/переменным, `ts-prune` и `depcheck` покрыли фронтенд.
- **`knip`** — не запускался, использован `ts-prune` (легче, тот же класс находок).
- **Поведение под нагрузкой, индексы, планы запросов** — вне рамок аудита.

## Что было сделано с окружением

- В `.venv` установлен пакет `coverage==7.16.0` (его не было; в `requirements.txt` не добавлен).
- В `frontend/` выполнен `npm ci` — `node_modules` переустановлены из `package-lock.json`.
- Собраны Docker-образы `autoforyou-backend` и `autoforyou-frontend`.
- Стек поднимался под **отдельным** именем проекта `autoforyouaudit` на порту 18080 и снесён вместе со своими томами (`down -v`). Тома `autoforyou_postgres_data`, `autoforyou_media`, `autoforyou_static` не затрагивались — проверено после удаления.
- Все проверки шли на временной БД в scratch-каталоге. `db.sqlite3` в корне не изменялся.
- **Рабочее дерево git чистое, ни один файл репозитория не изменён** (`git status --porcelain` — пусто).
