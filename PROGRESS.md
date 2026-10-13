# PROGRESS.md — Живой журнал прогресса

## Статус: ВОЛНА-1, этап 0 — 0.1–0.6 ✓, 1.2 ✓, 1.2b ✓, дальше 1.3 (Opus) → … (порядок — ROADMAP.md) | Сервер: Hetzner CX23 (запасной CAX11), Docker Compose | Платежи и C2C-подача выключены флагами до ВОЛНЫ-2

> История до 2026-10-12 (фазы 1–2, C2C-промты, Docker, QA, перенос БД) — `docs/PROGRESS_ARCHIVE.md`.

---

## Задача 1.2b: is_staff → права по ролям (2026-10-13) — ЗАВЕРШЕНО

- `can_view_wholesale` (`is_verified_dealer` или `is_admin_role`) для B2B-доски и wholesale в списке/деталях; `shipments._visible_to` — admin видит все, остальные (в т.ч. broker) только свои (`watchers`); `LotImportView` — `IsAdminRole`. Профиль отдаёт read-only `is_admin_role`; фронт (`/b2b`, шапка) проверяет его вместо `is_staff`.
- Тесты 403/404 для broker и moderator по каждой точке; мутации (вернуть `is_staff`) красные. Тесты `shipments`, полагавшиеся на голый `is_staff`, переписаны под `make_admin_role`.
- Перечень остальных `is_staff`: `users/*`, `messaging/services.py:31`, `deals`, `local_listings/admin.py` — все безопасны (роль/суперпользователь), без изменений.
- Проверки: backend 526 OK, build и tsc чистые, весь Playwright 105 passed / 7 skipped / 0 failed. `openapi.yaml` — только `is_admin_role`.
- **Ревью безопасности (находки вне задачи, ждут решения владельца, предложено в задачу 2.8 или отдельную):** (1) `vehicles/views.py:12-25` — `VehicleListView/DetailView` AllowAny с `fields='__all__'`: VIN и лоты оптовых машин видны анониму в обход wholesale; (2) `listings/views.py:85` + `serializers.py:34-44` — `ListingCreateView` для любого вошедшего: IDOR по `vehicle`/`calculation`, `channel=wholesale`, `is_express_buyout` уходит в Telegram-канал; (3) `messaging/services.py:66` — диалог по wholesale-объявлению раскрывает его существование. Права модератора на «Черга модерації» перенесены в 4.5b.

---

## Задача 1.2: Роли и права по умолчанию (2026-10-13) — ЗАВЕРШЕНО

- `Role.BROKER`/`MODERATOR`, хелперы, `users/permissions.py`; регистрация игнорирует `role` (201, `buyer`; тесты для admin/dealer/broker/moderator). Миграции: `users/0009` (choices), `0010` (группы «Брокери»/«Модератори»/«Адміністратори», с reverse), `local_listings/0006` (право `moderate_locallisting`).
- Модерация — `has_perm` вместо `is_staff`; 05-Q22 (`seller_type=dealer` только верифицированным); импортные диалоги (06-S9) — только broker/admin.
- `DEFAULT_PERMISSION_CLASSES=IsAuthenticated`, явный `AllowAny`, `cars/` через `core/urls.py` (`git diff cars/` пуст). Тест-аудит `core/tests.py`.
- Админка: `status` заявки дилера только через actions (atomic), действия назначения/снятия ролей (идемпотентны). Журнал аудита (Н-8) — пока logger `audit`.
- Фронт: `/b2b` по `is_staff` (09-S2), типы и метки ролей, нет выбора роли в регистрации. `e2e_seed` + учётки `broker`, `fakeadmin`; `roles.spec.ts`.
- Ревью безопасности: `is_admin_role` = superuser или (`role=admin` и `is_staff`), миграция `users/0011` снимает самозваный admin; `revoke_role` убирает брокера из импортных диалогов; actions ролей только для superuser; модератору закрыты поля объявления (`status`, `promoted_until`…) в форме админки. Тесты: 503 OK (дважды), Playwright 103+ passed; `roles.spec` нашёл баг: вечный спиннер на `/b2b` без доступа — исправлен.
- **Ждёт решения владельца:** модератор/брокер получают `is_staff=True` и проходят проверки `is_staff` в `listings/permissions.py`, `listings/views.py`, `shipments/views.py`, `integrations/views.py` (LotImportView): видят B2B и контейнеры, могут запускать импорт лотов. Вне файлов задачи. Также: права на прокси «Черга модерації» (прокси объявлен в admin.py) и редактирование `is_staff`/`groups` в форме пользователя (сейчас только у superuser).
- Не сделано: проверка границ модератора на `SiteSettings` и `Lead` (моделей нет — 1.12, 2.1). `is_staff` остался в `listings/permissions.py`, `listings/views.py`, `shipments/views.py` (вне «Файлов» задачи).

---

## Задача 0.6b: боевой .env отделён от e2e-стека (2026-10-13) — ЗАВЕРШЕНО

- `docker-compose.e2e.yml`: `env_file: !override [.env.e2e]` (required) у `backend`, `bot`, `celery_worker`, `celery_beat`; у `db` порт наружу снят (`!reset []`), чтобы e2e-стек не конфликтовал с dev-стеком на 5433. `.env.e2e.example` — без ключей (провайдеры пустые, `E2E_SEED_ALLOWED=true`, `E2E_PASSWORD` — заглушка). `.env.e2e` в `.gitignore`.
- Запуск: `docker compose -p autoforyou-e2e --env-file .env.e2e -f docker-compose.yml -f docker-compose.e2e.yml …`. `--env-file` нужен, чтобы подстановка `${VAR}` тоже шла не из боевого `.env`.
- Проверка через `docker compose config`: у четырёх сервисов `TELEGRAM_BOT_TOKEN` пуст при непустом токене в боевом `.env`. Мутация без `!override`: в `backend` 38 переменных вместо 37 (подмешивается ключ только из боевого `.env`) — проверка ловит. Без `.env.e2e` Compose падает с «couldn't find env file … .env.e2e».
- CI, джоба `e2e`: `.env.e2e` из шаблона + случайные значения, переменная `DC` со всеми флагами во всех командах, шаг с фиктивным боевым `.env` и проверкой, что токена нет в контейнерах, `FLUSHALL` перед `e2e_seed`.
- Документы: `docs/TEST_CASES.md` (запуск, нет `.env.e2e`, ловушка 429 и `FLUSHALL`, проверка изоляции), ссылка в `docs/BACKEND_TESTS.md`.
- Тесты: backend 442 OK (код не менялся). **Живой e2e-прогон (владелец разрешил остановить dev-стек, 2026-10-13):** стек с override поднялся; `TELEGRAM_BOT_TOKEN` пуст в `backend` и `celery_worker` при непустом токене в боевом `.env` (`bot` в e2e-стеке не стартует — без токена выходит), `E2E_SEED_ALLOWED=true`. Два прогона подряд, перед каждым `FLUSHALL` + `e2e_seed`: 98 passed, 7 skipped, 0 failed, без 429 (1,3 мин). Затем e2e-стек удалён с томами, dev-стек поднят обратно (данные не трогались). CI-джоба локально не запускалась.
- Замечание: `RuntimeWarning: coroutine 'send_notification.<locals>._send' was never awaited` при прогоне тестов — не ошибка, разбор вписан в `docs/tasks/2.2`.
- **CLAUDE.md обновлён** по «да» владельца (приложения, правила тестов и e2e, ловушки, ссылка на BRIEF §5). RuntimeWarning про `send_notification._send` передан в `docs/tasks/2.2`.

---

## Задача 0.6a: Тестовые фабрики, дубли, документы (2026-10-13) — ЗАВЕРШЕНО (0.6b впереди)

- `tests/factories.py` (`make_user` — по умолчанию подтверждённый, `verified=False` — нет; `make_dealer`, `make_staff`, `auth_client`, `make_region_city`, `make_local_listing`, `make_vehicle`, `make_listing`) и `tests/test_factories.py` (3 теста). Без `factory_boy`. Локальных `_make_user`/`_auth_client` не осталось; две тонкие обёртки с особой сигнатурой: `_make_listing` в `local_listings/tests.py`, `make_listing` в `tests/test_favorites…`.
- Переведены: deals, listings, local_listings, reports, shipments, users, integrations, messaging, `tests/test_e2e.py`, `tests/test_favorites…`.
- Удалённые дубли (удалённый → покрывающий):
  - `test_register_without_consent_blocked` → `users.TestRegistrationConsent.test_register_without_consent_returns_400`;
  - `TestB2BGatingE2E` (8): anon/buyer/dealer/admin на b2b → `users.TestB2BGating`; wholesale-деталь buyer 404, retail, dealer → `listings.TestWholesaleListingDetailGating`; анонимный каталог → `users.TestWholesaleCatalogFilter.test_anonymous_sees_only_retail`;
  - `test_duplicate_application_rejected_with_409` → `users.TestDealerApplyAPI.test_duplicate_pending_returns_409`;
  - `TestRegistryThrottleE2E` (3) → `integrations.TestExpensiveEndpointThrottle.test_registry_throttle_deny_returns_429`, `TestRegistryRequiresAuth` (401 теперь ровно 401, у провайдера `assert_called_once`).
- Тесты: было 448, стало 442 (−13 дублей, +3 фабрики, +4 теста `users.TestUserModel` — прямые проверки менеджера и `__str__`, чтобы не упало покрытие `users/models.py`). Полный прогон до добавления 4 тестов: 438 OK; после — `users` 47 OK.
- Coverage: было TOTAL 8071/578 = 93%, стало 7969/582 = 93%. Единственное падение в продуктовом коде — `users/models.py` (95% → 90%: `create_superuser`, `__str__`); закрыто тестами `TestUserModel`, теперь 99%. Остальные продуктовые файлы без изменений.
- Документы: `docs/BACKEND_TESTS.md`, `docs/TEST_CASES.md` исправлены по 13-Q19/13-C3, числа фактические, добавлены разделы про фабрики, seed, изоляцию, E2E. Docstring `tests/test_e2e.py` исправлен.
- Не сделано (0.6b): правка CLAUDE.md, `docker-compose.e2e.yml`, `.env.e2e.example`, CI, шаг `FLUSHALL`, раздел про e2e-override в документах.
- **CLAUDE.md — ждёт решения владельца.** Текст предложения — в `docs/tasks/0.6-test-factories-docs.md`, раздел «Что добавить в CLAUDE.md». Файл не менялся.
- Playwright, `npm run build`, `tsc` не запускались: фронт и бэкенд-код не менялись.

---

## Разбор плана: порядок, план Б, e2e-окружение (2026-10-13) — docs

- ROADMAP: заявки поднялись: 1.2 → 1.3 → 1.4 → 1.5 → 1.6 → 2.1 → 2.2 → 2.3 → 2.4 → 1.12 → 1.14 → 2.15, остальной этап 1, 7.2, 7.6, 8.9 — после, до деплоя. Зависимости проверены скриптом, нарушений нет.
- Метка [МИНИМУМ] (план Б БП §9): 35 позиций, 61 сессия (с 2.8, 1.8, 1.11 — решение владельца 2026-10-13; было 32 / 55). Колонка «Факт» (0.1–0.5 — по 1 сессии), пункт о ней в `/next`.
- 0.6: добавлено отделение боевого `.env` от e2e-стека и сброс троттлинга (было в 7.3), оценка 1 → 2. 2.5: баг пустых `engine_cc`/`vehicle_year` → 0 (`frontend/app/calculator/page.tsx:65,80`).

---

## Задача 0.5: Базовые Playwright-сценарии (2026-10-13) — ЗАВЕРШЕНО

- Новые спеки: `auth` (23-P1, P3), `private-pages` (P2), `cabinet` (P5), `register-flow` (P6), `cookie-banner` (P7), `mobile` (`@mobile`). Код фронта и бэкенда не менялся, `e2e_seed` не менялся.
- 6 `test.fixme` с ID и задачей: 08-S2, 08-S7 (два), 10-S7 → 1.4; 08-Q6 → 6.2; 08-Q4 → 6.1. Список — в `docs/TEST_CASES.md`. 23-P4 не входит (08-Q1 → 1.4).
- Результат (чистый e2e-стек, `E2E_PASSWORD` случайный): 6 спеков — 50 passed / 7 skipped (fixme; мобильный запускается в двух проектах), 36 с; полный прогон — 98 passed / 7 skipped, 76 с. Django: 448 тестов OK.
- Мутации (код откачен): без `router.push('/me')` в логине — красные «вірний пароль» и «Вийти»; без редиректа в `me/page.tsx` — красный `/me → /login`; без сохранения выбора в `CookieBanner` — красные 4 теста cookie. Тест «невірний пароль» мутацией входа не затрагивается (так и задумано).
- **Ловушка:** на одном стеке много прогонов подряд упираются в троттлинг (429) на логин и расчёт: на мобильных падали «вхід» и «розрахунок». После `redis-cli FLUSHALL` или на свежем стеке (CI) всё зелёное.
- Для 23-P6 после задачи 1.6 сценарий обновить (18+, Turnstile, «Перевірте пошту»).
- Docker: у `backend`/`celery`/`bot` в `docker-compose.yml` `env_file: .env`, то есть e2e-стек без override возьмёт боевой `.env` с токенами. Для локального прогона использован override с `!override` на отдельный env-файл вне репозитория.

---

## Задача 0.4: Инфраструктура e2e (2026-10-13) — ЗАВЕРШЕНО

- Команды `users`: `e2e_seed` (только при `E2E_SEED_ALLOWED=true`, пароль из `E2E_PASSWORD`, идемпотентна) и `e2e_cleanup` (только `@e2e.test` и `[E2E]`). 5 новых тестов в `users/tests_e2e_seed.py`.
- Playwright: проекты `setup`, `chromium`, `firefox` (`@smoke`), `mobile-chrome`, `mobile-safari` (`@mobile`); белый список хоста `E2E_BASE_URL` (обход — `E2E_ALLOW_REMOTE=1`); `auth.setup.ts`, `fixtures.ts`, `auth-smoke.spec.ts`; storageState в `frontend/e2e/.auth/` (в .gitignore).
- CI: джоба `e2e` — seed, три браузера, cleanup `if: always()`. `.dockerignore`: добавлено `!frontend/e2e/fixtures/` (решение владельца), чтобы сид видел фото.
- Маркер `[E2E]` для `LocalListing` лежит в `description` (поля заголовка у модели нет).
- Схема БД не менялась.

---

## Задача 0.3: Фальшиво-зелёные тесты (2026-10-12) — ЗАВЕРШЕНО

- Исправлены 13-Q1…Q9 и 13-Q10 (часть). Новый хелпер `frontend/e2e/helpers/network.ts` (`expectNoRequest`). В `local_listings/tests.py` оба ассерта сужены до 401. Остальные правки — в `pricing`, `deals`, `tests/`.
- В `negative.spec.ts` у «порожня форма» `valueMissing` проверяется только у цены.
- **Находка (код не менялся):** `frontend/app/calculator/page.tsx:65,80` превращает пустые `engine_cc` и `vehicle_year` в 0 через `Number(...)`, `required` не срабатывает. Нужна отдельная задача.
- **Не подтверждено мутацией:** отдельно «только `required`» и «только страничная проверка» у регистрации.

| Тест | Мутация | Красный |
|---|---|---|
| регистрация «без згоди» | снят `required` и страничная проверка | да |
| калькулятор: 5 негативных тестов | `noValidate` на форме | да, все |
| `test_phone_not_in_list_response`, `TestContactEndpoint.test_phone_not_in_list` | `contact_phone` в сериализаторе списка | да, оба |
| `TestAuctionFeeBoundary` | `_lookup_tier`: `>=` -> `>` | да (`bid_max`, `below_min`, `selected_tier_fee_applied`) |
| `test_percent_fee_round_half_up` | `ROUND_HALF_UP` -> `ROUND_HALF_EVEN` | да |
| `test_task_does_not_duplicate_on_rerun` | ранний `return` в `check_saved_searches` | да |

---

## Задача 0.2: Изоляция тестов от внешнего мира (2026-10-12) — ЗАВЕРШЕНО

- `core/settings.py`: один флаг `_TESTING`; блок изоляции в конце — обнуление ключей OpenDataBot/Apify/LiqPay/SMTP/Telegram/Turnstile, locmem-почта, `LocMemCache`, eager-Celery с `memory://` даже при заданном `REDIS_URL`; `TEST_RUNNER`.
- `core/test_runner.py`: `IsolatedDiscoverRunner` — сетевой предохранитель (localhost и хост БД разрешены) и очистка кэша `Update.event_type` aiogram.
- `tests/base.py`: `CleanCacheTestCase`; на нём три класса с seed тарифов (seed в `setUpTestData`) и два класса кэша pricing. Тест 23-D3 в `pricing/tests.py`.
- Тесты 13-S9 переписаны на моки: VIN-отчёт и registry -> 200, Apify без токена -> 400 `{'error': 'VIN обязателен для импорта лота'}`. Колбэк LiqPay в `local_listings` подписан ключом из `override_settings`.
- Новые страховочные тесты: `tests/test_environment.py`.

---

## Задача 0.1: Воспроизводимая локальная среда (2026-10-12) — ЗАВЕРШЕНО

- `.gitattributes`: LF для `*.sh`, `docker/*`, `Dockerfile*`, `nginx/*.conf` (12-Q14). Индекс уже был с LF, CRLF был только в рабочих копиях `docker/entrypoint.sh`, `deploy.sh`, `Dockerfile` — пересозданы через checkout.
- `Dockerfile.backend`: `sed -i 's/\r$//'` перед `chmod`. CI (джоба `backend`): шаг «Shell scripts use LF».
- `scripts/test-backend.ps1` / `.sh`: тесты через `.venv` с пустыми `DATABASE_URL`/`REDIS_URL`. В PowerShell `$env:X=''` удаляет переменную, поэтому `.ps1` запускает Python через `ProcessStartInfo`.
- Удалён локальный `venv/` (12-Q8). README и `docs/BACKEND_TESTS.md` обновлены.
- Проверки: Django 433 теста OK (283 с); `npm run build` и `tsc --noEmit` без ошибок; `pip check` чисто; `git ls-files --eol '*.sh'` везде `i/lf w/lf`.
- Docker на Windows: `down` + `up -d --build` → `backend` и `db` `(healthy)`, `http://localhost` и `/api/v1/listings/` отвечают 200.
- **Первый локальный Playwright: 33 passed, 0 failed, 0 skipped (17,5 с).**
