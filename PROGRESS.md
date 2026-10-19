# PROGRESS.md — Живой журнал прогресса

## Статус: ВОЛНА-1, этап 0 — 0.1–0.6 ✓, 1.2 ✓, 1.2b ✓, 1.3 ✓, 1.4 ✓, 1.5 ✓, 1.6 ✓, 1.12 ✓, 2.1a ✓, 2.1b ✓, дальше 2.2 → 2.3 → … (порядок — ROADMAP.md) | Сервер: Hetzner CX23 (запасной CAX11), Docker Compose | Платежи и C2C-подача выключены флагами до ВОЛНЫ-2

> История до 2026-10-12 (фазы 1–2, C2C-промты, Docker, QA, перенос БД) — `docs/PROGRESS_ARCHIVE.md`.

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
