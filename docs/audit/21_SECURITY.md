# 21. Безопасность и личные данные — сводка по разделу 3 брифа

Фаза C аудита. Источники: отчёты `01…13` (разделы «Сверка с BRIEF.md», «Безопасность и личные данные», «Итог»),
`STATUS.md` (прогоны) и точечная проверка кода на `finish-site @ d4cbfab`. Код не менялся.

Точечно перепроверено по коду:
- токен бота в `.claude/settings.local.json:58` (значение не приводится), файл впервые добавлен коммитом `a61a8c5` от 2026-06-17, сам токен появился в нём в коммите `a47169c` от 2026-07-26;
- `DEFAULT_PERMISSION_CLASSES = AllowAny` (`core/settings.py:223-224`);
- `CSRF_TRUSTED_ORIGINS`, `NUM_PROXIES`, `LOGGING`, `SENTRY` в `core/settings.py` отсутствуют (grep пуст);
- nginx слушает только `:80` (`nginx/nginx.conf:10`), TLS и HSTS закомментированы (`nginx/nginx.conf:56-61`);
- Postgres проброшен только на `127.0.0.1:5433` (`docker-compose.yml:8`);
- вызовов `getexif`/`ImageOps`/`exif` в Python-коде нет, упоминаний `captcha`/`turnstile`/`recaptcha` в `.py`/`.tsx` нет.

Легенда статуса: **выполнено** — требование брифа закрыто кодом; **частично** — есть часть механизма или есть исключения;
**нет** — механизма нет или он противоречит брифу.

## 1. Требования раздела 3 — статус

| # | Требование брифа §3 | Статус | Доказательство (файл:строка) | ID находок |
|---|---|---|---|---|
| **Токены** |||||
| 1 | JWT не в `localStorage`; httpOnly + Secure + SameSite cookie | нет | токены в теле ответа `users/urls.py:27-28`; DRF принимает только Bearer `core/settings.py:220-222`; фронт пишет в localStorage `frontend/lib/auth-context.tsx:29-30,60-61,88-89`, `frontend/api/client.ts:4,13,22,71`; страница cookie закрепляет это `frontend/app/cookies/page.tsx:87-110` | 01-S1, 08-S1, 09-S1, 10-S2, 11-S5 |
| 2 | CSRF-защита при cookie-аутентификации | нет | `CsrfViewMiddleware` есть (`core/settings.py:88`), но при Bearer не работает; `CSRF_TRUSTED_ORIGINS` не задан; на фронте нет `X-CSRFToken` (`frontend/api/client.ts:23-27`) | 08-S3, 01-S1 |
| 3 | SSR Next.js продолжает работать (после перехода на cookie) | частично | SSR сейчас анонимный, с белым списком query (`frontend/lib/server-api.ts:14-29`), поэтому приватного SSR нет; B2B-лот по SSR даёт 404, потому что SSR не знает пользователя (09-Q2) | 09-Q2, 08-S7 |
| **Регистрация** |||||
| 4 | Подтверждение email | нет | поле `is_email_verified` есть (`users/models.py:40-41`), нигде не выставляется и не проверяется | 01-S4, 08-S4 |
| 5 | Согласие на обработку данных | выполнено | `users/serializers.py:11,27-30,35-36` (метка `agreed_to_terms_at`, `users/models.py:38`); заявка дилера `users/serializers.py:76,82-89`; e2e `frontend/e2e/register.spec.ts` | — |
| 6 | Капча или эквивалентная защита от ботов | нет | grep `captcha|turnstile|recaptcha` по `.py`/`.tsx` пуст; `RegisterView` `users/views.py:40-44` | 01-S5, 08-S4 |
| **Пароли** |||||
| 7 | Стандартное хеширование Django | выполнено | `CustomUser` на `AbstractUser`, `create_user`/`set_password` (`users/serializers.py:33-37`) | — |
| 8 | Валидаторы сложности | выполнено | `AUTH_PASSWORD_VALIDATORS` `core/settings.py:130-135`, вызов в `users/serializers.py:9`. Замечание: сообщения на русском при украинском UI (`core/settings.py:137`, 01-C14) | 01-C14 |
| 9 | Сброс пароля по email, ссылка одноразовая, со сроком | нет | эндпоинтов нет (`users/urls.py:25-40`), страницы нет (`frontend/app/login/page.tsx:49-51`) | 01-S3, 08-S5 |
| 10 | Смена пароля в кабинете | нет | `UserProfileSerializer` без пароля `users/serializers.py:43-46`; в `/me` раздела нет `frontend/app/me/page.tsx:17-28` | 01-S3, 08-S5 |
| 11 | Отзыв всех сессий при смене пароля | нет | `LogoutView` отзывает один refresh `users/views.py:28-37`; фронт `logout()` его не вызывает `frontend/lib/auth-context.tsx:28-33`; бан не отзывает refresh `users/admin.py:9-22` | 01-S3, 08-S2, 08-S5, 01-S12 |
| **Защита от перебора** |||||
| 12 | Ограничение попыток входа по IP | частично | только общий `anon` 60/час на весь API (`core/settings.py:214,229-235`); IP подменяется через `X-Forwarded-For` — `NUM_PROXIES` не задан, nginx дописывает XFF (`nginx/nginx.conf:34,46`); `limit_req` в nginx нет | 01-S2, 12-S9, 12-S10 |
| 13 | Ограничение попыток по аккаунту | нет | счётчика неудач по email нет; `token/` — стандартный `TokenObtainPairView` (`users/urls.py:27`) | 01-S2 |
| 14 | Временная блокировка | нет | механизма нет; админка `/admin/` без лимита (`core/urls.py:12`) | 01-S2, 01-S16 |
| **Доступ к данным** |||||
| 15 | Телефон, email, заявки видит только владелец; брокер/админ — по роли | частично | профиль только свой (`users/views.py:52-57`), телефон C2C по отдельному эндпоинту с лимитом (`local_listings/views.py:364-378`). Но email контрагента в сделках/чате/`listing-buyers` (`deals/serializers.py:13-17`, `messaging/serializers.py:9-12`, `deals/views.py:91-107`); все `is_staff` видят импортные диалоги (`messaging/views.py:62-65`); заявок брокеру нет вообще (02-Q1) | 06-S5, 10-S3, 13-S1, 06-S9, 02-S6 |
| 16 | Тест 401/403 для чужого пользователя на каждый эндпоинт с ПД | частично | есть для profile, logout, dealers/apply (`tests/test_e2e.py:100-146`), диалогов; из 36 эндпоинтов 9 без тестов, 12 частично (`13_tests.md`) | 13-S1, 13-S2, 13-S3, 13-S4, 13-S5, 13-S7 |
| 17 | Нет утечек через списки | частично | `/api/v1/vehicles/` AllowAny `fields='__all__'` — VIN wholesale/контейнерных авто (`vehicles/views.py:11-23`, `vehicles/serializers.py:12-17`); избранное раскрывает непубличные объявления (`favorites/views.py:31-38`) | 04-S2, 13-S5, 05-S7 |
| 18 | Нет утечек через сериализаторы | частично | `owner_name` = локальная часть email (`local_listings/serializers.py:92-95`); `raw`/`owners` Opendatabot всем залогиненным (`integrations/providers.py:236-238`); `seller`/`calculation` id в публичном `ListingSerializer` (`listings/serializers.py:17-19`) | 05-S3, 10-S1, 03-S2, 04-S5, 09-S4 |
| 19 | Нет утечек через сообщения об ошибках | нет | `str(exc)` клиенту: калькулятор (`pricing/views.py:279-280`), Opendatabot вместе с API-ключом в URL (`integrations/providers.py:209-219`, `integrations/views.py:173-183`), NHTSA (`integrations/providers.py:85-86`), logout (`users/views.py:31-36`), LiqPay callback (`payments/views.py:149,162`); регистрация раскрывает существование email (`users/serializers.py:20-22`) | 03-S1, 02-S1, 09-S5, 03-S6, 01-S13, 06-S13, 01-S11 |
| 20 | Нет утечек через sitemap | выполнено | `frontend/app/sitemap.ts:30-57` — только публичные URL, без ПДн (проверено в 11) | — |
| 21 | Нет утечек через SSR-HTML | частично | телефон в SSR не попадает (10); но `owner_name` с частью email рендерится в SSR (`frontend/components/.../LocalListingDetail.tsx:145`), а `seller`/`calculation` id — в RSC-payload (`frontend/app/listings/[id]/page.tsx:73`) | 05-S3, 10-S1, 09-S4 |
| **Права субъекта ПДн** |||||
| 22 | Удаление аккаунта | нет | `ProfileView` только Retrieve/Update (`users/views.py:52-57`); удаление пользователя в админке каскадом стирает данные второй стороны (`deals/models.py:20,26,64`, `messaging/models.py:16,64`) | 01-S6, 08-S6, 11-S2, 06-S11 |
| 23 | Выгрузка своих данных | нет | эндпоинта нет (`users/urls.py:25-40`), при этом политика это обещает (`frontend/app/privacy/page.tsx:67-78`) | 01-S6, 08-S6, 11-S2 |
| 24 | Политика конфиденциальности и cookie, проверенная связка | частично | страницы есть, связь с регистрацией/футером работает (11). Нет реквизитов владельца ПДн (`frontend/app/privacy/page.tsx:18-22`), список данных не совпадает с моделями, нет третьих лиц и трансграничной передачи, срока хранения, права жалобы Омбудсмену; cookie-страница описывает localStorage | 11-S1, 11-S3, 11-S4, 11-S5, 11-S6, 11-S7 |
| **Загрузки файлов** |||||
| 25 | Проверка типа | частично | C2C-фото — только `content_type` от клиента, без Pillow (`local_listings/views.py:251,292,303-307`); `VehicleImage`/`TrackingEvent` — без проверки (`vehicles/models.py:42`, `shipments/models.py:87`); `upload_lot_photos` — тип по Content-Type (`integrations/management/commands/upload_lot_photos.py:59-71`) | 05-S1, 04-S4, 03-S5, 13-S8 |
| 26 | Проверка размера | частично | C2C: лимит `LOCAL_LISTING_PHOTO_MAX_SIZE_MB` (`local_listings/views.py:279-280`); фото авто и трекинга — без лимита; `upload_lot_photos` читает ответ целиком в память | 04-S4, 03-S5, 13-S8 |
| 27 | Удаление EXIF-геоданных | нет | в проекте нет ни одного вызова `getexif`/`ImageOps` (grep) | 05-S2, 04-S4, 03-S5 |
| 28 | Безопасные имена файлов | нет | сохраняются исходные имя и расширение (`local_listings/views.py:303-307`, `local_listings/models.py:203`); `/media/` без `nosniff` (`nginx/nginx.conf:24-27`) | 05-S1, 04-S4, 12-S7 |
| **Инфраструктура** |||||
| 29 | Секреты только в `.env` | нет | **реальный токен Telegram-бота в отслеживаемом файле** `.claude/settings.local.json:58`; insecure `SECRET_KEY`-фолбэк в коде (`core/settings.py:27`); `.dockerignore` пропускает `.claude/`, `dump.sql`, `pgdata/` в образ (`Dockerfile.backend:25`, `.dockerignore:1-20`) | 12-S1, 01-S10, 01-C8, 12-S4 |
| 30 | HTTPS | нет | nginx только `listen 80` (`nginx/nginx.conf:10`), TLS закомментирован (`:56-60`); Django при `DEBUG=false` редиректит на https (`core/settings.py:423`) — прод-сценарий не работает | 12-S2 |
| 31 | HSTS | частично | Django — только при `DEBUG=false` (`core/settings.py:424-426`, preload без решения владельца); в nginx закомментирован (`nginx/nginx.conf:61`); на HTML Next нет | 01-S9, 12-S3, 01-S18 |
| 32 | Безопасные заголовки (CSP и др.) | частично | Django: `X_FRAME_OPTIONS`, `nosniff` только для API (`core/settings.py:430-431`); CSP нет нигде; nginx не добавляет заголовков, в `next.config.ts` нет `headers()` (`frontend/next.config.ts:12-36`) | 01-S9, 12-S3, 08-S9 |
| 33 | Порт БД не наружу | выполнено | `docker-compose.yml:8` — `127.0.0.1:5433:5432`; Redis не проброшен (`docker-compose.yml:26-28`, без пароля — 12-S12) | 12-S12 (желательно) |
| 34 | Бэкапы Postgres | нет | ни скрипта, ни сервиса/cron; `DEPLOY_NOTES.md:7-20` описывает SQLite | 12-S6 |
| 35 | Логирование без личных данных | нет | `LOGGING` не задан; gunicorn/nginx пишут полный URL с query и IP (`docker/entrypoint.sh:32`, нет `log_format`); `telegram_id` в info-логе (`integrations/tasks.py:103`); ротации нет | 12-S8, 01-S14, 03-S4, 07-S9 |
| **Роли** |||||
| 36 | Роли buyer / dealer / broker / admin | частично | есть buyer/dealer/admin (`users/models.py:25-28`), **broker нет**; права фактически дают `is_verified_dealer`/`is_staff`, а `role` декоративна (01-Q3); фронт B2B проверяет `role === 'admin'` (`frontend/app/b2b/page.tsx:17`) | 01-S7, 02-S6, 06-S9, 01-Q3, 09-S2, 04-S6 |

**Итого по 36 пунктам: выполнено 5, частично 13, нет 18.**

## 2. Сквозные находки безопасности (критично и важно)

Дедуплицировано: одна проблема, найденная в нескольких пакетах, — одна строка с перечнем ID.
Желательные находки (S «желательно») сюда не включены, кроме упомянутых в скобках при слиянии.

| № | Уровень | Проблема | Где (файл:строка) | ID | Действие |
|---|---|---|---|---|---|
| 1 | **критично** | Реальный токен Telegram-бота в отслеживаемом файле в **публичном** репозитории; файл в истории с 2026-06-17 (коммит `a61a8c5`), токен — с 2026-07-26 (коммит `a47169c`), игнорируется `.gitignore:44`, но уже отслеживается | `.claude/settings.local.json:58` | 12-S1 | **Владелец: отозвать токен в @BotFather (`/revoke`) и выпустить новый — сразу, до любых задач.** Затем задача: `git rm --cached .claude/settings.local.json`, по желанию чистка истории (filter-repo) |
| 2 | критично | JWT (access + refresh на 7 дней) в `localStorage`, нет httpOnly-cookie и CSRF; cookie-страница юридически закрепляет это | `frontend/lib/auth-context.tsx:29-30,60-61,88-89`; `frontend/api/client.ts:4,13,22,71`; `users/urls.py:27-28`; `core/settings.py:220-222`; `frontend/app/cookies/page.tsx:87-110` | 01-S1, 08-S1, 08-S3, 09-S1, 10-S2, 11-S5 | Cookie-аутентификация + CSRF, SSR с `credentials`, обновить cookie-страницу |
| 3 | критично | Нет лимита попыток входа по аккаунту и временной блокировки; по IP — только общий anon 60/час | `core/settings.py:214,229-235`; `users/urls.py:27` | 01-S2 (01-S16 жел.) | Scoped throttle на auth + счётчик неудач по email с блокировкой |
| 4 | критично | Нет HTTPS: nginx только `:80`; Django при `DEBUG=false` редиректит на https; за балансировщиком — бесконечный редирект (`X-Forwarded-Proto $scheme`) | `nginx/nginx.conf:10,35,54-61`; `core/settings.py:423,429` | 12-S2 | Сервер 443 + Let's Encrypt, редирект 80→443 |
| 5 | критично | Любой залогиненный создаёт импортный `Listing` на любой `vehicle` (wholesale, `status`, чужой `calculation`) без модерации, и он сразу уходит в официальный Telegram-канал | `listings/views.py:84-86`; `listings/serializers.py:34-45`; `telegram_bot/signals.py:5-13` | 04-S1, 07-S1, 02-S5 (жел.), 13-S12 (жел.) | Закрыть на админа/брокера, модерация перед публикацией |
| 6 | критично | API-ключ Opendatabot утекает пользователю и в кэш БД через текст исключения httpx (ключ в query) | `integrations/providers.py:209,212-219`; `integrations/views.py:173-183` | 03-S1 | Общий текст ошибки, маскировка в логе, ключ в заголовке |
| 7 | критично | Загрузка фото C2C: тип только по `content_type` клиента, исходное имя/расширение → хранимый XSS через `/media/` (нет `nosniff`/CSP) | `local_listings/views.py:251,292,303-307`; `local_listings/models.py:203`; `nginx/nginx.conf:24-27` | 05-S1, 12-S7 (жел.) | Pillow `verify()` + пересохранение, uuid-имя, `nosniff` на `/media/` |
| 8 | критично | EXIF/GPS не удаляется ни с каких фото; фото авто/трекинга без лимита размера и с исходными именами; `upload_lot_photos` качает любой URL без лимита и проверки; трекинг-фото публичны | `local_listings/views.py:301-310`; `vehicles/models.py:42`; `shipments/models.py:87`; `integrations/management/commands/upload_lot_photos.py:59-71` | 05-S2, 04-S4, 03-S5, 13-S8 | Общий валидатор изображений (формат, размер из `.env`, без EXIF, uuid-имя), приватная отдача трекинг-фото |
| 9 | критично | При пустом `LIQPAY_PRIVATE_KEY` (дефолт) подпись callback = `sha1(data)` — любой переводит платёж в completed | `payments/liqpay_client.py:44-46,98-103`; `core/settings.py:302` | 06-S1 | Без ключа callback и checkout — 503 «не настроено» |
| 10 | критично | Общий checkout: сумма, `purpose` и чужой `listing_id` от клиента; оплата 0.01 меняет статус любого `Listing` (issue #24); тесты закрепляют это поведение | `payments/serializers.py:24-26,41-48`; `payments/views.py:74-97`; `payments/models.py:76-79`; `payments/tests.py:30-35` | 06-S2, 13-S6 | Серверная цена из админки, проверка владения; до этого отключить эндпоинт |
| 11 | критично | Email (и ФИО) контрагента раскрывается в сделках, чате, уведомлениях (в т.ч. Telegram) и `listing-buyers`; на `listing-buyers` нет ни одного теста | `deals/serializers.py:13-17`; `messaging/serializers.py:9-12`; `deals/views.py:91-107`; `deals/services.py:57`; `frontend/app/me/deals/page.tsx:102`; `frontend/api/deals.ts:23-26` | 06-S5, 10-S3, 13-S1, 08-S11 (жел.) | Отдавать id + отображаемое имя; тесты 401/403 |
| 12 | критично | Права субъекта ПДн (удаление, выгрузка) заявлены в политике, механизма нет ни на бэкенде, ни в UI | `users/views.py:52-57`; `users/urls.py:26-40`; `frontend/app/me/page.tsx:17-28`; `frontend/app/privacy/page.tsx:67-78` | 01-S6, 08-S6, 11-S2, 06-S11 (жел.) | `DELETE /auth/profile/` (анонимизация + отзыв токенов), `GET /auth/me/export/`, кнопки в `/me` |
| 13 | критично | Не указан владелец ПДн (юрлицо, ЄДРПОУ, адрес) — ст. 12 ЗУ «Про захист персональних даних»; issue #10 | `frontend/app/privacy/page.tsx:18-22`; `frontend/app/rules/page.tsx:200`; `frontend/app/terms/page.tsx:78-81`; `frontend/components/layout/Footer.tsx:9-10` | 11-S1 | Модель реквизитов в админке; **данные — решение владельца** (см. 22_CONFIG, раздел д) |
| 14 | важно | Нет сброса пароля, смены пароля и отзыва всех сессий | `users/urls.py:25-40`; `frontend/app/login/page.tsx:49-51`; `frontend/app/me/page.tsx:17-28` | 01-S3, 08-S5 | password-reset (одноразовый токен, срок из `.env`), password-change с blacklist всех refresh |
| 15 | важно | Выход на фронте не отзывает refresh (logout-эндпоинт не вызывается) | `frontend/lib/auth-context.tsx:28-33`; `users/urls.py:29` | 08-S2 (01-S12, 01-S13 жел.) | Вызов logout / очистка cookie на сервере |
| 16 | важно | Email не подтверждается — можно зарегистрироваться на чужой адрес | `users/models.py:40-41`; `users/serializers.py:33-37`; `frontend/app/register/page.tsx:24-28` | 01-S4, 08-S4 (01-S11 жел.) | Письмо с подписанной ссылкой, ограничения до подтверждения |
| 17 | важно | Нет капчи/антибота на регистрации, входе, заявке дилера | `users/views.py:40-44`; `users/urls.py:27` | 01-S5, 08-S4 | Turnstile/hCaptcha через адаптер с demo-режимом, ключ в `.env` |
| 18 | важно | Нет роли broker: заявки/диалоги доступны всем `is_staff`, «брокер по роли» невозможен; `role` декоративна | `users/models.py:25-28`; `core/settings.py:272`; `messaging/views.py:62-65`; `messaging/services.py:157-161` | 01-S7, 02-S6, 06-S9 | `Role.BROKER` миграцией + `IsBroker` |
| 19 | важно | `DEFAULT_PERMISSION_CLASSES = AllowAny` — любой новый view публичен по умолчанию | `core/settings.py:223-224` | 01-S8 | По умолчанию `IsAuthenticated`, публичные — явно |
| 20 | важно | Нет CSP и заголовков безопасности на HTML-страницах; HSTS только в Django при `DEBUG=false`, в nginx закомментирован | `nginx/nginx.conf:9-62`; `frontend/next.config.ts:12-36`; `core/settings.py:418-431` | 01-S9, 12-S3, 08-S9 (жел.), 01-S18 (жел.) | `add_header ... always` в nginx или `headers()` в Next, CSP из `.env` |
| 21 | важно | `DEBUG=true` в `.env` на проде отключает все SECURE_* и включает известный SECRET_KEY из репозитория | `core/settings.py:25-27,419`; `docker-compose.yml:36` | 01-S10, 01-C8 | Нет фолбэка в репо; проверка при старте DEBUG + не-localhost хосты |
| 22 | важно | Текст исключения (`str(exc)`) в ответе 500 калькулятора и далее в UI | `pricing/views.py:279-280`; `frontend/app/calculator/page.tsx:47` | 02-S1, 09-S5 (жел.), 03-S6 (жел.), 06-S13 (жел.) | Общее сообщение, детали в лог |
| 23 | важно | Анонимный `POST /pricing/calculate/` пишет `Calculation` на каждый вызов, без отдельного throttle и очистки | `pricing/views.py:144,328-336` | 02-S2 | Scope `expensive`, очистка анонимных расчётов |
| 24 | важно | Сырой ответ Opendatabot (`raw`, `owners`) — возможно ПДн третьих лиц — отдаётся всем залогиненным и хранится бессрочно | `integrations/providers.py:236-238`; `integrations/views.py:183` | 03-S2 | Белый список полей, TTL |
| 25 | важно | VIN/номер без regex → подмена пути/query запроса к внешнему API; длинный номер → 500 | `integrations/views.py:45-47,96-101,146-158`; `integrations/providers.py:80,203-205` | 03-S3 (05-S8 жел.) | Regex VIN/номера, экранирование URL |
| 26 | важно | Публичный `/api/v1/vehicles/` отдаёт VIN, лоты, повреждения всех авто (wholesale, в контейнерах) в обход B2B | `vehicles/views.py:11-23`; `vehicles/serializers.py:12-17` | 04-S2, 13-S5 | Ограничить выборку или закрыть; тест утечки |
| 27 | важно | Legacy `/api/calculate/` публичен, хардкод-ставки, `float`, без `is_estimate` (решение владельца — не трогать) | `cars/views.py:26-54`; `core/urls.py:34` | 04-S3 | Минимум — флаг отключения или `is_estimate: true` |
| 28 | важно | `owner_name` = локальная часть email в публичном списке, детали и SSR-HTML | `local_listings/serializers.py:92-95`; `LocalListingDetail.tsx:145` | 05-S3, 10-S1 | Нейтральное отображаемое имя |
| 29 | важно | Обход модерации: правка expired + оплата RENEW сразу делает объявление active | `local_listings/serializers.py:259-266`; `payments/views.py:33-38` | 05-S4 (05-S9 жел.) | Правка не-active → pending |
| 30 | важно | Жёсткое удаление объявления каскадом стирает сделки, отзывы и жалобы | `local_listings/views.py:146-148`; `deals/models.py:12-15`; `reports/models.py:26-31` | 05-S5 | Мягкое удаление |
| 31 | важно | Показ телефона не журналируется; массовый сбор номеров не обнаружить | `local_listings/views.py:364-378`; `core/settings.py:238` | 05-S6 | Журнал просмотров без номера + суточный лимит |
| 32 | важно | Избранное принимает любое объявление (pending/rejected/hidden) и раскрывает его данные | `favorites/views.py:31-38`; `favorites/serializers.py:25-67` | 05-S7 | Только `status=active` |
| 33 | важно | LiqPay callback не сверяет `amount`/`currency`/`action` с `Payment` | `payments/views.py:154-179` | 06-S3 | Сверка, иначе failed + лог |
| 34 | важно | Статус LiqPay `sandbox` засчитывается как оплата и в боевом режиме | `payments/liqpay_client.py:111` | 06-S4 | Принимать только при `LIQPAY_SANDBOX=true` |
| 35 | важно | Ответы в диалоге без отдельного спам-лимита | `messaging/views.py:35-36,100`; `core/settings.py:215,237` | 06-S6 | Throttle `messages` на POST |
| 36 | важно | `result_url`/`server_url` задаёт клиент — открытый редирект и увод callback | `payments/serializers.py:33-34`; `payments/views.py:80-81` | 06-S7 | Строить на сервере из `SITE_URL` |
| 37 | важно | Гонка и повторное применение эффекта в callback; reversed не откатывает | `payments/views.py:158-179` | 06-S8 | `select_for_update`, флаг `applied_at` |
| 38 | важно | Wholesale-лоты со срочным выкупом при пустом B2B-канале уходят в публичный канал (утечка B2B-цен) | `telegram_bot/tasks.py:45-49` | 07-S2 | Без B2B-канала wholesale не публиковать |
| 39 | важно | Данные в Telegram-постах без `html.escape` → поломка отправки, 500 в webhook, подмена разметки | `telegram_bot/handlers.py:75,95-100`; `telegram_bot/tasks.py:58-63` | 07-S3 | `html.escape()` |
| 40 | важно | Фронт B2B проверяет доступ по самовыбранной `role === 'admin'`, а не `is_staff`/`is_verified_dealer` | `frontend/app/b2b/page.tsx:17` | 09-S2 (04-S6 жел.) | Проверка по флагам |
| 41 | важно | Фото Copart/IAAI проксируются, кэшируются и уходят в og:image без атрибуции (issue #11) | `frontend/components/listings/ListingCard.tsx:22`; `ListingDetail.tsx:20,52`; `frontend/app/listings/[id]/page.tsx:40-41`; `frontend/next.config.ts:31-33` | 09-S3 | **Решение владельца #11**, затем флаг «показывать фото аукциона» |
| 42 | важно | Политика не соответствует фактическим данным (переписка, сделки, жалобы, телефон, заявка дилера…; «просмотры» не собираются) | `frontend/app/privacy/page.tsx:26-33` | 11-S3 | Переписать §2 по моделям |
| 43 | важно | Не названы получатели (LiqPay, SMTP, VIN-провайдеры, S3, Telegram) и трансграничная передача | `frontend/app/privacy/page.tsx:55-64` | 11-S4 | Дополнить §5 |
| 44 | важно | Нет срока хранения и права жалобы Уповноваженому ВР | `frontend/app/privacy/page.tsx:67-78,85` | 11-S6 | Срок из настроек, пункт об Омбудсмене |
| 45 | важно | `COPY . .` запекает в образ `.claude/` (с токеном), `pgdata/`, `dump.sql` | `Dockerfile.backend:25`; `.dockerignore:1-20` | 12-S4 | Расширить `.dockerignore` |
| 46 | важно | Все контейнеры работают от root | `Dockerfile.backend:13-33`; `Dockerfile.frontend:24-34` | 12-S5 | `USER app` / `USER node` |
| 47 | важно | Бэкапов Postgres нет | `docker-compose.yml:4-23`; `DEPLOY_NOTES.md:7-20,146-149` | 12-S6 | `pg_dump -Fc` по расписанию, ротация, внешняя копия, тест restore |
| 48 | важно | Логи с ПДн (URL с query, IP, `telegram_id`) и без ротации; `LOGGING` не задан | `docker/entrypoint.sh:32`; `nginx/nginx.conf`; `docker-compose.yml`; `integrations/tasks.py:103` | 12-S8, 01-S14 (жел.), 03-S4 (жел.), 07-S9 (жел.) | `log_format` без `$args`, ротация json-file, фильтр ПДн |
| 49 | важно | Throttling обходится подменой `X-Forwarded-For` (нет `NUM_PROXIES`) | `nginx/nginx.conf:34,46`; `core/settings.py:219-240` | 12-S9 (12-S10 жел.) | `NUM_PROXIES: 1`, `X-Forwarded-For $remote_addr` |
| 50 | важно | Мониторинга ошибок нет (Sentry/GlitchTip) | `requirements.txt:1-25`; `core/settings.py` | 12-S13 | `SENTRY_DSN` из `.env`, `send_default_pii=False` |
| 51 | важно | Нет тестов 401/изоляции на `me/*`, `dealers/application`, confirm/cancel/review сделок, `notifications/mark-read`, чужой saved-search, `telegram/link` | `users/urls.py:32-35,40`; `deals/tests.py:236-321`; `telegram_bot/views.py:47-60` | 13-S2, 13-S3, 13-S4 | Тест на каждый эндпоинт: аноним 401, чужой 403/404 |
| 52 | важно | Нет ни одного теста на требования §3 (функции отсутствуют) | — | 13-S7 | Писать вместе с этапом 1 |
| 53 | важно | Тесты ходят в платные API, если ключ есть в локальном `.env` (обнуляется только Telegram) | `integrations/tests.py:452-462,582-585`; `tests/test_e2e.py:555-567`; `core/settings.py:14,406-407` | 13-S9, 13-C1 | Мокать провайдеров / обнулять ключи при `_testing` |

Всего: **53 уникальные проблемы** (13 критичных, 40 важных), сведённые из 76 ID S-находок уровня «критично»/«важно» по 13 пакетам (плюс желательные ID, влитые в строки при слиянии).

## 3. Что сделать владельцу немедленно (не задача для Claude)

1. Отозвать токен Telegram-бота в @BotFather (`/revoke`), выпустить новый и положить только в `.env` на сервере (12-S1).
2. Решить: чистить ли историю git от файла `.claude/settings.local.json` (после отзыва токена это уже не блокер).
3. Решения по #10 (реквизиты юрлица — владелец ПДн) и #11 (права на фото аукционов) — см. `22_CONFIG.md`, раздел (д).
