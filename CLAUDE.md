# AUTOforYOU — Конвенции проекта

## Стек
Python 3.12, Django 6.x, DRF, SimpleJWT, Pillow, PostgreSQL (sqlite3 в dev), CORS Headers.

## Структура приложений
| App        | Ответственность                                      |
|------------|------------------------------------------------------|
| `users`    | CustomUser, JWT-аутентификация                       |
| `vehicles` | Модель Vehicle (каноническая), VehicleImage          |
| `pricing`  | Тарифные справочники, сервис калькулятора, Calculation|
| `listings` | Listing (объявление на маркетплейсе)                 |
| `cars`     | Устаревший Car/CarImage (legacy, оставлен временно)  |
| `local_listings` | Объявления частников по Украине                |
| `shipments`  | Отслеживание доставки/контейнеров                    |
| `integrations` | Внешние API (реестры, уведомления), троттлинг      |
| `payments`   | Платежи (LiqPay)                                     |
| `telegram_bot` | Telegram-бот и каналы                              |
| `messaging`  | Диалоги покупатель–продавец                          |
| `notifications` | Уведомления пользователю                          |
| `favorites`  | Избранное                                            |
| `site_settings` | Реквизиты владельца ПДн, контакты, юр. документы (singleton) |
| `saved_searches` | Сохранённые поиски                               |
| `reports`    | Жалобы на объявления                                 |
| `deals`      | Сделки                                               |
| `task_ledger` | Учёт упавших Celery-задач (`FailedTask`), только просмотр в админке |
| `content` | Тексты «Як працює пригон» и FAQ (`ImportStep`, `FaqItem`), правятся в админке |
| `landings` | SEO-страницы «Пригон [модель] з США»: `ModelLandingPage`, расчёт через калькулятор (`landings/services.py`), публикация только с расчётом |
| `metrics` | Щоденні лічильники без ПДн (`DailyMetric`, `record_metric`) |

`core` — проект (настройки, celery); в `INSTALLED_APPS` только ради management-команд (`monitoring_test`), моделей нет. Базовый класс сетевых задач с повторами — `core.tasks.ResilientTask` (`base=ResilientTask`).

## Принципы

### 1. Сервисный слой
Бизнес-логика — в `pricing/calculator.py`, не во views и не в models.
Калькулятор — чистая детерминированная функция без обращений к БД.

### 2. Деньги
- Только `Decimal`, никогда `float`.
- Каждая сумма знает свою валюту (поле `currency` рядом с `amount`).
- Курс валют фиксируется снимком на момент расчёта.

### 3. Тарифы — это данные
Все ставки хранятся в редактируемых моделях админки с полями `valid_from`/`valid_to`.
Никакого хардкода ставок во views или в calculator.py.
Каждый `Calculation` хранит замороженный JSON-снимок входов и применённых ставок.

### 4. Кастомная модель User
`AUTH_USER_MODEL = 'users.CustomUser'`. Всегда использовать `settings.AUTH_USER_MODEL` в ForeignKey.

### 5. Всегда рабочее состояние
После каждого шага: миграции применены, тесты зелёные, `runserver` стартует без ошибок.

### 6. Инкрементальные коммиты
Понятные сообщения после каждого логического шага.

## Роли и права
- `role` — только метка. Регистрация всегда даёт `buyer`, поле `role` в запросе игнорируется.
- `dealer` — только `is_verified_dealer=True` (ставит `approve_application`, не админка вручную).
- `broker`, `moderator`, `admin` назначает только администратор (действия «Призначити…» в админке пользователей).
- `is_staff` — только доступ в Django Admin. Модерация — `user.has_perm('local_listings.moderate_locallisting')` (группы «Модератори», «Адміністратори»).
- Хелперы и классы: `users/permissions.py` (`IsBroker`, `IsBrokerOrAdmin`, `IsModerator`, `IsAdminRole`), `user.is_broker/is_moderator/is_admin_role`.
- `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`: у публичного view — явный `AllowAny`. Тест-аудит: `core/tests.py`.

## Именование
- Модели: CamelCase, в единственном числе (`Vehicle`, `Listing`, `Calculation`).
- URL: kebab-case (`/api/v1/vehicles/`, `/api/v1/pricing/calculate/`).
- Поля денег: `{name}_usd` / `{name}_uah` / `{name}_eur` — суффикс валюты.

## Важно: украинская растаможка
Ставки акциза и пенсионного сбора хранятся в БД (модели `CustomsExciseRate`, `PensionFundBracket`)
с дефолтными placeholder-значениями. Они помечены `# ПРОВЕРИТЬ по действующему законодательству`.
Результат калькулятора всегда возвращает флаг `is_estimate: true`.
## Тестирование — правила
- Backend-тесты: `scripts/test-backend.ps1` / `.sh` или `DATABASE_URL= REDIS_URL= .venv/Scripts/python.exe manage.py test`. Окружение — только `.venv/`.
- Ни один тест не ходит в сеть: провайдеры мокаются, предохранитель `core/test_runner.py` роняет тест при внешнем соединении. Новый ключ провайдера — сразу в блок обнуления `if _TESTING:` в `core/settings.py`.
- Данные для тестов — из `tests/factories.py`. Новые локальные `_make_user` не заводить.
- Тесты, читающие тарифы через кэш, наследуются от `tests.base.CleanCacheTestCase`, seed — в `setUpTestData`.
- Один ожидаемый код ответа в ассерте. Никаких `assertIn(status, (200, 400))` и `if results:` перед проверкой. `assertRaisesMessage` вместо `assertRaises(msg=)`.
- Каждый новый/исправленный тест проверяется мутацией: сломать код — тест красный — откатить.
- На каждый эндпоинт с личными данными — тесты 401 (аноним) и 403/404 (чужой), бриф §3.
- Для функций без UI — Django-тесты с моками внешних API (бриф §5 п. 3).

## E2E (Playwright) — правила
- Запускать только из `frontend/`.
- Стек: `docker compose -p autoforyou-e2e --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build` (env из `.env.e2e`, боевой `.env` не подхватывается; шаблон `.env.e2e.example`), затем `docker compose -p autoforyou-e2e exec -T redis redis-cli FLUSHALL` (сброс троттлинга), затем `... exec -T backend python manage.py e2e_seed`. Сайт — `http://localhost` (nginx), не `:3000`. Dev-стек занимает те же порты 80 — перед прогоном его остановить.
- Постоянное разрешение владельца (2026-10-13), спрашивать не нужно: для e2e — `docker compose down` dev-стека **без `-v`**, подъём e2e-стека, после прогона `docker compose -p autoforyou-e2e … down -v` (e2e-стек с томами) и `docker compose up -d` dev-стека обратно. Тома dev-стека (`-v`) не трогать никогда.
- Импорт `test` — из `e2e/fixtures`. Роли — через `storageState` (`e2e/.auth/<role>.json`). Новые пользователи — только `…@e2e.test`, тестовые записи — с префиксом `[E2E]`.
- Негативные проверки — через отсутствие сетевого запроса (`helpers/network.ts`) и `validity.*`, а не мгновенное «элемента нет». Ошибки сверять по тексту, не по CSS-классу.
- `fill()` на `input[type=number]` с нечисловым значением кидает исключение — печатать с клавиатуры.
- Мобильные тесты — `@mobile`, кросс-браузерные — `@smoke`. Незаработавшее — `test.fixme('<ID> → <задача>')`, не молча зелёный тест.
- `frontend/e2e/test-1.spec.ts` не переименовывать (решение владельца).

## Известные ловушки
- `openapi.yaml` генерировать только против PostgreSQL (`DATABASE_URL=postgresql://… python manage.py spectacular --file openapi.yaml`): на SQLite другие границы int, и CI падает.
- Next пререндерит страницы при `npm run build`, где backend недоступен. Для страниц с данными — `export const dynamic = 'force-dynamic'`.
- TextChoices выносить на уровень модуля: тело `class Meta` не видит вложенные классы модели.
- Тесты с настоящими aiogram `Update` — `addCleanup(Update.event_type.fget.cache_clear)`, иначе segfault 139 в CI после «OK». Страховка — в `core/test_runner.py`.
- Локальный `.env` — docker-шаблон с хостами `db`/`redis`, поэтому тесты вне Docker — с пустыми `DATABASE_URL` и `REDIS_URL`.
- `*.sh` — только LF (`.gitattributes`). CRLF ломает backend-контейнер на Windows.
- `main` в Actions может быть красным из-за deploy-джобы без SSH-секретов (12-Q2), при этом проверки зелёные — не путать.
- `cars/` — legacy, не трогать без решения владельца.

## Определение «готово»
См. `docs/BRIEF.md` §5.

## Агенты и модели
Агенты лежат в .claude/agents/. Основная сессия координирует и принимает решения, работу делегирует:
- code-scout (Haiku) — найти в коде, получить путь:строки. Не читать файлы целиком в основной сессии.
- test-runner (Haiku) — любые прогоны тестов, сборки, Playwright. Длинный вывод в основной контекст не тянуть.
- implementer (Sonnet) — выполнение обычной задачи из docs/tasks/.
- security-reviewer (Opus) — обязательная проверка после задач этапа 1, задачи 4.1 и любых правок
  платежей, прав доступа и личных данных. Замечания «критично» и «важно» исправить до закрытия задачи.
- task-writer (Sonnet) — создание и правка файлов задач.
- parity-auditor (Sonnet) — только для промта 01.

Модель основной сессии:
- Sonnet — по умолчанию.
- Opus — задачи 1.3, 1.4, 1.10, 4.1 и планирование этапов/ROADMAP.

## Экономия токенов
- Одна сессия — одна задача. После задачи: коммит → /clear.
- Во время задачи — тесты только затронутого приложения, полный прогон один раз в конце (через test-runner).
- Не перечитывай файлы, уже прочитанные в сессии. Читай фрагменты, а не файлы целиком.
- Не делай работу за агента заново в основной сессии.