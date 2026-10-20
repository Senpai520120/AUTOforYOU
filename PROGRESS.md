# PROGRESS.md — Живой журнал прогресса

## Статус: ВОЛНА-1, этап 0 — 0.1–0.6 ✓, 1.2 ✓, 1.2b ✓, 1.3 ✓, 1.4 ✓, 1.5 ✓, 1.6 ✓, 1.12 ✓, 2.1a ✓, 2.1b ✓, 2.2 ✓, 2.3 ✓, 2.4 ✓, 1.14 ✓, 2.15 ✓, 1.1 ✓, 1.7 ✓, 1.9 ✓, 1.10 ✓, 1.11 ✓, 1.8 ✓, 7.2 ✓, 7.6 ✓, 8.9 ✓, 2.14 ✓, дальше 2.5 → 2.6 → … (порядок — ROADMAP.md) | Сервер: Hetzner CX23 (запасной CAX11), Docker Compose | Платежи и C2C-подача выключены флагами до ВОЛНЫ-2

> История до 2026-10-12 (фазы 1–2, C2C-промты, Docker, QA, перенос БД) — `docs/PROGRESS_ARCHIVE.md`.

---

## ⏸ ТОЧКА ОСТАНОВКИ (2026-10-20) — откуда продолжать

- 2026-10-19/20 локальный оркестратор сделал 12 задач (2.1a … 1.11) в ветке `finish-site` (PR #38 в `main`).
- 2026-10-20 облачная сессия: ветка `task-1.8` (PR #39 → `finish-site`), по коммиту на задачу: 1.8, 7.2, 7.6, 8.9, 2.14 (далее по плану 2.5).
- **Следующая задача по критическому пути: 2.5** (корректность калькулятора), затем 2.6 → 2.7 → … (ROADMAP.md, «Порядок выполнения»).
- Перед продолжением: проверить CI PR #39; локальные `.env` и `.env.e2e` — задать настоящий `SECRET_KEY` (с 7.2 заглушки из шаблонов не стартуют) и переменные из `.env.e2e.example` (`THROTTLE_*`, `PRIVATE_MEDIA_USE_X_ACCEL=true`); для Playwright экспортировать `E2E_PASSWORD`.
- Решения владельца, накопленные за прогон, — в разделах задач ниже («Для владельца») и в `docs/LAUNCH_CHECKLIST.md`.

---

## Задача 2.14: источник визита first-touch у регистрации и объявления (2026-10-20, облачная сессия) — ЗАВЕРШЕНО

- `core/attribution.py: clean_attribution` — одна функция на заявку (2.1, `leads.validators` её реэкспортирует), регистрацию и объявление: UTM по whitelist и шаблону, реферер — только `http(s)://host[:port]` (без пути, query, fragment и логина/пароля), страница — только путь своего сайта; управляющие символы (`\x00` и т.п., на PostgreSQL давали бы 500) → пусто; никогда не бросает.
- Поля (`editable=False`): `CustomUser.first_touch_utm/referrer/entry_url` (миграция users 0018 + право `users.view_attribution`, data-часть выдаёт его группе «Адміністратори»), `LocalListing.utm/referrer/entry_page_url` (миграция local_listings 0008). Пишутся только при регистрации и создании объявления (`attribution` — write-only JSON, мусор/`null` тихо отбрасываются), PATCH профиля и редактирование объявления их не меняют.
- Админка: блок «Джерело візиту» только для чтения и только с правом (суперпользователь, «Адміністратори»); модератор (в т.ч. «Черга модерації») и брокер не видят. Выгрузка «Мої дані» содержит свой источник; обезличивание очищает `first_touch_*` и `referrer`/`entry_page_url` объявлений (UTM без ПДн остаётся).
- Фронт: `register/page.tsx` отправляет `attribution` из `lib/attribution.ts`, пустой — не отправляется. Форму объявления подключает 4.2.
- Проверки: бэкенд SQLite 1647 OK (skipped=2); PostgreSQL (tests, users, local_listings, leads) 1206 OK, в т.ч. NUL-тест; `openapi.yaml` перегенерирован против PostgreSQL; ruff, tsc, lint (0 ошибок), build OK. Мутационная проверка: 21 мутация, поймано 20; выжила одна избыточная (`write_only` у `attribution` в объявлении — ответ создания и так его не содержит). E2E `attribution.spec.ts` 3/3 + `register-flow` 2/2 (локальный стек): UTM с калькулятора → тело регистрации → sessionStorage, не cookie → своя выгрузка; мусор в sessionStorage не мешает; без UTM поле не уходит. Ревью `security-reviewer`: критичного нет; 3 «важно» исправлены (NUL → 500 на PostgreSQL; `attribution: null` → 400; тест модератора/брокера без кодов ответа) и 2 «желательно» (логин/пароль в реферере; доступ admin-роли только через право).
- Для владельца: право «Може бачити джерело візиту» — только нужным людям; юрист — подтвердить хранение в `sessionStorage` без согласия на cookie (строка в политике есть с 1.12). В задаче упоминается `GET /auth/me/` — такого маршрута нет, проверен `GET /auth/profile/`.

---

## Задача 8.9: учёт упавших Celery-задач (2026-10-20, облачная сессия) — ЗАВЕРШЕНО

- Приложение `task_ledger`: модель `FailedTask` (миграция 0001, только создание таблицы; индекс `task_name, failed_at`), обработчик `task_failure` (подключается в `AppConfig.ready`): запись (имя, id, повторы, класс ошибки, ошибка после `scrub`, аргументы в безопасном виде, очередь) и `capture_message('Celery task failed: …')` с `extra` без аргументов и текста ошибки. Обработчик ничего не бросает: ошибки записи, мониторинга и даже странного `sender` только логируются (без аргументов).
- `sanitize.safe_repr`: int/bool/float/None как есть; короткая строка без пробелов (id, код заявки) — после `scrub`; длинная (>`FAILED_TASK_ARG_MAX_LEN`, 64) или с пробелами (тексты писем и сообщений, имена) — только `<str:длина>`; словари, списки, объекты — `<dict:3>`.
- `core/tasks.py: ResilientTask` (`autoretry_for` OSError/ConnectionError, backoff + jitter, `max_retries`/`acks_late` из `RESILIENT_TASK_MAX_RETRIES` (3) / `RESILIENT_TASK_ACKS_LATE` (true) — в файле задачи имена `CELERY_TASK_*`, но с префиксом `CELERY_` Celery применил бы их ко всем задачам, см. ревью). Подключён к `check_saved_searches`; четыре задачи со своими повторами не менялись, их окончательные неудачи тоже попадают в журнал. Ежедневная чистка `purge_failed_tasks` (04:10, `FAILED_TASK_RETENTION_DAYS`, 90). Админка «Невдалі завдання»: только просмотр, только admin-роль (модератор и брокер — 403), в списке нет аргументов.
- Проверки: бэкенд SQLite 1629 OK (skipped=2); PostgreSQL (task_ledger, tests) 550 OK; `openapi.yaml` не изменился; ruff чисто. Мутационная проверка: 24 мутации, все пойманы. Ловушка eager-режима: вложенные eager-повторы Celery 5 не эмулируют воркер, поэтому повторы проверены по частям (последняя попытка → одна запись; промежуточная → `retry`, записи нет). Ревью `security-reviewer`: **1 «критично» исправлено** (глобальный `task_acks_late` через префикс `CELERY_`), 2 «важно» (тексты сообщений в аргументах; тест админки без проверки значений) и 2 «желательно» (защита всего обработчика, тест без мока мониторинга) исправлены.
- Для владельца: раз в неделю смотреть «Невдалі завдання» в админке; подтвердить `RESILIENT_TASK_ACKS_LATE=true` (при падении воркера задача повторится — возможен дубль алерта сохранённого поиска) и срок хранения 90 дней. Действие «повторить» — задача 9.35.

---

## Задача 7.6: мониторинг ошибок (2026-10-20, облачная сессия) — ЗАВЕРШЕНО

- `core/monitoring.py` (адаптер, протокол Sentry: sentry.io или GlitchTip): `init_monitoring(component)` — пустой `SENTRY_DSN` → выключен без импорта SDK, невалидный → предупреждение без DSN, повтор — no-op, в тестах `.env`-DSN игнорируется; `send_default_pii=False`, без локальных переменных и тела запроса, интеграции Django/Celery/logging (ERROR — события, WARNING — крошки). `before_send` (и `before_send_transaction`): `scrub` для сообщений, исключений, контекста кадров, extra/tags/contexts, крошек, спанов; без cookies/data/env, заголовков Authorization/Cookie/X-CSRFToken/Referer/XFF, query везде (в т.ч. repr `WSGIRequest` из django.request), `user` — только `id`. `capture_message` — no-op при выключенном.
- Инициализация: web — `core/wsgi.py`/`asgi.py` после `get_wsgi_application()` (не в settings: команды и тесты не поднимают SDK); Celery — сигналы `worker_process_init`, `beat_init` (`core/celery.py`); бот — `run_bot`. `sentry-sdk[django,celery]==2.70.0`.
- `POST /api/v1/monitoring/client-errors/`: AllowAny, без аутентификации и CSRF, throttle `client_errors` (`THROTTLE_CLIENT_ERRORS_RATE`, 20/hour на IP), тело до 4 КБ (заголовок и поток), сериализатор (message ≤500, digest, path без query, component); `frontend-ssr` принимается только изнутри сети (без X-Forwarded-For). Ответ 204 и при выключенном мониторинге. `manage.py monitoring_test`. `core` добавлен в `INSTALLED_APPS` только ради команды (моделей нет).
- Фронт: `lib/reportError.ts` (fetch keepalive, без cookie, стека и query), `error.tsx` (отчёт, `Link` «На головну»), `global-error.tsx` (отчёт, inline-стили вместо недоступного `globals.css`), `instrumentation.ts` `onRequestError` → `INTERNAL_API_URL` (таймаут 3 с). DSN в бандле нет (проверено grep по `.next/static`).
- Проверки: бэкенд SQLite 1607 OK (skipped=2); PostgreSQL (tests, core, telegram_bot) 581 OK; `openapi.yaml` перегенерирован против PostgreSQL (+ client-errors); ruff, tsc, lint (0 ошибок), build OK. **Живая проверка**: локальный приёмник Sentry-envelope + настоящий SDK — 3 события (log.error, logger.exception, capture_message) дошли, в них нет email, телефонов, токенов, паролей из аргументов, `user` пуст. Настоящий sentry.io/GlitchTip не подключался (нет аккаунта). Мутационная проверка: 32 мутации, все пойманы. E2E `error-monitoring.spec.ts`: отчёт со страницы сайта → 204, мусор → 400, GET → 405, поток → 429 (локальный стек); сценарий «ошибка рендера → error.tsx шлёт отчёт» — `test.fixme` → 7.6b (в e2e-стеке нет способа вызвать ошибку рендера без тестовой страницы). Ревью `security-reviewer`: критичного нет; 2 «важно» исправлены (query через repr запроса в extra/крошках; транзакции мимо фильтра), желательные 3, 5, 6, 8 исправлены.
- Для владельца:
  - Создать проект в sentry.io (бесплатно) или GlitchTip, `SENTRY_DSN` в `.env`, затем `docker compose exec backend python manage.py monitoring_test`; включить алерты и Data Scrubber в проекте.
  - Реестра статусов интеграций (3.1) ещё нет — статус мониторинга в админке появится с ним.
  - Остаточный риск (ревью, желательно): все SSR-отчёты Next идут с одного IP контейнера и делят лимит 20/час; общего дневного потолка событий нет — квоту Sentry можно выжечь ротацией IP. Решить при 7.5 (отдельный лимит/секрет для SSR, лимит в самом Sentry).

---

## Задача 7.2: прод-настройки Django, хранилища, логи без ПДн (2026-10-20, облачная сессия) — ЗАВЕРШЕНО

- `core/secret_key.py`: фиксированного ключа больше нет. При `DEBUG=true` без ключа он создаётся один раз в `.dev_secret_key` (0600, в `.gitignore`/`.dockerignore`; каталог только для чтения — ключ в памяти с предупреждением), в тестах — случайный. При `DEBUG=false` пустой, короче 50 символов или с маркерами заглушек (`REPLACE`, `local-docker-dev`, `django-insecure`, `not-for-production`, `e2e-only`, `your-`) — `ImproperlyConfigured`. `DEBUG=true` с публичным хостом в `ALLOWED_HOSTS`, `SITE_URL`, `CSRF_TRUSTED_ORIGINS` или `CORS_ALLOWED_ORIGINS` — ошибка старта (обход `ALLOW_DEBUG_ON_PUBLIC_HOST=true`); `docker/entrypoint.sh` не запускает gunicorn с `DEBUG=true`. Пустой `ALLOWED_HOSTS` при `DEBUG=false` — ошибка старта (01-Q9). Celery eager — флаг `CELERY_EAGER` (01-C13).
- `core/storage_settings.py: build_storage_settings` → `STORAGES` (01-C1): медиа в S3/R2, статика локальная, `MEDIA_ROOT` всегда; `MEDIA_URL` — `S3_CUSTOM_DOMAIN`, для R2 без домена — подписанные URL storage, шаблон amazonaws только для AWS (12-C6). Приватные фото трекинга: подпись всегда (без CDN-домена), отдельный bucket `PRIVATE_S3_BUCKET_NAME`, предупреждение при CDN-домене без него.
- `core/logging_filters.py`: `scrub` (email, телефоны UA/международные и `%2B`, секреты в query/JSON, Cookie/Authorization/Bearer, голые JWT, имена в JSON) и `PiiScrubFilter` (форматирует запись, маскирует и traceback), `RequestPathFilter` (django.request/django.server без query и без объекта запроса). `LOGGING`: stdout, `LOG_LEVEL`, фильтры на handler'е; Celery не перехватывает корневой логгер. gunicorn access-лог `%(U)s` без query и IP; nginx `log_format main_anon` (`$uri`, IP с обнулённым октетом); compose `x-logging` (`LOG_MAX_SIZE`, `LOG_MAX_FILES`) у всех сервисов. `integrations/tasks.py` без `telegram_id` в логе. Дефолты `SITE_URL=http://localhost`, `DEFAULT_FROM_EMAIL=noreply@localhost` (+ предупреждение на проде). `flushexpiredtokens` в расписании уже был (1.7), покрыт тестом.
- Попутно: Swagger/Redoc/схема только admin-роли (`API_DOCS_PUBLIC`, 01-S15, строки в матрице 1.11); `next/image` — только хост медиа бэкенда и `NEXT_PUBLIC_IMAGE_HOSTS` (build-arg), без `*.amazonaws.com`, `*.cloudfront.net`, хостов аукционов (08-C8, 08-S10).
- Тесты: `tests/test_prod_settings.py` (38; старт Django в subprocess, хранилища без сети, фильтры, entrypoint) — у `core` уже есть модуль `core/tests.py`, поэтому не `core/tests/`. `check --deploy` (23-D106) — `skip` до 7.1. E2E `image-hosts.spec.ts`: обход (чужие хосты → 400) зелёный; успех — `test.fixme` → 7.5: в e2e-стеке медиа на localhost, а Next 16 запрещает оптимизатору локальные IP независимо от списка (так было и до задачи).
- Проверки: бэкенд SQLite 1582 OK (skipped=2); PostgreSQL (tests, core, integrations, users) 945 OK; `openapi.yaml` не изменился; ruff чисто; tsc/lint/build OK; `nginx -t` в `nginx:alpine` OK и формат лога проверен запросом (`127.0.0.0`, путь без query); `docker compose config` — logging у всех сервисов. Мутационная проверка: 28 мутаций, все пойманы. S3/R2 вживую не проверены (нет бакета; MinIO в облаке не поднимал). Ревью `security-reviewer`: критичного нет; 4 «важно» исправлены (обход проверки DEBUG через Host: localhost; Cookie/sessionid/JWT мимо `scrub`; Celery перехватывал root-логгер без фильтра; приватные файлы в публичном bucket), 3 «желательно» исправлены (маркеры e2e-ключа, `%2B`-телефон и имена в JSON, тест `RequestPathFilter`); `error_log` nginx с IP — описан в LAUNCH_CHECKLIST.
- Для владельца:
  - **Локальный `.env` (docker) со старым ключом `local-docker-dev-…-REPLACE…` больше не стартует** — задать сгенерированный `SECRET_KEY`; то же для `.env.e2e` (в шаблоне ключ теперь пустой, CI генерирует свой).
  - При S3/R2 с публичным доменом — задать `PRIVATE_S3_BUCKET_NAME` (отдельный бакет без публичного доступа) и `NEXT_PUBLIC_IMAGE_HOSTS`. Если фото лотов не переносятся (`LOT_PHOTO_ALLOWED_HOSTS` пуст), их CDN-хосты нужно внести в `NEXT_PUBLIC_IMAGE_HOSTS`, иначе фото лотов в каталоге не покажутся.
  - Swagger `/api/docs/` теперь только для админа; открыть всем — `API_DOCS_PUBLIC=true`.

---

## Задача 1.8: профиль, выгрузка данных, удаление аккаунта с обезличиванием (2026-10-20, облачная сессия) — ЗАВЕРШЕНО

- Модель: `CustomUser.deletion_scheduled_at`, `deleted_at` (миграция users 0017, только добавление полей).
- API: `DELETE /auth/profile/` `{password}` → 202 `deletion_scheduled_for` (неверный/пустой пароль 400, суперпользователь 400, лимит `password_reset`); сразу снимаются активные и pending объявления (`hidden`), `revoke_all_sessions`, cookie очищены, письмо «Видалення акаунту заплановано» со ссылкой на `/me/data`. `POST /auth/profile/cancel-deletion/` (объявления остаются снятыми). `GET /auth/me/export/` — JSON-вложение `autoforyou-data-<дата>.json`, throttle `data_export` (`THROTTLE_DATA_EXPORT_RATE`, 5/day), `no-store`. В профиле поле `deletion_scheduled_for`; телефон только `+380XXXXXXXXX` (пустой разрешён).
- `users/services.py: anonymize_user` (один сервис для Celery и админки): email → случайный `deleted-<uuid>@deleted.invalid`, имя/фамилия/телефон/Telegram стёрты, роль buyer, без staff/групп, неактивен, пароль непригоден, `deleted_at`; удалены партнёры, сохранённые поиски, избранное, уведомления, токены Telegram, заявки дилера; объявления → `hidden` без телефона, описания и фото (файлы удаляются после коммита); расчёты и контейнеры отвязаны; импортные диалоги бывшего брокера переданы другому брокеру/админу; `ConsentRecord` не удаляются, `user` обнуляется явным UPDATE в обход неизменяемого менеджера. Сделки, отзывы, переписка, жалобы, платежи остаются — вторая сторона видит «Користувач видалений». `leads/services.py: anonymize_user_leads` — имя «Користувач видалений», телефон/email/ник/комментарий стёрты, `user=None`; `public_id`, партнёрские поля, атрибуция, журналы, UTM остаются. Письмо «Акаунт видалено» на старый адрес (ошибка SMTP не мешает).
- Celery beat `users.tasks.anonymize_due_accounts` (03:45): период — `SiteSettings.account_deletion_grace_days`; под блокировкой строки повторно проверяется, что удаление не отменено.
- `users/export.py: build_user_export` — разделы profile, consents, trusted_shops, dealer_applications, calculations, watched_shipments, leads, local_listings, imported_listings, favorites, saved_searches, notifications, conversations, deals, reviews_written/received, reports_filed, payments; контрагенты — только `public_display_name`, без `liqpay_raw` и служебных полей брокера.
- Админка пользователей: удаление запрещено (`has_delete_permission=False`, каскад 06-S11 невозможен), действие «Анонімізувати» (только суперпользователь, себя и других суперпользователей пропускает), фильтр «видалений».
- Фронт: `/me/profile` (правка имени, фамилии, телефона, ошибки полей), `/me/data` («Завантажити мої дані» через blob; удаление с паролем и «Я розумію, що це незворотно»; «Скасувати видалення»), баннер «Акаунт буде видалено <дата>» и пункты «Профіль», «Мої дані» в `/me`, одноразовое сообщение на главной после удаления. Ссылка в `privacy` §6 уже была (1.12).
- Проверки: бэкенд SQLite 1528 OK (skipped=1); PostgreSQL 16 — users, leads, tests, deals, messaging, local_listings, site_settings: 1206 OK; ruff чисто; `tsc`, `lint` (0 ошибок; 1 новое предупреждение `set-state-in-effect` в `FlashMessage`, как у соседних компонентов), `build` OK; `openapi.yaml` перегенерирован против PostgreSQL. Мутационная проверка: 31 мутация бэкенда и 1 мутация фронта (баннер) — все пойманы. E2E `account-data.spec.ts` 5/5 (chromium) — **не в docker compose**: в облаке собрать образы нельзя (прокси с собственным CA), прогон шёл на локальном стеке (runserver + `next start` + Node-прокси вместо nginx, PostgreSQL); прочие e2e-спеки не перепрогонялись. Ревью безопасности (инструкция `security-reviewer` через general-purpose агента): критичного нет; 2 «важно» исправлены (гонка отмены с задачей; занятие подменного email регистрацией срывало обезличивание) и 3 «желательно» (проверка суперпользователя под блокировкой, осмысленный тест матрицы cancel-deletion, тест пропуска второго суперпользователя).
- Для владельца:
  - Удаление сделок/платежей по сроку хранения не сделано: `data_retention_years` пуст до ответа бухгалтера, удаление затрагивает историю второй стороны (LAUNCH_CHECKLIST). Тогда — management-команда с dry-run.
  - Дата удаления считается от текущего `account_deletion_grace_days`: уменьшение периода в админке сдвинет уже запланированные удаления раньше даты из письма. Оставить так или фиксировать срок при запросе?
  - После обезличивания остаются (решение юриста/1.12): тексты сообщений удалённого, его отзывы и жалобы, заметки брокера в истории заявки, уведомления у других с display-именем, уже отправленные сообщения журнала в группе партнёра, `django_admin_log` с прежним email, объявления-лоты `listings.Listing` брокера (не снимаются). `ConsentRecord` после отвязки ни к кому не привязан — согласовать с юристом.
  - Суперпользователь удаляется только вручную (API и админка отказывают). В выгрузку попадает `review_notes` заявки дилера (пользователь и так видит его в статусе заявки).

---

## Задача 1.11: общий набор тестов авторизации (2026-10-20) — ЗАВЕРШЕНО

- `tests/test_authz_matrix.py`: матрица по всем API-эндпоинтам (аноним 401, чужой, владелец, роли, cookie без CSRF → 403 с положительным контролем; изоляция списков; снимок состояния после 403/404), тест полноты по `get_resolver()` (ловит новый view, пропущенный метод и безымянный маршрут под `api/`), `AdminRolesTests`, `InfraExposureTests`, `ErrorTextsNotLeakedTests`. ~350 тестов за ~10 с; мутационная проверка в нескольких приложениях.
- Исправлено по находкам: сделки (confirm/cancel/review) и диалоги — посторонний получает 404 вместо 400/403; общий текст ошибки вместо `str(exc)` в `pricing`, `integrations`, `payments` (LiqPay); миграция `users/0016` — права «Модератори»/«Адміністратори» на очередь модерации (`PendingLocalListingProxy`, без delete).
- `frontend/e2e/authz.spec.ts` 23/23; `docs/BACKEND_TESTS.md` — раздел «Безопасность, бриф §3» (36 пунктов, часть «ждёт задачу N»). Бэкенд 1471 тест (после обновления 5 ожиданий 403→404 в `users/tests.py` зелёный), Postgres-прогон матрицы зелёный. Ревью `security-reviewer`: 4 «важно» + 4 «желательно» исправлены.
- Для владельца: модератор через API может править и удалять чужое объявление (в админке delete нет) — оставить так? `pricing-rates` публичен (ждёт 2.6, Q8), сумма платежа от клиента (ждёт 4.1), создание `Listing` любым вошедшим (ждёт 2.8).

---

## Задача 1.10: безопасные загрузки (2026-10-20, Opus) — ЗАВЕРШЕНО

- `core/uploads.py`: тип по содержимому (Pillow, `formats=`), лимиты байт (до чтения) и пикселей (`UPLOAD_IMAGE_MAX_PIXELS` 25M, `MAX_IMAGE_PIXELS` при импорте), поворот по EXIF, пересохранение без EXIF/GPS/ICC/XMP/PNG-текста, имя `uuid.ext`. `SanitizedImageField` на фото C2C, авто и трекинга (очистка в `FieldFile.save`: API, админка, `advance_status`, `upload_lot_photos`, `e2e_seed`). Миграции `local_listings/0007`, `vehicles/0004`, `shipments/0002` — только смена класса поля.
- Загрузка фото C2C: throttle `THROTTLE_UPLOADS_RATE` (30/час), всё или ничего, файлы удаляются при откате.
- `upload_lot_photos`: allowlist `LOT_PHOTO_ALLOWED_HOSTS`, только https, проверка IP после резолва (private/loopback/link-local/CGNAT/reserved), до 3 редиректов, общий дедлайн 30 с, обрыв потока по лимиту. Остаточный риск: DNS-rebinding между проверкой и соединением (ограничен allowlist и https).
- Фото трекинга — приватное хранилище `PRIVATE_MEDIA_ROOT` (S3: `private/`, подписанные ссылки `PRIVATE_MEDIA_URL_EXPIRE` 300 с), отдача только `GET /api/v1/shipments/<pk>/events/<id>/photo/` (watcher, admin-роль, `view_trackingevent`) через `FileResponse` или `X-Accel-Redirect`. nginx: `nosniff`, `attachment` для не-картинок, `/media/tracking_photos/` 404, internal `/protected-media/`, том `private_media`.
- Команда `sanitize_existing_images` (по умолчанию план; `--apply`, `--delete-invalid`), перенос старых фото трекинга в приватное хранилище.
- Проверки: бэкенд 1110 OK, Postgres 591 OK, e2e `uploads`+`cabinet` 16 passed (X-Accel на реальном файле). Ревью `security-reviewer`: 1 «важно» + 6 «желательно» исправлены.
- Для владельца: заполнить `LOT_PHOTO_ALLOWED_HOSTS` (не `*.amazonaws.com`/`*.cloudfront.net`), на сервере запустить `sanitize_existing_images` (сначала без флагов) и включить `PRIVATE_MEDIA_USE_X_ACCEL`; в локальном `.env.e2e` — `PRIVATE_MEDIA_USE_X_ACCEL=true`, `THROTTLE_UPLOADS_RATE`. Хардкод «15» и «до 8 МБ» в `PhotoUploadBlock` — задача 4.2.

---

## Задача 1.9: ПДн в сериализаторах (2026-10-20) — ЗАВЕРШЕНО

- `users/display.py::public_display_name` — «Ім'я П.» (первое слово имени + инициал первого слова фамилии), «Користувач» при пустом имени, «Користувач видалений» по `deleted_at` (появится в 1.8). Email и его локальная часть контрагентам не отдаются.
- `deals`: `DealUserSerializer` `{id, display_name}`, `ReviewSerializer.author_name`, `listing-buyers` — владелец или admin-роль, остальным 404 (как несуществующий id); `SellerRatingView` 404 без активных объявлений; тексты уведомлений через хелпер. `messaging`: `ParticipantSerializer` `{id, display_name}`, `sender_name` и Telegram-подписи через хелпер. `local_listings`: `owner_name` через хелпер, поле `is_owner` (на фронте берётся авторизованным запросом из браузера — SSR-кэш 60 с без пользовательских данных).
- Фронт: типы и страницы `/me/deals`, `/me/local-listings`, `/me/messages` без email. `@extend_schema` для `listing-buyers`, `/deals/`, `conversations`; openapi через Postgres.
- Проверки: бэкенд 1024 OK; e2e `pii-leaks.spec.ts` (новый) и полный chromium-прогон зелёные. Ревью `security-reviewer`: критичного и важного нет, 5 «желательно» сделаны.
- Для владельца: нужен ли брокеру доступ к `listing-buyers` (сейчас нет). В 1.8 проставлять `deleted_at` при обезличивании.

---

## Задача 1.7: сброс и смена пароля, выход со всех устройств, бан (2026-10-20) — ЗАВЕРШЕНО

- API: `password-reset/` (throttle → honeypot и капча → без обращения к БД, письмо и поиск пользователя — в Celery-задаче; ответ всегда 200 одним текстом), `password-reset/confirm/` (uid + токен Django, `validate_password`), `password-change/` (текущий пароль, throttle), `token/logout-all/`.
- Сессии: `CustomUser.session_version` (миграция users 0015) + claim `sv` во всех токенах (`users/jwt.py`: `VersionedRefreshToken`, свои `TokenObtainPairSerializer`/`TokenRefreshSerializer`); `revoke_all_sessions` под `select_for_update` увеличивает версию и кладёт refresh в blacklist; `CookieJWTAuthentication` и refresh сверяют `sv` (токены без `sv` = версия 0). После смены пароля текущему устройству выдаются новые токены.
- Бан: `ban_user`/`unban_user` (отзыв сессий; суперпользователь не банится), в том числе из `reports/admin.py`; `is_banned` в админке только чтение, деактивация `is_active` отзывает сессии. Beat `users.tasks.flush_expired_tokens` (03:30).
- Фронт: «Забули пароль?», `/password-reset`, `/password-reset/confirm` (токен убирается из адреса, `Referrer-Policy: no-referrer`), `/me/security`, `logoutAll`. E2E-стек: Mailpit для писем.
- Проверки: бэкенд 996 OK; e2e `password`, `auth-cookie`, `register`, `private-pages` 57 passed. Ревью `security-reviewer`: 3 «важно» + 4 «желательно» исправлены.
- Для владельца: SMTP и `SITE_URL` (LAUNCH_CHECKLIST 2.4); локальный `.env.e2e` — добавить `THROTTLE_PASSWORD_RESET_RATE=2000/hour` (есть в `.env.e2e.example`); токены, выданные до деплоя 1.7, действуют до первого отзыва сессий.

---

## Задача 1.1: утечки секретов (2026-10-20) — ЗАВЕРШЕНО (код), действия владельца — ниже

- `integrations/providers.py`: Opendatabot, NHTSA, Apify при ошибке отдают общий текст и `error='service_unavailable'`, детали — в лог с маской `apikey=***`. `integrations/views.py`: ошибка провайдера → 503 без сохранения `RegistryReport`; кэш не отдаёт старые записи с `error` (`.exclude(payload__has_key='error')`).
- Ручная команда `purge_registry_errors` (по умолчанию dry-run, удаление только с `--confirm`) вместо data-миграции: необратимое удаление — решение владельца.
- `.gitleaks.toml` (allowlist только для тестовых фиктивных значений, docs и `*.example` сканируются), `.pre-commit-config.yaml` (gitleaks v8.21.2), CI-job `secrets-scan` (`gitleaks dir . --redact`). `.gitignore`: `.env.*` кроме `*.example`, `.claude/settings.local.json`, дампы `*.sql`/`*.dump`, ключи `*.pem`/`*.key`/`id_rsa*`; `.dockerignore`: `.claude/`. `LOGGING`: `httpx`/`httpcore` на WARNING. README — установка pre-commit.
- Проверки: бэкенд 945 OK; тесты на настоящий `httpx.HTTPStatusError` с ключом в URL. Ревью `security-reviewer`: 3 «важно» + 3 «желательно» исправлены. Gitleaks локально не запускался (нет образа) — проверить `pre-commit run --all-files` и первый прогон CI.
- Владелец: токен Telegram-бота был в истории публичного репозитория (`.claude/settings.local.json`, коммит a47169c; историю по Q1 не чистим). Владелец сообщил 2026-10-19, что токены перевыпущены — убедиться, что отозван именно токен бота AUTO_F_Y. Перевыпустить `OPENDATABOT_API_KEY`, если ключ работал в бою; `pre-commit install`; запустить `purge_registry_errors` (dry-run, затем `--confirm`); закрепить образ gitleaks по digest в CI.

---

## Задача 2.15: журнал заявок для партнёра, квалификация, атрибуция, CSV, воронка (2026-10-20) — ЗАВЕРШЕНО

- `Lead`: квалификация (`qualification`, четыре `q_*`), окно атрибуции `attribution_until` (`add_months`, последний день месяца), `journal_message_id`/`journal_sent_at`/`journal_sending_at`. Новые модели: `LeadJournalSettings` (порог 3 из 4, 8000 USD, 12 мес., `journal_retry_minutes`; меняет только superuser), `LeadPartnerStatusChange` и `LeadExportLog` — только добавление (`AppendOnlyQuerySet`, запрет save/delete). Миграции leads 0006–0008.
- Журнал в группу партнёра (`LEAD_JOURNAL_CHAT_ID`): белый список (AFY-ID, авто только из лота/расчёта, бюджет, город, время UTC), в свободных полях телефон/@ник/email → «не вказано»; `send_journal_task` с `self.retry` без ПДн, beat-задача `resend_journal` (каждые 5 мин, пакет 50, до 7 дней); отправка вне транзакции с меткой `journal_sending_at`, без дублей.
- API брокера: `POST /broker/leads/{id}/qualification/`, `GET /broker/leads/export.csv` (фильтры статус/период, потоковый, `csv_safe` с `lstrip`, throttle `lead_export` общий с админкой, аудит без поискового запроса). Админка: колонки/фильтры квалификации и статуса партнёра, CSV, воронка `/admin/leads/lead/funnel/` (право `view_funnel` у «Адміністратори»); правки через сервисы с проверкой владельца (брокер не меняет чужую заявку и в админке).
- Фронт: блок «Кваліфікація» в `BrokerLeadCard`, «Завантажити CSV» в `BrokerLeadList`. E2E `lead-journal.spec.ts` 3/3, `broker`+`lead` 41/41.
- Проверки: бэкенд 936 OK, ruff чисто. Ревью `security-reviewer`: 3 «важно» + 5 «желательно» исправлены. Квалификация и статус партнёра — POST (в задаче PATCH), как соседние эндпоинты 2.4.
- Для владельца: подтвердить пороги (3 из 4, 8000 USD, 12 мес.) с партнёром и договором; заполнить `LEAD_JOURNAL_CHAT_ID`; юрист — срок хранения `LeadExportLog` и окно атрибуции. В 1.8 не обезличивать `public_id`, `partner_name`, `journal_message_id`, `partner_status`, журналы и `attribution_until`.

---

## Задача 1.14: журнал согласий, версия документов, 18+, настройки cookie (2026-10-20) — ЗАВЕРШЕНО

- `ConsentRecord` (`users/models.py`, миграции users 0013–0014): тип документа (terms, privacy, dealer_processing, lead_processing, age_18, partner_transfer), способ, версия из `SiteSettings`, `partner_name`, `lead_public_id`; без IP, user-agent и текста чекбокса. Неизменяемость: `save()` повторно, `obj.delete()`, `QuerySet.update/bulk_update/delete` бросают `ImmutableError`; `SET_NULL` при удалении пользователя/заявки работает. Админка только чтение, только admin-роль.
- `users/consents.py::record_consents` в одной транзакции с регистрацией (terms, privacy, age_18), заявкой дилера (dealer_processing, age_18) и `create_lead` (lead_processing, partner_transfer). Поле 1.6 `is_adult` переименовано в `confirmed_age_18`; 18+ проверяется сервером. Миграция 0014 переносит согласия существующих заявок (идемпотентна).
- Фронт: `cookie_consent` — JSON `{level, version, ts}` (старые строки читаются), повторный запрос при новой версии и `reconsent_required`, `hasAnalyticsConsent()` false до повторного согласия; ссылка «Налаштування cookie» в футере; чекбокс 18+ на заявке дилера.
- `GET /api/v1/site-settings/` без DRF-throttle (кэш 5 мин, без ПДн; баннер запрашивает его на каждой странице). E2E-стек: лимиты nginx и DRF подняты только в `docker-compose.e2e.yml`/`.env.e2e.example` (боевые не менялись); `broker.spec.ts` и `auth-cookie.spec.ts` не зависят от порядка прогона.
- Проверки: бэкенд 888 OK, `consent.spec.ts` 19/19, связанные спеки зелёные на чистом стеке. Ревью `security-reviewer`: 4 «важно» + 4 «желательно» исправлены.
- Для владельца: юрист — формулировка и порог 18+, срок хранения журнала; заполнить `legal_docs_version` до запуска; выгрузка `ConsentRecord` — в задаче 1.8. `broker.spec.ts` требует чистого e2e-стека.

---

## Задача 2.4: кабинет брокера (2026-10-20) — ЗАВЕРШЕНО

- API `/api/v1/broker/leads/` (`leads/broker_urls.py`): список (фильтры `status`, `source`, `assigned_to=me`, `utm_source`, `search` по имени/телефону, `ordering`, пагинация 20, `new_count`), карточка `<id>/`, `<id>/status/`, `<id>/take/`, `<id>/partner-status/`. Доступ `IsBrokerOrAdmin`: аноним 401, buyer/dealer/moderator (даже staff) 403.
- Сервис: `take_lead` (select_for_update, чужая 409, повтор идемпотентен), `broker_change_status` (переход из `new` назначает брокера), `set_partner_status` (журнал `partner: old → new`), `_check_owner` — чужую взятую заявку меняет только назначенный брокер или admin-роль (решение при реализации, записано в файле задачи; можно ослабить). `force` через API недоступен.
- Сериализаторы: в списке минимум полей; `assigned_to`/`history[].changed_by` — `{id, name, email?}`, email только себе и admin-роли.
- Фронт: `/broker/leads`, `/broker/leads/[id]` (`BrokerLeadList`, `BrokerLeadCard`, `LeadStatusBadge`, `AccessDenied`), поиск не попадает в URL; ссылка «Заявки» в шапке (десктоп) и в `/me` по роли (косметика, доступ решает API). Telegram-кнопка и in-app ссылка ведут в кабинет.
- Проверки: бэкенд 860 OK, `tests_broker.py` 43; `broker.spec.ts` 16 passed (chromium, mobile-chrome, mobile-safari), XSS-нагрузки из `e2e_seed` выводятся текстом; openapi через Postgres. Ревью `security-reviewer`: 2 «важно» + 4 «желательно» исправлены.
- Для владельца: назначить роль broker сотрудникам; nginx — не логировать query `/api/v1/broker/` (LAUNCH_CHECKLIST); `e2e_cleanup` не удаляет `[E2E]`-заявки; DELETE заявки брокером даёт 405 (тесты DELETE — в 1.11).

---

## Задача 2.3: форма заявки и `/me/leads` (2026-10-20) — ЗАВЕРШЕНО

- `LeadForm` после расчёта (`CalcBreakdown`) и на странице лота (`ListingDetail`): капча, honeypot, предзаполнение из профиля, блок «Ще» (бюджет, «Коли потрібне авто», город), ошибки 400 под полями, общие тексты на 429/503/500/сеть. Экран успеха `LeadSuccess` с кодом AFY. `/me/leads` — список своих заявок, пустое состояние, гость → `/login`; пункт «Мої заявки» в `MeDashboard`.
- Атрибуция `lib/attribution.ts` + `AttributionCapture` в `app/layout.tsx`: только `sessionStorage`, UTM по белому списку и шаблону `[\p{L}\p{N}_.-]{1,100}` (то же на бэкенде в `clean_attribution`), реферер до origin, пути без query.
- Текст согласия партнёру — один источник: публичный `site-settings` отдаёт `partner_consent_text` из `PARTNER_CONSENT_TEMPLATE`, тот же текст сохраняется в заявку. При лоте `vehicle_label` формируется на сервере. `e2e_seed` заполняет `partner_name`.
- Проверки: `lead.spec.ts` + `legal.spec.ts` 42 passed (1 старый fixme), tsc/build чисто, бэкенд 817 OK (skipped=1). Ревью `security-reviewer`: 3 «важно» (2 ложно-зелёных e2e, расхождение текста согласия) + 4 «желательно» исправлены.
- Для владельца: ссылка «Як працює пригон?» (Н-30) появится со страницами доверия (2.13); настоящая Turnstile-капча с боевыми ключами не проверялась; `npm run lint` — 3 старые ошибки вне задачи.

---

## Задача 2.2: уведомление брокеру о заявке (2026-10-20) — ЗАВЕРШЕНО

- `notify_new_lead` → Celery-задача `leads.tasks.notify_broker_new_lead` (после коммита). Отправка через общий `telegram_bot/sender.py`; chat_id из админки «Налаштування сповіщень про заявки» (singleton, только числовой id) или `TELEGRAM_BROKER_CHAT_ID`; шаблон в админке, все значения `html.escape`, запрет `.`/`[`/`!`/`:` в плейсхолдерах, длина в UTF-16 (лимит 4096), кнопка «Відкрити заявку» только при https `SITE_URL`.
- Статусы доставки на `Lead`: `pending`/`sending`/`sent`/`skipped_not_configured`/`failed`; атомарный захват отправки (без дублей), повтор `self.retry` без объекта исключения (ПДн не уходят в backend). In-app уведомление `new_lead` активным брокерам, один раз на заявку (`broker_in_app_sent`).
- Админка: статус и время отправки, фильтр, действие «Надіслати брокеру повторно» (право `change`), предупреждение при ненастроенном Telegram. Настройки меняет только superuser.
- Миграции: leads 0003–0005, notifications 0003. Тесты `leads/tests_notify.py` (34), всего 814 OK (skipped=1). Ревью `security-reviewer`: 3 «важно» + 6 «желательно» исправлены.
- Для владельца: `TELEGRAM_BOT_TOKEN`, chat_id брокера/группы (бот в группе с правом писать), `SITE_URL=https://…`; выдать роль `broker` сотрудникам. Резервного email нет (Н-28) — не открывать заявки, пока доставка не проверена.

---

## Задача 2.1b: API заявки (2026-10-20) — ЗАВЕРШЕНО

- `POST /api/v1/leads/` (AllowAny) и `GET /api/v1/leads/mine/` (IsAuthenticated, пагинация 20, без ПДн и снимка, `spam` показывается как `rejected`). Порядок: тело-объект (иначе 400) → throttle `lead` (`THROTTLE_LEAD_RATE`) → honeypot `website` (правдоподобный 201 без записи) → 503 при пустом `partner_name` → капча `require_captcha(point='lead')` → поля → `create_lead`.
- Сериализатор: обязательные `consent` и `partner_consent`, нормализация телефона, тихая атрибуция, чужой/несуществующий расчёт и недоступный wholesale-лот дают одинаковый 400, сверка `source` с объектом, запрет управляющих символов. Ответ 201: `public_id`, `status`, `created_at` (без `id` и ПДн).
- `openapi.yaml` перегенерирован против Postgres (только добавления). `ENUM_NAME_OVERRIDES` для `LeadStatusEnum`, `LeadSourceEnum`, `SourceEnum`. `THROTTLE_LEAD_RATE` в `.env*.example`, пункты в `LAUNCH_CHECKLIST.md`.
- Тесты `leads/tests_api.py`: 201/400/401/403 CSRF/429 (без мока)/503, honeypot, порядок проверок, пагинация `mine/`, мутационная проверка. Ревью `security-reviewer`: 2 «важно» + 4 «желательно» исправлены. Всего 780 тестов OK (skipped=1).
- Решения владельца: (1) гостевой расчёт может приложить любой, кто знает его id (видны только суммы, без ПДн; закрыть — привязать к сессии/токену калькулятора); (2) ставка 5/час на IP считает и неудачные попытки — CGNAT и опечатки упрутся в 429; (3) принимать ли заявку на проданный лот (сейчас принимается); (4) referrer хранится без пути (задача говорила «хост и путь»).

---

## Задача 2.1a: приложение `leads` — модели, статусы, сервис, админка (2026-10-20) — ЗАВЕРШЕНО

- Модели `Lead`, `LeadStatusChange`, `LeadCounter`; TextChoices на уровне модуля (`LeadStatus` с `spam`, `PartnerStatus`, `LeadSource` calculator/listing/landing, `ContactMethod`, `NeededWhen`). `public_id` вида `AFY-ГГГГ-NNNN` (счётчик по году, `select_for_update`). CheckConstraint на `status`, `source`, `budget_usd >= 0`. Миграции 0001–0002 (0002 — права: «Брокери» и «Адміністратори» получают view/change заявок, без delete; модераторам ничего).
- `leads/validators.py`: `normalize_ua_phone` (E.164, 0 после 380 запрещён), `clean_attribution` (4 ключа UTM, URL без query/fragment, referrer только `scheme://netloc`).
- `leads/services.py`: `create_lead` (снимок расчёта, `partner_name` из `SiteSettings`, `PartnerNotConfigured` для 503 в 2.1b, чужой `Calculation` → `ValueError`), `change_status` + `ALLOWED_TRANSITIONS`, `first_response_at`, хуки `notify_new_lead`/`record_metric` через `on_commit` в try/except (лог только `lead_id`).
- `LeadAdmin`: «Джерело», фильтры, поиск, ПДн read-only, `assigned_to` только broker/admin, проверка перехода в `clean()`, чекбокс «Перевідкрити» (superuser/admin-роль, в журнал `force:`), добавление закрыто, удаление только superuser.
- Ревью `security-reviewer`: 6 «важно» + 4 «желательно» исправлены. Тесты: 731 OK (skipped=1 — параллельный `public_id` на SQLite, проверяется на Postgres в CI).
- Для владельца: подтвердить статус `spam`; текст согласия партнёру (`PARTNER_CONSENT_TEMPLATE` в `services.py`) — на юридическую вычитку; `record_metric` — заглушка до 8.7; согласие хранится на заявке до 1.14.

---

## Задача 1.12: настройки сайта и юридические документы (2026-10-14) — ЗАВЕРШЕНО

- Приложение `site_settings`: singleton `SiteSettings` (реквизиты владельца ПДн, контакты, `partner_name`/`partner_legal_name`, сроки, версия документов), админка без добавления/удаления, публичный `GET /api/v1/site-settings/` (белый список, кэш с инвалидацией в `signals.py`). Миграции 0001–0002.
- Фронт: `getSiteSettings()`, `LegalPage`, пять юр. страниц на нём (`force-dynamic`), переписанная политика, серверный подвал с реквизитами и дисклеймером партнёра. `e2e_seed` заполняет настройки.
- Ревью безопасности: исправлены сброс кэша вне веб-процесса, проверка прав в `changelist_view`, тесты границ модератора/брокера (`users/tests.py`), фильтр ссылки Telegram в подвале. Критичных не было.
- Тесты: полный прогон 682 OK до правок ревью, затем `site_settings users` 217 OK; мутации проверены.
- Не сделано: `openapi.yaml` (нужен Postgres); e2e «пустые настройки» — `test.fixme` (нужен e2e-переключатель настроек).
- Политика ссылается на `/me/data` и удаление аккаунта (1.8), заявку (2.1) — пункт в LAUNCH_CHECKLIST.
- Факт 1 сессия при оценке 2.

---

## Перепланирование 2.1 (2026-10-14)

- Решение владельца: 1.12 (SiteSettings, `partner_name`) выполняется перед 2.1; 2.1 разделена на 2.1a (модели, сервис, админка) и 2.1b (API, антиспам, openapi); выгрузка и обезличивание заявок перенесены в 1.8. Порядок ВОЛНЫ-1: … 1.6 → 1.12 → 2.1a → 2.1b → 2.2 → 2.3 → 2.4 → 1.14 → … Зависимости проверены скриптом: 56 позиций, нарушений нет.

---

## Задача 1.6: подтверждение email, Turnstile + honeypot (2026-10-14) — ЗАВЕРШЕНО

- Бэкенд: `users/tokens.py` (токен с `is_email_verified` и email, TTL `EMAIL_VERIFY_TTL_HOURS`), `users/emails.py` + шаблоны, `verify-email/`, `verify-email/resend/` (scope `verify_resend`), `auth/config/` (без секретов, `no-store`), `IsEmailVerified` на `POST /local/listings/`, начале диалога/сообщении, `dealers/apply/` (403 `email_not_verified`), data-миграция `0012_grandfather_email_verified`, 18+ (`is_adult`), одинаковый 201 на дубль email (01-S11), `users.E001/W002/E002` (system check капчи).
- `integrations/captcha.py`: Turnstile / honeypot (всегда) / off, `require_captcha(request, data, point=…)`; вход — капча после `CAPTCHA_LOGIN_AFTER_FAILURES` неудач (порядок: блокировка → капча → попытка). Honeypot `form_token` одноразовый (nonce, IP, TTL 1 ч).
- Фронт: `Captcha.tsx` (`resetKey`, `expired-callback`, сообщение о провале скрипта), «Перевірте пошту», `/verify-email`, баннер в `/me`, обработка 403 на формах.
- Ревью безопасности: исправлены тайминг-различие занятого email, многоразовый form_token, тестовые ключи Cloudflare на проде (E002), `assertRaises(Exception)`. Оставлено на 1.7: сброс пароля должен ставить `is_email_verified=True` и отзывать сессии (захват аккаунта до регистрации владельцем); желательное — проверка `hostname` в siteverify, пороги капчи по IP (password spraying), `Referrer-Policy` на `/verify-email`, имя honeypot-поля `website`.
- e2e: в стеке нет Mailpit — сценарии «письмо → ссылка» и «повторная ссылка» `test.fixme` (verify-captcha.spec.ts:70,72); нужна задача на mail-catcher в `docker-compose.e2e.yml`. Блокировка ставится на (MAX+1)-й попытке, капча проверяется раньше — спека login-limit шлёт её с токеном. auth-cookie.spec.ts:247 флейкает из-за общего аккаунта buyer и nginx `limit_req` (счётчик в памяти nginx, FLUSHALL не сбрасывает).
- Для 1.12: Turnstile (Cloudflare) обрабатывает IP посетителя. Для этапа 7: `challenges.cloudflare.com` в `script-src` и `frame-src`.
- `openapi.yaml` НЕ перегенерирован (нужен Postgres) — сделать отдельно.
- Факт 1 сессия при оценке 2.

---

## Задача 1.5: защита входа от перебора (2026-10-14) — ЗАВЕРШЕНО

- `users/lockout.py`: счётчик неудач и блокировка по sha256(email) в `django.cache` (`failure_count`, `is_locked`, `register_failure`, `reset`); в лог — хэш (12 симв.) и IP.
- `CookieTokenObtainView`: порядок throttle `login` → блокировка (429 + `Retry-After` + `retry_after` в теле) → пароль. 401 содержит `captcha_required` (порог `CAPTCHA_LOGIN_AFTER_FAILURES`=3). **Ждёт 1.6:** проверка капчи до пароля (`captcha_failed`) и её тесты.
- Scoped throttle `login`/`register`/`refresh`; `NUM_PROXIES` из `.env`; nginx: `X-Forwarded-For $remote_addr`, `limit_req` (20 r/min, burst 10 — мягче 10 r/min из задачи, чтобы не ронять e2e с одного IP) на `token/`, `register/`, `admin/login/`, `server_tokens off`.
- Админка: `LockoutAdminAuthenticationForm` (тот же счётчик, 01-S16). Предупреждение `users.W001` про LocMemCache вне DEBUG.
- Фронт: `login()` различает 429 («Забагато спроб. Спробуйте через N хв.»), 400/401, 5xx/сеть. Playwright: `login-limit.spec.ts`.
- Ревью безопасности: исправлены NFKC-обход в админке, HMAC вместо голого sha256, гонка (попытка занимается до проверки пароля), мёртвая проверка LocMemCache. Принято как есть: блокировка чужого аккаунта (в LAUNCH_CHECKLIST), 403/CSRF на входе показывается как «Сервіс тимчасово недоступний».
- Тесты: `users/tests_lockout.py` (19), мутации проверены.

---

## Задача 1.4: фронтенд на cookie-аутентификации (2026-10-14) — ЗАВЕРШЕНО

- `api/client.ts`: `credentials:'include'`, без `Authorization`; `Content-Type` только с телом (08-Q16); `X-CSRFToken` на POST/PUT/PATCH/DELETE и upload (`lib/csrf.ts`, при отсутствии cookie — `GET /auth/csrf/`). Refresh — single-flight в вкладке + `navigator.locks` между вкладками; «эпоха» сессии: 401 на запрос, ушедший до refresh, просто повторяется. Refresh 401 → один повтор → событие `auth:expired`; 429/5xx на refresh из сессии не выкидывают. 401 не редиректит, кидается `ApiError` со `status`.
- Метка сессии `has_session=1` (не httpOnly, без токена; `users/cookies.py`, `AUTH_COOKIE_HINT_NAME`): без неё фронт не зовёт profile/refresh — гость не тратит анонимный лимит (найдено ревью). Бэкенд ставит её вместе с refresh и удаляет в `clear_auth_cookies`.
- `lib/auth-context.tsx`: профиль по cookie, `login` → `POST token/` (400/401 → «Невірний email або пароль»), `logout` → `POST token/logout/` и полный переход на `/` только при 200/400, иначе сообщение «Не вдалося вийти» (ревью: при сбое сети cookie остаются). Одноразовая очистка старых `localStorage.access/refresh`. Удалены `Tokens`, `tokens`, `refreshToken`.
- `lib/use-require-auth.ts` + `lib/safe-next.ts`: 15 страниц (`app/me/**`, `b2b`, `local/new`, `local/[id]/edit`, `dealers/apply`) — один хук, `/login?next=<путь>`; `next` и ссылка уведомления — только путь сайта (не `//`, `/\`, без управляющих символов). `/login` в `Suspense`.
- `lib/server-api.ts::serverGetAuthed` — только cookie `access` (значение проверяется `^[\w.-]+$`), `cache:'no-store'`. Используется на `/me` (`app/me/page.tsx` — серверная обёртка с `force-dynamic` и меткой `data-ssr-auth`, кабинет — `MeDashboard.tsx`). После refresh клиент делает `router.refresh()`. **Следующий шаг — 2.9: B2B-лот на `serverGetAuthed`.**
- Бэкенд: `AUTH_TOKENS_IN_BODY=False`; `CSRF_COOKIE_SECURE = AUTH_COOKIE_SECURE` в прод-блоке + `ImproperlyConfigured` при `SECURE_SSL_REDIRECT` без `AUTH_COOKIE_SECURE`. Тесты: `test_token_body_has_no_tokens`, метка сессии; Bearer-тесты берут токен через `RefreshToken.for_user`.
- Тексты 11-S5: `/cookies` (таблица `access`/`refresh`/`has_session`/`csrftoken`/`cookie_consent`), `consent.ts`, `CookieBanner`, комментарии `WholesaleHint`, `server-api`.
- E2E: `auth.setup.ts` сохраняет cookie в storageState, `fixtures.api` берёт Bearer из cookie `access`; `auth.spec.ts`, `private-pages.spec.ts` (`?next=` и внешний `next` — из fixme в тесты) переписаны; новый `auth-cookie.spec.ts` (23-P8, 23-P3, 23-P4, 09-Q7, 08-S7, 11-S5, сбой выхода, утечка SSR, очистка старых токенов). 23-P4 сделан без отдельного стека с `JWT_ACCESS_MINUTES=1`: удаление cookie `access` = то, что делает браузер по Max-Age, время шапки — `page.clock`.
- `.env.e2e.example`: `AUTH_COOKIE_SECURE=false` (стенд по HTTP), `THROTTLE_ANON_RATE=2000/hour` — весь набор Playwright с одного IP выбирал 60/hour к мобильным проектам.
- Вне раздела «Файлы» (неизбежно для зелёного Playwright и ревью): `e2e/auth.setup.ts`, `fixtures.ts`, `auth.spec.ts`, `private-pages.spec.ts`, `auth-cookie-api.spec.ts` (комментарий), `users/cookies.py`, `users/views.py` (описание OpenAPI), `tests/test_e2e.py`, `.env.e2e.example`, `app/local/[id]/edit`, `app/dealers/apply`, `app/me/notifications` (safeNext).
- Проверки: backend 563 OK (+ users 138 OK после правок ревью); tsc и build чистые (`/me` — ƒ dynamic); eslint — новых ошибок нет (3 старые в `e2e/fixtures.ts`). **Весь Playwright: 127 passed / 4 skipped (fixme) / 0 failed.** Мутации Django: `AUTH_TOKENS_IN_BODY=True` и имя метки — красные. E2E-мутации отдельно не гонялись (пересборка образа); роль мутации сыграли прогоны на промежуточных сборках: без метки сессии — 429 и 13 красных, с гонкой в 23-P4 — красный.
- Ревью безопасности: «критично» — нет; три «важно» (лимит гостя, ложный выход при сбое, старые токены в localStorage) и желательные (обходы `next`, утечка SSR, защита флага Secure) исправлены.
- Серверный редирект `/me` без JS — решение владельца (2026-10-14): задача 6.2, `proxy.ts` по наличию cookie `has_session`, права проверяет API. Fixme в `private-pages.spec.ts` ссылается на 6.2. Тест на ссылку уведомления через `safeNext` — нет засева уведомлений, проверено только кодом.

---

## Задача 1.3: JWT в httpOnly-cookie + CSRF, бэкенд (2026-10-13) — ЗАВЕРШЕНО

- `users/authentication.py::CookieJWTAuthentication` — сначала Bearer (плохой → 401, как раньше), потом cookie `access`: CSRF на небезопасных методах, мусорная/протухшая cookie и забаненный пользователь → аноним (09-Q7). OpenAPI: `jwtAuth` ИЛИ `cookieAuth`.
- `users/cookies.py` — единое место флагов: `access` Path=/, `refresh` Path=/api/v1/auth/, HttpOnly, SameSite и Secure из `.env`. Views: login ставит cookie и меняет csrftoken; refresh/logout берут refresh из тела (без CSRF — переходный фронт) или из cookie (с CSRF); logout `AllowAny`, чужой refresh не отзывает (01-S13), нейтральные тексты; `GET /auth/csrf/`.
- Настройки: `CSRF_TRUSTED_ORIGINS`, `AUTH_COOKIE_*`, `JWT_ACCESS_MINUTES`/`JWT_REFRESH_DAYS`, `UPDATE_LAST_LOGIN`, `AUTH_TOKENS_IN_BODY=True` (выключить в 1.4). Шаблоны `.env.example`, `.env.docker.example`.
- Ревью безопасности: «критично» — нет; «важно» исправлено: login/refresh/logout принимают только JSON (login-CSRF через HTML-форму), `CORS_ALLOW_CREDENTIALS = not CORS_ALLOW_ALL_ORIGINS`. Желательное тоже: refresh удалённого пользователя 500 → 401, ротация csrftoken при входе, `AUTH_COOKIE_SAMESITE` только Lax/Strict.
- Тесты: 34 новых в `users/tests.py`; `test_logout_requires_auth` заменён на `test_logout_without_access_still_revokes` — контракт изменён задачей (logout `AllowAny`). Мутации (12 шт.) все красные. Backend 561 OK, tsc и build чистые, `openapi.yaml` перегенерирован против Postgres (ошибок генерации 130, было 131).
- **Не сделано:** живой прогон `frontend/e2e/auth-cookie-api.spec.ts` (2 теста, `--list` ок) — нужен e2e-стек, а это остановка dev-стека (только с «да» владельца).
- **Для 1.4 (переходный режим, найдено ревью):** «Вийти» на фронте только чистит localStorage — cookie живут (refresh 7 дней) и 15 минут любой POST фронта без Bearer получает 403 CSRF. В 1.4 «Вийти» должен вызывать `POST /api/v1/auth/token/logout/`.

---

## Задача 1.2b: is_staff → права по ролям (2026-10-13) — ЗАВЕРШЕНО

- `can_view_wholesale` (`is_verified_dealer` или `is_admin_role`) для B2B-доски и wholesale в списке/деталях; `shipments._visible_to` — admin видит все, остальные (в т.ч. broker) только свои (`watchers`); `LotImportView` — `IsAdminRole`. Профиль отдаёт read-only `is_admin_role`; фронт (`/b2b`, шапка) проверяет его вместо `is_staff`.
- Тесты 403/404 для broker и moderator по каждой точке; мутации (вернуть `is_staff`) красные. Тесты `shipments`, полагавшиеся на голый `is_staff`, переписаны под `make_admin_role`.
- Перечень остальных `is_staff`: `users/*`, `messaging/services.py:31`, `deals`, `local_listings/admin.py` — все безопасны (роль/суперпользователь), без изменений.
- Проверки: backend 526 OK, build и tsc чистые, весь Playwright 105 passed / 7 skipped / 0 failed. `openapi.yaml` — только `is_admin_role`.
- **Ревью безопасности (находки вне задачи, записаны в файлы задач 2.8 (п.1–2) и 4.7 (п.3) с пометкой «найдено ревью 1.2b»):** (1) `vehicles/views.py:12-25` — `VehicleListView/DetailView` AllowAny с `fields='__all__'`: VIN и лоты оптовых машин видны анониму в обход wholesale; (2) `listings/views.py:85` + `serializers.py:34-44` — `ListingCreateView` для любого вошедшего: IDOR по `vehicle`/`calculation`, `channel=wholesale`, `is_express_buyout` уходит в Telegram-канал; (3) `messaging/services.py:66` — диалог по wholesale-объявлению раскрывает его существование. Права модератора на «Черга модерації» перенесены в 4.5b.

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
