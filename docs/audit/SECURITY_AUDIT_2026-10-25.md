# Аудит уязвимостей и недочётов — 2026-10-25

Ветка `finish-site`. Метод: ревью незакоммиченного diff (задача 3.4a) + 5 параллельных проверок `security-reviewer` по зонам приложения.
Уровни: **критично** — исправить до релиза; **важно** — до закрытия текущего этапа; **недочёт** — в бэклог.

## Сводка

Всего **78** находок: **4 критично**, **30 важно**, **44 недочёта**.

| Раздел | Зона | Крит. | Важно | Недочёт |
|---|---|---|---|---|
| A | Незакоммиченные правки 3.4a | 0 | 7 | 8 |
| B | Объявления, избранное, поиски, жалобы | 0 | 6 | 9 |
| C | Фронтенд, зависимости, инфраструктура, CI | 2 | 5 | 6 |
| D | Аккаунты, аутентификация, настройки | 0 | 2 | 7 |
| E | Сообщения, калькулятор, сиды | 0 | 4 | 8 |
| F | Платежи, сделки, интеграции, бот | 2 | 6 | 6 |

### Порядок исправления (первым делом)

1. **C2** — перевыпустить токен Telegram-бота в @BotFather (действие владельца, 2 минуты).
2. **F1 + F2** — закрыть платежи: пустой ключ LiqPay → 503; цена и листинг только с сервера. Пока не сделано — эндпоинт checkout за флагом.
3. **C1** — обновить `next` ≥ 16.4.3 (RCE в `/_next/image`).
4. **C3–C5** — поднять Pillow, PyJWT, Django, DRF.
5. **B1, B2, B3** — обходы модерации и утечка скрытых объявлений через избранное.
6. **D1** — отзыв сессий при смене пароля в админке.
7. **E1, E2** — сиды при старте контейнера (демо-курс поверх реального, воскрешение удалённых ставок).
8. **A1–A7** — до коммита задачи 3.4a.

### Соответствие «ID находки → задача» (все 78)

Файлы задач — `docs/tasks/`, номера и порядок — `ROADMAP.md` (блок «Срочные доработки по аудиту»). «Новая» — задача создана по этому аудиту; «допись» — находка добавлена разделом «Дополнено аудитом…» в существующий файл.

| ID | Задача | Тип |
|---|---|---|
| A1–A15 | 3.4 (3.4a), раздел «Обязательные доработки 3.4a до закрытия» | допись |
| B1, B2, B10, B11 | 4.3 (4.3a), раздел «Дополнено аудитом…» | допись |
| B3, B4, B5, B7, B12 | 4.4, раздел «Дополнено аудитом…» | допись |
| B6 | 2.17 (hotfix, ВОЛНА-1) + 4.4 (полная валидация) | новая + допись |
| B8, B9 | 4.13 | новая |
| B13 | 3.3 (блокирует `LOTS_ENABLED=true`) | допись |
| B14 | 6.7 (выполнена; устарела) + проверка в 4.4 и 4.13 | допись |
| B15 | 4.3 (тесты B1, B2, B10, B11) + 4.4 (тесты B3–B6) | допись |
| C1, C3, C4, C5 | 1.16 (C5: pip-audit/npm audit в CI — 7.5) | новая |
| C2 | действие владельца: `docs/LAUNCH_CHECKLIST.md`, раздел 0 (ссылка на этот аудит); опциональный скан истории — 7.5 | чек-лист |
| C6, C8, C9, C12, C13 | 7.3 | допись |
| C7, C10 | 7.1 | допись |
| C11 | 7.5 | допись |
| D1–D9 | 1.17 | новая |
| E1, E2 | 1.18 | новая |
| E3, E4, E5, E6, E7, E12 | 4.7 | допись |
| E8 | 2.10 (блокирует `SHIPMENTS_ENABLED=true`) | допись |
| E9, E10, E11 | 2.17 | новая |
| F1, F2, F3, F4, F5, F6, F12 (LiqPay), F14 | 1.15 (первая в очереди; связь с 4.1 — раздел в файле 4.1) | новая |
| F7, F13 | 4.6 | допись |
| F8 | 3.2 (блокирует Opendatabot и `VIN_REPORTS_ENABLED=true`) | допись |
| F9, F10, F12 (Telegram) | 5.5 | новая |
| F11 | 5.2 | допись |

Пересчёт: A 15 + B 15 + C 13 + D 9 + E 12 + F 14 = 78. Не перенесённых находок нет.

## A. Незакоммиченные правки задачи 3.4a (почта, НБУ, Outbox)

Тесты затронутых приложений зелёные (368 OK), `ruff` и `makemigrations --check` чистые — находки ниже тестами не ловятся.

| # | Уровень | Где | Суть | Исправление |
|---|---|---|---|---|
| A1 | важно | `pricing/views.py:134` | `exchange_rate_info` вставлена между `@extend_schema(...)` и `class CalculateView` — декоратор ушёл на функцию, у калькулятора пропало OpenAPI-описание; CI «openapi.yaml актуален» упадёт, перегенерация сотрёт документацию. | Перенести функцию выше декоратора (лучше в `calculator.py`), перегенерировать схему против Postgres. |
| A2 | важно | `integrations/email.py:79` | `EMAIL_MODE=real` + smtp без `EMAIL_HOST` (и dummy/locmem/filebased) = «Налаштовано»; письма падают в воркере. Тест `test_email_smtp_without_host_not_configured` переключили на `auto` вместо починки. | Проверять хост для smtp и в режиме real; locmem — только в тестах. |
| A3 | важно | `integrations/tasks.py:12` | `send_email_task` наследует `retry_backoff=True` (1 с) и 3 повтора — все попытки за ~7 с; минутный сбой SMTP = потеря писем сброса пароля. | `retry_backoff≈60`, больше повторов. |
| A4 | важно | `pricing/tasks.py:15` | `autoretry_for=(URLError, RatesUnavailable)` не ловит `TimeoutError`/`RemoteDisconnected` — курс за день не загружается, команда падает трейсбеком. | Использовать `integrations.base.RETRYABLE_EXCEPTIONS` в задаче и команде. |
| A5 | важно | `.env.docker.example:100` | `DEFAULT_FROM_EMAIL=noreply@localhost`; `is_placeholder` не считает заглушкой ни его, ни `noreply@your-domain.example` — статус зелёный, письма в спам (возврат 01-C3). | Пустое значение в шаблоне + проверка домена в `EmailProvider._from_ok`. |
| A6 | важно | `integrations/email.py:102` | demo-режим печатает письмо целиком в stdout (мимо PiiScrubFilter) и хранит тело в `OutboxMessage` — рабочие ссылки сброса пароля в логах = захват аккаунта читающим логи. | Маскировать ссылки в demo; demo при `DEBUG=False` — Error, не Warning. |
| A7 | важно | `integrations/admin.py:88` | Кнопки «Оновити курс НБУ» и «Надіслати тестовий лист» защищены только `view_integrationhealth`; `update_or_create` затирает ручной курс владельца. | Отдельное право (`pricing.change_exchangerate` / `integrations.run_checks`) или superuser. |
| A8 | недочёт | `users/views.py:252` | При ненастроенной почте регистрация отвечает 201, фронт пишет «ми надіслали лист», а письма нет. | Вернуть `email_sent` в ответе 201 (не раскрывает существование аккаунта). |
| A9 | недочёт | `integrations/email.py:114` | Воркер при «не налаштовано» молча возвращает `skipped` с INFO — нет `record_error`, нет FailedTask (рассинхрон окружения web/worker не виден). | `record_error('email', …)` + WARNING. |
| A10 | недочёт | `core/settings.py:491` | `NBU_API_URL=` (пустая переменная) → пустой URL → `ValueError`, а статус «Налаштовано». | `os.environ.get(...) or default`. |
| A11 | недочёт | `pricing/views.py:139` | Давность курса считается только по USD/UAH; старый USD/EUR не даёт `exchange_rate_stale`. | Брать самую старую из двух дат. |
| A12 | недочёт | `pricing/nbu.py:60` | `fetch_and_save_rates` сообщает «оновлено» по полученным, а не записанным курсам; запись без транзакции → смесь дат. | `transaction.atomic()` + возвращать только изменённые строки. |
| A13 | недочёт | `pricing/views.py:134` | Нарушение CLAUDE.md: бизнес-логика курса во views, дублирует `selection_is_demo` из `calculator.py`. | Перенести в `calculator.py`. |
| A14 | недочёт | `integrations/email.py:55` | `_redact` дублирует `core.logging_filters.scrub` и слабее его (`%40`, телефоны). | `scrub(mask_secrets(text))`. |
| A15 | недочёт | `integrations/tests_email.py:263` | `test_smtp_error_shown_without_recipient` и `tests_rates_provider::test_failure_is_shown_without_secrets` не содержат `assertNotIn` — мутация не краснеет; нет тестов на A2 и A4. | Добавить проверки, прогнать мутацией. |

## B. Объявления, избранное, поиски, жалобы

Все находки воспроизведены пробным тестом (`scratchpad/audit/test_audit_zone.py`, в проект не добавлен).

| # | Уровень | Где | Суть | Исправление |
|---|---|---|---|---|
| B1 | важно | `local_listings/serializers.py:282-290`, `payments/views.py:31-37` | **Обход модерации через продление:** правка `expired`-объявления не возвращает его на модерацию, а RENEW переводит `expired → active` — непроверенный спам публикуется. | Существенная правка не-active (кроме sold/hidden) → `pending`; или RENEW → active только без правок после `moderated_at`. |
| B2 | важно | `local_listings/views.py:263-304` | Фото, добавленные/удалённые/сменённые (is_primary) в `active`-объявлении, не идут на модерацию — подмена фото после одобрения. | Изменение фото в `active` → `pending`. |
| B3 | важно | `favorites/views.py:44-56` | **Утечка скрытых объявлений:** чужое `pending/rejected/hidden` можно добавить в избранное перебором id, и список избранного покажет марку, цену, фото (карточка при этом 404). То же для оптовых Listing при LOTS_ENABLED. | Проверять видимость перед `get_or_create` (иначе 404); фильтровать невидимые в сериализаторе. |
| B4 | важно | `favorites/views.py:44-56,82-88` | `listing_id='abc'` или несуществующий → 500 (IntegrityError, `FavoriteSerializer(None)`). | Валидация через сериализатор, 400/404. |
| B5 | важно | `saved_searches/serializers.py:6-10`, `saved_searches/tasks.py:30,72-97` | `filters` не валидируются: `[1,2]` или `{"year_min":"abc"}` принимаются, и ежедневная рассылка падает для **всех** пользователей. Нет лимита числа поисков и размера JSON. | Схема filters, лимит N на пользователя, try/except на каждый поиск в задаче. |
| B6 | важно | `local_listings/filters.py:42-51` | `?price_min=abc` → 500 на публичном каталоге (ловится ValueError, а летит ValidationError). | `Decimal()` с перехватом `InvalidOperation` / ловить ValidationError. |
| B7 | недочёт | `saved_searches/tasks.py:27-30` | Алерт ищет по `created_at > last_notified_at`: объявление, созданное до прогона и одобренное после, не попадёт в алерт никогда. | Сравнивать с `moderated_at`. |
| B8 | недочёт | `reports/views.py:6-8` | У жалоб нет своего троттлинга и `IsEmailVerified`, нет `max_length` у comment (принят комментарий на 200 000 символов). | Scope `reports` (~10/hour), IsEmailVerified, max_length. |
| B9 | недочёт | `reports/serializers.py:6-10` | Перечисление: на чужое `pending` ответ 201, на несуществующее 400; `reported_user` принимает любой id. | queryset `listing` — только ACTIVE/свои; одинаковый ответ для пользователей. |
| B10 | недочёт | `local_listings/views.py:412-422` | Promote не проверяет статус: TOP/BUMP за `pending/rejected/hidden` списывает деньги без эффекта. | TOP/BUMP только ACTIVE, RENEW — ACTIVE/EXPIRED. |
| B11 | недочёт | `local_listings/serializers.py:292-297` | Владелец переводит `pending → sold/hidden`, объявление выпадает из очереди модерации. | Из `pending/rejected` разрешить только `hidden` или запретить до модерации. |
| B12 | недочёт | `favorites/views.py:21`, `saved_searches/views.py:14` | Списки без пагинации и лимита записей. | Пагинация / лимит. |
| B13 | недочёт | `listings/serializers.py:17` | `seller` (pk пользователя) отдаётся публично в каталоге лотов (модуль пока заморожен). | Убрать или `public_display_name`. |
| B14 | недочёт | `core/modules.py`, `core/middleware.py` | Флага `C2C_ENABLED` в коде нет (запланирован в задаче 6.7): `/api/v1/local/`, избранное, поиски, жалобы флагом не закрываются. | Сверить с ROADMAP 6.7. |
| B15 | недочёт | `tests/test_authz_matrix.py:288` | Нет тестов на B1–B6. | Добавить регрессионные тесты. |

**В порядке:** обработка фото (`core/uploads.py`: тип по содержимому, лимиты байт/пикселей, снятие EXIF/GPS, uuid-имена, без SVG/GIF); права владельца на фото и promote (403 чужому); mass assignment закрыт; телефон только через `/contact/` для ACTIVE с троттлингом; ordering по белому списку; N+1 закрыт; поиски/избранное фильтруются по пользователю; legacy `cars/` выключен по умолчанию.

## C. Фронтенд, зависимости, инфраструктура, CI

| # | Уровень | Где | Суть | Исправление |
|---|---|---|---|---|
| C1 | **критично** | `frontend/package.json:17` | `next` 16.2.9: `npm audit` — 1 critical + 4 high, в т.ч. **неаутентифицированный RCE** в Image Optimization (AVIF/SVG, GHSA-2xp9-vwfh-vxw4, GHSA-2464-fhr4-w9xw), SSRF в оптимизаторе, cache poisoning ISR. `/_next/image` открыт наружу; вложенный `sharp` 0.34.5 тоже уязвим. | `next` и `eslint-config-next` ≥ 16.4.3, пересобрать образ. |
| C2 | **критично** | история git, коммит `a47169c` (`.claude/settings.local.json`) | В публичном репозитории в истории `origin/main` лежит **настоящий токен Telegram-бота**. Из дерева удалён в `a6e0a57`, но доступен любому. Gitleaks в CI историю не сканирует (`ci-cd.yml:10-19`). | Перевыпустить токен в BotFather (если ещё не сделано); чистка истории после этого не обязательна. |
| C3 | важно | `requirements.txt:4` | `Pillow==12.2.0` — много известных уязвимостей (по OSV 5 critical); Pillow обрабатывает загружаемые фото. | ≥ 12.3.x / 13.x, прогнать тесты загрузки. |
| C4 | важно | `requirements.txt:7` | `PyJWT==2.13.0` — известные уязвимости (1 critical); через неё SimpleJWT проверяет токены. | 2.15.x. |
| C5 | важно | `requirements.txt:2-3` | `Django==6.0.6` (1 high), `djangorestframework==3.17.1` (3 high). | Django 6.0.8, DRF 3.18.2; pip-audit/npm audit в CI (задача 7.5). |
| C6 | важно | `Dockerfile.backend:25`, `.dockerignore` | `COPY . .` запекает в образ `dump.sql` (дамп БД с ПДн), `pgdata/`, `private_media/`, `.env.e2e`, `.claude/`, `.coverage`. | Дописать исключения из `docs/tasks/7.3-containers.md:31`. |
| C7 | важно | `nginx/nginx.conf:101-111`, `frontend/next.config.ts:20-28` | На страницах Next нет CSP, `X-Frame-Options`/`frame-ancestors`, `nosniff` — clickjacking `/login`, `/me`; HTTPS закомментирован (`nginx.conf:113-120`). | Задача 7.1. |
| C8 | недочёт | `Dockerfile.backend`, `Dockerfile.frontend:28-37` | Процессы от root; во frontend-runtime весь `node_modules` с dev-зависимостями. | Задача 7.3 (non-root, `output: 'standalone'`). |
| C9 | недочёт | `docker-compose.yml:35-38` | Redis без пароля (наружу закрыт, но доступен любому контейнеру сети). | `REDIS_PASSWORD` (7.3/7.5). |
| C10 | недочёт | `nginx/nginx.conf:89` | `/admin/` открыт в интернет, только `limit_req` на логин. | allow/deny по IP или VPN. |
| C11 | недочёт | `.github/workflows/ci-cd.yml:1-9, 246-253` | Нет `permissions:`; actions по тегам, не SHA; `appleboy/ssh-action` без `fingerprint` (подмена сервера). | `permissions: contents: read`, `fingerprint:`. |
| C12 | недочёт | `Dockerfile` (корень) | Мёртвый файл: `npm install` без lock, root, `server.js` не существует. | Удалить. |
| C13 | недочёт | `.env.docker.example:10-11` | Слабый пароль БД по умолчанию `autoforyou_dev_pass` (`deploy.sh` отклоняет, ручной `compose up` — нет). | Оставить пустым. |

**В порядке:** JWT только в httpOnly-cookie, CSRF-заголовок, нет `dangerouslySetInnerHTML`/`eval`, `?next=` через `lib/safe-next.ts`, SSR не тянет лишнего, `NEXT_PUBLIC_*` — только URL; nginx: media не-картинки как attachment + nosniff, `/protected-media/` internal, XFF не подменить, `server_tokens off`; БД и Mailpit только на 127.0.0.1; gunicorn не стартует с DEBUG; в текущем дереве живых секретов нет; `pull_request_target` не используется.

## D. Аккаунты, аутентификация, настройки проекта

Проверочные скрипты: `scratchpad/probe.py`, `scratchpad/probe2.py` (в проект не добавлены).

| # | Уровень | Где | Суть | Исправление |
|---|---|---|---|---|
| D1 | важно | `users/admin.py:58`, `:110` | Смена пароля через админку («Змінити пароль») и `manage.py changepassword` **не отзывает сессии**: `session_version` не растёт, старые access/refresh работают (подтверждено). Угнанный аккаунт остаётся у атакующего. | `change_password_form` с `revoke_all_sessions(user)` в `save()` + тест. |
| D2 | важно | `users/views.py:125`, `users/models.py:118` | Вход чувствителен к регистру email, а регистрация и сброс — нет: `John.Doe@…` не входит как `john.doe@…` (подтверждено 401). Возможны дубли, отличающиеся регистром. | `email__iexact` в `get_by_natural_key`, хранить в нижнем регистре, `UniqueConstraint(Lower('email'))`. |
| D3 | недочёт | `users/serializers.py:33` | `validate_password` без `user` → `UserAttributeSimilarityValidator` не работает: пароль = email принят (201). | Вызывать в `validate()` с `CustomUser(email=…)`. |
| D4 | недочёт | `users/views.py:255`, `:346` | Письма сброса и «вже є акаунт» лимитированы только по IP — с пула IP можно бомбить чужой ящик и портить репутацию домена. | Лимит по HMAC-хэшу адреса (~3/час), ответ тот же. |
| D5 | недочёт | `core/settings.py:21` | `_TESTING = 'test' in sys.argv` срабатывает на `celery -Q test`/`--hostname test` → в проде отключаются проверка SECRET_KEY, HSTS, капча, почта в locmem. | `sys.argv[1:2] == ['test']`. |
| D6 | недочёт | `users/admin.py:128` | `is_superuser/is_staff/groups/user_permissions` правит любой staff с `change_customuser` (сейчас право никому не выдано — скрытая эскалация). | readonly для не-superuser. |
| D7 | недочёт | `users/serializers.py:44` | Телефон при регистрации не валидируется (`UA_PHONE_VALIDATOR` только в профиле). | Добавить валидатор в `RegisterSerializer`. |
| D8 | недочёт | `users/services.py:35` | Проверка «уже есть pending-заявка дилера» без транзакции — два параллельных POST дают две заявки. | Частичный `UniqueConstraint` + 409. |
| D9 | недочёт | `core/test_runner.py:58` | Сетевой предохранитель не перехватывает `connect_ex` и `sendto` (UDP). | Обернуть их `_check_address`. |

**В порядке:** JWT 15 мин/7 дней, ротация + blacklist, claim `sv` под `select_for_update`, отзыв сессий при сбросе/смене пароля через API, logout-all, бан; httpOnly-cookie, Secure, SameSite, CSRF; lockout с HMAC/NFKC (и в админке) + nginx `limit_req`; одинаковые ответы при регистрации/входе/сбросе (нет перечисления); одноразовые токены; `role`/`is_verified_dealer`/`is_staff` read-only; экспорт данных без ПДн контрагентов; проверки SECRET_KEY/DEBUG; CORS без credentials при `*`; схема API только для admin; `PiiScrubFilter` везде; `site_settings` — whitelist полей.

## E. Сообщения, уведомления, доставка, калькулятор, учёт задач

| # | Уровень | Где | Суть | Исправление |
|---|---|---|---|---|
| E1 | важно | `pricing/management/commands/seed_rates.py:79-83`, `docker/entrypoint.sh:30` | Сид при каждом старте контейнера кладёт **демо-курс 41.50/0.92 на сегодня**, если НБУ за сегодня ещё не загружен — после рестарта до 09:00 все расчёты и снимки `Calculation` идут по демо-курсу, хотя вчерашний настоящий есть. | Демо-курс только при пустой `ExchangeRate` или `NBU_MODE=demo`. |
| E2 | важно | `seed_rates.py:51,66,73,109,135`, `seed_auction_fees.py:178,198` | `get_or_create` без `valid_from` на каждом старте: после закрытия старой ставки и создания новой — `MultipleObjectsReturned`, справочники досеиваются частично; удалённый админом плейсхолдер **возвращается** после рестарта и попадает в расчёт. | Сиды только на пустой базе или ручным шагом. |
| E3 | важно | `messaging/services.py:115-120`, `messaging/views.py:106` | Брокер/админ, не участвующий в импортном диалоге, при открытии помечает прочитанными **все** сообщения, включая ответы коллег покупателю; счётчик брокера раздут. | Не-участнику помечать только сообщения инициатора. |
| E4 | важно | `messaging/views.py:56-75`, `messaging/serializers.py:72-85` | Список диалогов без пагинации; prefetch всех сообщений всех диалогов; N+1 в `get_other_participant`; детальный просмотр отдаёт всю переписку. Раздутый диалог (300 req/h) делает просмотры тяжёлыми для всех брокеров (DoS). | Пагинация, аннотации `Subquery`/`Count(filter=)`, сообщения порциями. |
| E5 | недочёт | `messaging/views.py:109-127`, `services.py:102-112,184` | Ответ в диалог не проверяет активность объявления и получателя; уведомление с ПДн создаётся для удалённого аккаунта. | 403 «диалог закрыт», получатели только `is_active`. |
| E6 | недочёт | `messaging/services.py:67,92` | Двойной клик «Написати» → `IntegrityError` → 500. | Поймать и вернуть существующий диалог. |
| E7 | недочёт | `notifications/views.py:27-30` | `mark-read {"id":"abc"}` → 500. | `IntegerField` в сериализаторе, 400. |
| E8 | недочёт | `shipments/serializers.py:30`, `views.py:23-28` | Наблюдатель сборного контейнера видит VIN, лот и фото **чужих** авто (`fields='__all__'`). Сейчас модуль заморожен `SHIPMENTS_ENABLED`. | При разморозке — только свои авто. |
| E9 | недочёт | `pricing/models.py:84` | Перекрывающиеся диапазоны `bid_min..bid_max` тиров проходят `clean()`; применяемый тир решает `pk`. | Проверка пересечения диапазонов в `AuctionFeeTier.clean()`. |
| E10 | недочёт | `pricing/serializers.py:34` | `calculation_date` не ограничен: гость видит будущие (ещё не вступившие) тарифы. | Диапазон «сегодня − N … сегодня». |
| E11 | недочёт | `task_ledger/sanitize.py:17-19` | Короткие строки без пробелов хранятся открыто после `scrub` (токен, IBAN, VIN не маскируются); сейчас таких аргументов нет — защита на договорённости. | По умолчанию `<str:len>`, открыто — allowlist имён. |
| E12 | недочёт | `messaging/tests.py`, `tests/test_authz_matrix.py:274-279` | Нет тестов на доступ к импортным диалогам (`handles_imports`). | Добавить. |

**В порядке:** диалоги только свои (чужой → 404), запрет писать себе; XSS в сообщениях нет; уведомления по `user`, лимит 50; права и гейтинг shipments; калькулятор — только `Decimal`, кросс-курс верный, ставки из БД, снимки неизменяемы; 422/500 без деталей; полная сетка тарифов только broker/admin; троттлинг калькулятора; `metrics` без ПДн; `FailedTask` только admin read-only; `e2e_seed` защищён флагом и паролем.
## F. Платежи, сделки, интеграции, Telegram-бот

Подделка подписи при пустом ключе и схлопывание `../` в URL Opendatabot подтверждены скриптом, остальное — по коду.

| # | Уровень | Где | Суть | Исправление |
|---|---|---|---|---|
| F1 | **критично** | `payments/liqpay_client.py:216-222,275-285` | При пустом `LIQPAY_PRIVATE_KEY` (дефолт, пока LiqPay не подключён) подпись = `base64(sha1(data))` — **любой подделывает callback**: `promote` → `order_id` → анонимный callback `status=success` → TOP/RENEW бесплатно. `LIQPAY_MODE` нигде не применяется. | Пустой/плейсхолдер-ключ → checkout и callback 503, `decode_callback` бросает исключение; тест. |
| F2 | **критично** | `payments/views.py:66-115`, `payments/models.py:377-380` | Сумма, валюта, `listing_id`, `purpose` приходят от клиента, владелец не проверяется; `unlock_listing()` переводит **чужой** Listing в `in_stock` (оплата 0.01 в sandbox или подделка из F1). | Цену и листинг — с сервера, проверка владельца/роли; до прайса закрыть флагом. |
| F3 | важно | `payments/views.py:158-179` | Callback без `atomic`/`select_for_update`, переход из COMPLETED обратно разрешён — двойной success продлевает TOP дважды. | `select_for_update` по `order_id`, COMPLETED — конечный статус. |
| F4 | важно | `payments/views.py:154-175` | Не сверяются `amount`/`currency`/`action` из callback с `Payment`. | При расхождении не завершать, warning. |
| F5 | важно | `payments/serializers.py:421-422` | `server_url`/`result_url` задаёт клиент — подписанные колбэки уходят атакующему (материал для replay), open redirect. | Строить из `SITE_URL` на сервере. |
| F6 | важно | `core/settings.py:406` | `LIQPAY_SANDBOX` по умолчанию `true`, статус `sandbox` → `completed` — на проде с забытой переменной тарифы оплачиваются тестовой картой. | При `not DEBUG` — `false` или `ImproperlyConfigured`. |
| F7 | важно | `deals/services.py:187-203` | По одному объявлению можно подтвердить несколько сделок (статус SOLD не проверяется) — накрутка бейджа продавца и отзывов фейковыми аккаунтами. | confirm только если нет другой CONFIRMED и не SOLD, `select_for_update`. |
| F8 | важно | `integrations/providers.py:233-241,272` | `vin`/`plate` в путь Opendatabot без `quote`: `?plate=../../X` → произвольный эндпоинт с **нашим apikey**; ответ (`raw`, `owners`) кэшируется и отдаётся любому авторизованному. Модуль заморожен `VIN_REPORTS_ENABLED`. | `quote(..., safe='')`, regex-валидация, не отдавать `raw`/`owners`. |
| F9 | недочёт | `telegram_bot/handlers.py:239-243` | Привязка одного Telegram ко второму аккаунту → `IntegrityError` → webhook 500 → Telegram повторяет апдейт; гонка по токену. | `atomic` + `select_for_update`, понятный ответ. |
| F10 | недочёт | `integrations/tasks.py:64-121` | `TelegramNetworkError`/`TelegramRetryAfter` не входят в `RETRYABLE_EXCEPTIONS` — уведомления теряются при сбое сети. | Слать через `telegram_bot/sender.send_message`, `base=ResilientTask`. |
| F11 | недочёт | `telegram_bot/tasks.py:104-117` | `self.retry()` внутри `asyncio.run` глотается `except Exception`; `time.sleep(3)` держит воркер. | Пробрасывать `Retry`, `rate_limit` вместо sleep. |
| F12 | недочёт | `payments/liqpay_client.py:281`, `telegram_bot/views.py:88` | Подпись и секрет сравниваются `!=` (timing). | `hmac.compare_digest`. |
| F13 | недочёт | `deals/services.py:216-225` | `cancel_deal`/`confirm_deal` без блокировки — CANCELLED при проданном объявлении. | `select_for_update`. |
| F14 | недочёт | `local_listings/tests.py:894`, `tests/test_e2e.py:252` | Нет тестов на пустой ключ, чужой `listing_id`, расхождение суммы, откат из COMPLETED, параллельный callback. Пункт токена бота (см. C2) в `docs/LAUNCH_CHECKLIST.md:691` не отмечен. | Добавить тесты; отметить пункт после `/revoke`. |

**В порядке:** webhook Telegram закрыт 503 при пустом секрете; IDOR в deals закрыт (404), `DealUserSerializer` без email; `IsAdminRole` на импорте лотов; маскировка секретов в `record_error`; таймауты httpx; троттлинг `expensive` у VIN; `csrf_exempt` только на callback и webhook; деньги в `Decimal`.
