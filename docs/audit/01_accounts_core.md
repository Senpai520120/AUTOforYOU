# Аудит: 01 «Аккаунты и ядро» (`users/`, `core/`)

## Состав

**Файлы `users/`**

| Файл | Строк | Назначение |
|---|---|---|
| `users/models.py` | 129 | `CustomUser`, `TrustedShop`, `DealerApplication` |
| `users/serializers.py` | 100 | регистрация, профиль, партнёры, заявка дилера |
| `users/services.py` | 74 | сервис заявок дилера (подача/одобрение/отклонение + email) |
| `users/views.py` | 155 | logout, register, profile, «кабинет», заявка дилера |
| `users/urls.py` | 41 | маршруты `auth/` и `dealers/` |
| `users/admin.py` | 99 | админка пользователей (бан/разбан), партнёров, заявок дилера |
| `users/apps.py` | 5 | AppConfig |
| `users/tests.py` | 397 | 38 тестов |
| `users/__init__.py` | 0 | — |

Миграции (только назначение):
- `0001_initial.py` — CustomUser (email вместо username, phone, role, is_verified_dealer).
- `0002_alter_customuser_managers.py` — менеджер `CustomUserManager`.
- `0003_trustedshop.py` — модель TrustedShop.
- `0004_dealer_application.py` — модель DealerApplication.
- `0005_customuser_telegram_id.py` — поле `telegram_id`.
- `0006_customuser_agreed_to_terms_at.py` — метка согласия с условиями.
- `0007_customuser_is_banned_is_email_verified.py` — `is_banned`, `is_email_verified`.
- `0008_dealerapplication_agreed_to_processing_at.py` — метка согласия на обработку ПД в заявке дилера.

**Файлы `core/`**

| Файл | Строк | Назначение |
|---|---|---|
| `core/settings.py` | 431 | все настройки |
| `core/urls.py` | 42 | корневой роутинг, swagger |
| `core/celery.py` | 9 | приложение Celery, autodiscover |
| `core/__init__.py` | 3 | экспорт `celery_app` |
| `core/asgi.py`, `core/wsgi.py` | 16 / 16 | стандартные точки входа |

**Модели:** `CustomUser` (`users/models.py:24-52`), `TrustedShop` (`users/models.py:55-84`), `DealerApplication` (`users/models.py:87-129`).

**Эндпоинты** (префикс `api/v1/auth/` — `core/urls.py:13`, `api/v1/dealers/` — `core/urls.py:32`):

| Метод | Путь | View | Доступ |
|---|---|---|---|
| POST | `/api/v1/auth/register/` | `RegisterView` (`users/views.py:40-44`) | AllowAny |
| POST | `/api/v1/auth/token/` | SimpleJWT `TokenObtainPairView` (`users/urls.py:17-19,27`) | AllowAny |
| POST | `/api/v1/auth/token/refresh/` | SimpleJWT `TokenRefreshView` (`users/urls.py:21-23,28`) | AllowAny |
| POST | `/api/v1/auth/token/logout/` | `LogoutView` (`users/views.py:25-37`) | IsAuthenticated |
| GET/PUT/PATCH | `/api/v1/auth/profile/` | `ProfileView` (`users/views.py:52-57`) | IsAuthenticated |
| GET | `/api/v1/auth/me/calculations/` | `MyCalculationsView` (`users/views.py:62-72`) | IsAuthenticated |
| GET | `/api/v1/auth/me/shipments/` | `MyShipmentsView` (`users/views.py:75-85`) | IsAuthenticated |
| GET/POST | `/api/v1/auth/me/trusted-shops/` | `TrustedShopListView` (`users/views.py:92-97`) | IsAuthenticated, свой owner |
| GET/PUT/PATCH/DELETE | `/api/v1/auth/me/trusted-shops/<pk>/` | `TrustedShopDetailView` (`users/views.py:106-111`) | IsAuthenticated, свой owner |
| POST | `/api/v1/dealers/apply/` | `DealerApplyView` (`users/views.py:124-138`) | IsAuthenticated |
| GET | `/api/v1/dealers/application/` | `DealerApplicationStatusView` (`users/views.py:146-155`) | IsAuthenticated |
| — | `/admin/`, `/api/schema/`, `/api/docs/`, `/api/redoc/` | `core/urls.py:12,36-38` | админка / публичная схема |

## Функции

| Функция | Состояние | Файл:строки | Комментарий |
|---|---|---|---|
| Регистрация по email | готово | `users/serializers.py:8-37`, `users/views.py:40-44` | валидаторы пароля, проверка password2, согласие |
| Согласие с условиями при регистрации | готово | `users/serializers.py:11,27-30,35-36`; `users/models.py:38` | хранится метка времени |
| Вход (JWT) | частично | `users/urls.py:27` | токены в теле ответа; фронт кладёт их в localStorage (`frontend/lib/auth-context.tsx:60-61,88-89`) |
| Обновление токена + ротация + blacklist | готово | `core/settings.py:347-353`, `users/urls.py:28` | ROTATE + BLACKLIST_AFTER_ROTATION |
| Выход (отзыв refresh) | частично | `users/views.py:28-37` | отзывает один refresh; «выйти на всех устройствах» нет |
| Подтверждение email | заглушка | `users/models.py:40-41` | поле `is_email_verified` есть, нигде не выставляется и не проверяется (используется только в `users/admin.py:35-36,44`) |
| Сброс пароля по email | отсутствует | — | эндпоинтов нет |
| Смена пароля в кабинете | отсутствует | — | `UserProfileSerializer` не содержит пароля (`users/serializers.py:43-46`) |
| Отзыв всех сессий | отсутствует | — | нет эндпоинта; при бане refresh-токены не отзываются (`users/admin.py:9-22`) |
| Лимит попыток входа | частично | `core/settings.py:229-235` | только глобальный anon 60/час на IP; по аккаунту и блокировки нет |
| Капча / антибот | отсутствует | — | нигде в проекте |
| Удаление аккаунта | отсутствует | — | нет эндпоинта |
| Выгрузка своих данных | отсутствует | — | нет эндпоинта |
| Профиль (просмотр/правка) | готово | `users/serializers.py:40-58`, `users/views.py:52-57` | role/is_staff только для чтения |
| Роли | частично | `users/models.py:25-28` | buyer/dealer/admin; **broker нет** |
| Верификация дилера (заявка → одобрение) | готово | `users/services.py:21-63`, `users/admin.py:65-99` | email-уведомление, согласие на ПД |
| Бан/разбан | частично | `users/admin.py:9-28` | скрывает только `LocalListing`; импортные `Listing` не трогает; дублирует `reports/admin.py:24-33` |
| Кабинет: расчёты, контейнеры, партнёры | готово | `users/views.py:62-111` | фильтр по `request.user` |
| Celery + beat | готово | `core/celery.py:1-9`, `core/settings.py:355-394` | 4 задачи по расписанию, имена задач существуют |
| Заголовки безопасности (HSTS, SSL-редирект, secure cookie) | частично | `core/settings.py:418-431` | CSP нет; HSTS в nginx закомментирован (`nginx/nginx.conf:61`) |
| Логирование | отсутствует | — | `LOGGING` не задан, фильтра ПДн нет |

## Сверка с BRIEF.md

**Раздел 3 (безопасность):**

| Пункт брифа | Статус | Где |
|---|---|---|
| JWT в httpOnly+Secure+SameSite cookie, не localStorage | **противоречит** | backend отдаёт токены в теле (`users/urls.py:27-28`, `REST_FRAMEWORK` `core/settings.py:220-222` принимает только заголовок Bearer); фронт хранит в localStorage `frontend/lib/auth-context.tsx:60-61,88-89` |
| CSRF-защита при cookie | не хватает | `CsrfViewMiddleware` есть (`core/settings.py:88`), но при JWT в заголовке не применяется; `CSRF_TRUSTED_ORIGINS` не задан |
| Подтверждение email | не хватает | только поле `users/models.py:40-41` |
| Согласие на обработку данных | совпадает | `users/serializers.py:27-30`, `users/serializers.py:76,82-89` |
| Капча/защита от ботов | не хватает | — |
| Хеширование + валидаторы сложности | совпадает | `core/settings.py:130-135`, `users/serializers.py:9` |
| Сброс пароля (одноразовая ссылка со сроком) | не хватает | — |
| Смена пароля в кабинете + отзыв всех сессий | не хватает | — |
| Ограничение попыток входа по IP **и аккаунту**, временная блокировка | не хватает (частично по IP) | `core/settings.py:214,229-235` |
| Телефон/email видит только владелец | совпадает в пакете | `UserProfileSerializer` используется только в `ProfileView` (`users/views.py:53`), отдаёт только свои данные. Сериализаторы других приложений — вне пакета |
| Тесты 401/403 на каждый эндпоинт с ПД | частично | есть для dealers/apply, logout, profile (в `tests/test_e2e.py:134`); нет для `me/calculations`, `me/shipments`, `me/trusted-shops` (чужой pk → 404), `dealers/application` без токена |
| Удаление аккаунта, выгрузка данных | не хватает | — |
| Секреты только в .env | частично | insecure SECRET_KEY в коде как dev-fallback `core/settings.py:27` |
| HTTPS, HSTS | частично | `core/settings.py:423-426` (только при DEBUG=false) |
| CSP и др. заголовки | не хватает | CSP нет ни в Django, ни в nginx |
| Порт БД не наружу | совпадает | `docker-compose.yml:8` (только 127.0.0.1) |
| Логирование без ПДн | не хватает | `LOGGING` не задан |
| Роли buyer/dealer/broker/admin | **противоречит** | нет `broker` (`users/models.py:25-28`, `core/settings.py:272`) |

**Раздел 2 (конфигурация):**
- Совпадает: почти все параметры читаются из `.env` (`core/settings.py:18-411`); LiqPay по умолчанию sandbox (`core/settings.py:303`); Telegram без токена не падает (`core/settings.py:399-407`).
- Не хватает: «честного статуса не настроено» для email — без `EMAIL_BACKEND` письма молча уходят в консоль даже в проде (`core/settings.py:335-338`); отправитель письма дилеру захардкожен (`users/services.py:74`).
- Противоречит: S3-хранилище задаётся удалёнными в Django 5.1 настройками — см. 01-C1.

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 01-S1 | критично | JWT (access и refresh на 7 дней) хранятся в localStorage; любой XSS уводит сессию. Бриф требует httpOnly cookie | `frontend/lib/auth-context.tsx:60-61,88-89`; `users/urls.py:27-28`; `core/settings.py:220-222` | Кастомные TokenObtain/Refresh/Logout views ставят httpOnly+Secure+SameSite cookie; своя `JWTAuthentication` читает cookie + проверка CSRF; фронт и SSR переводить на `credentials: 'include'` |
| 01-S2 | критично | Нет ограничения попыток входа по аккаунту и блокировки; на `token/` действует только общий anon 60/час на IP (одинаковый с остальным API) | `core/settings.py:214,229-235`; `users/urls.py:27` | Отдельный `ScopedRateThrottle` на token/register/refresh (например, 5/мин) + счётчик неудач по email с временной блокировкой (кэш/django-axes) |
| 01-S3 | важно | Нет сброса и смены пароля; нет отзыва всех сессий (blacklist всех `OutstandingToken` пользователя) | `users/urls.py:25-36` | Эндпоинты password-reset (PasswordResetTokenGenerator, срок из .env), password-change с блэклистом всех refresh |
| 01-S4 | важно | Email не подтверждается: `is_email_verified` всегда False, нигде не проверяется; можно зарегистрироваться на чужой email | `users/models.py:40-41`; `users/serializers.py:33-37` | Письмо с подписанной ссылкой при регистрации; ограничить действия (объявления/сообщения) до подтверждения |
| 01-S5 | важно | Нет капчи/антибота на регистрации, входе, заявке дилера | `users/views.py:40-44`, `users/urls.py:27` | Cloudflare Turnstile (бесплатно) через адаптер с demo-режимом, ключ в .env |
| 01-S6 | важно | Нет удаления аккаунта и выгрузки данных (закон Украины о защите ПД) | — | `DELETE /auth/profile/` (анонимизация + blacklist токенов) и `GET /auth/me/export/` (JSON) |
| 01-S7 | важно | Роль `broker` отсутствует, а заявки клиентов видит брокер по роли (бриф §1, §3) | `users/models.py:25-28`; `core/settings.py:272` | Добавить `Role.BROKER` миграцией + permission-класс `IsBroker`, назначение только админом |
| 01-S8 | важно | Глобальное `DEFAULT_PERMISSION_CLASSES = AllowAny`: любой новый view без явных прав становится публичным | `core/settings.py:223-225` | По умолчанию `IsAuthenticated`, публичные view помечать `AllowAny` явно |
| 01-S9 | важно | CSP нет вообще; HSTS в nginx закомментирован; в Django HSTS только при DEBUG=false | `core/settings.py:418-431`; `nginx/nginx.conf:61` | CSP через nginx или django-csp (политика из .env); `SECURE_REFERRER_POLICY`, `Permissions-Policy` |
| 01-S10 | важно | Если в `.env` стоит `DEBUG=true` (комментарий `core/settings.py:199-202` показывает, что так было в Docker), в проде отключаются все SECURE_* и используется известный из репозитория SECRET_KEY | `core/settings.py:25-27,419`; `docker-compose.yml:36` (backend берёт DEBUG из .env) | Не иметь SECRET_KEY-фолбэка в репозитории (генерировать при старте dev) и валидировать при старте: DEBUG=true + не-localhost ALLOWED_HOSTS → ошибка |
| 01-S11 | желательно | Регистрация раскрывает существование email («user with this email already exists») — перебор пользователей | `users/serializers.py:20-22` (unique-валидатор модели `users/models.py:33`) | Одинаковый ответ + письмо «у вас уже есть аккаунт» (вместе с 01-S4) |
| 01-S12 | желательно | Бан не отзывает refresh-токены; блокирует только проверка `is_active` в JWTAuthentication (SimpleJWT 5.5.1, `authentication.py:138`). Refresh-эндпоинт `is_active` не проверяет (проверено grep по `serializers.py`) — забаненный продолжает получать новые access, хотя они отклоняются | `users/admin.py:9-22` | При бане блэклистить все `OutstandingToken` пользователя |
| 01-S13 | желательно | `LogoutView` блэклистит любой переданный refresh, не проверяя, что он принадлежит `request.user`; текст исключения SimpleJWT уходит клиенту | `users/views.py:31-36` | Сверять `token['user_id'] == request.user.id`; нейтральное сообщение об ошибке |
| 01-S14 | желательно | Логирование не настроено (`LOGGING` отсутствует): нет фильтра ПДн, нет `ADMINS`/Sentry; ошибки 500 с данными запроса идут в стандартный вывод | `core/settings.py` (нет секции) | Секция LOGGING с фильтром, маскирующим email/телефон/токены; DSN мониторинга из .env |
| 01-S15 | желательно | Swagger/Redoc/схема открыты всем в проде | `core/urls.py:36-38` | `SERVE_PERMISSIONS` = IsAdminUser или флаг .env `API_DOCS_PUBLIC` |
| 01-S16 | желательно | Админка на стандартном `/admin/` без ограничения попыток входа и 2FA | `core/urls.py:12` | Путь из .env, лимит попыток (тот же механизм, что 01-S2) |
| 01-S17 | желательно | `phone` в профиле и `contact_phone` в заявке без валидации формата | `users/models.py:34,101`; `users/serializers.py:43-46,80` | RegexValidator для формата +380… |
| 01-S18 | желательно | `SECURE_HSTS_PRELOAD=True` и `INCLUDE_SUBDOMAINS=True` включены без решения владельца; preload почти необратим для домена | `core/settings.py:425-426` | Флаги в .env, по умолчанию preload=false |

## Готовность к конфигурации

| ID | Что захардкожено / заглушка / TODO | Файл:строка | Куда вынести |
|---|---|---|---|
| 01-C1 | **S3 не заработает**: `DEFAULT_FILE_STORAGE`/`STATICFILES_STORAGE` удалены в Django 5.1 (проект на Django 6.0.6, `requirements.txt:2`) и игнорируются. При `USE_S3` файлы пойдут в локальное хранилище, а `MEDIA_ROOT` в этой ветке не задан, `MEDIA_URL` указывает на S3 → битые ссылки. Требует проверки запуском (не проверено) | `core/settings.py:174-191` | Перейти на словарь `STORAGES`; задавать `MEDIA_ROOT` всегда |
| 01-C2 | `MEDIA_URL` собирается под формат amazonaws и игнорирует `S3_ENDPOINT_URL` (R2/MinIO) | `core/settings.py:170,190` | `S3_PUBLIC_URL` / `AWS_S3_CUSTOM_DOMAIN` в .env |
| 01-C3 | Отправитель писем дилеру `'noreply@autoforyou.ua'` захардкожен вместо `DEFAULT_FROM_EMAIL`; `fail_silently=True` скрывает ненастроенный SMTP | `users/services.py:74` | `settings.DEFAULT_FROM_EMAIL`; статус интеграции SMTP |
| 01-C4 | Тексты писем об одобрении/отклонении захардкожены (и на русском при украинском интерфейсе) | `users/services.py:67-72` | Модель шаблонов уведомлений в админке |
| 01-C5 | TODO «позже заменить на Telegram-уведомление (промт 11)» | `users/services.py:8,73` | Отправка через адаптер уведомлений |
| 01-C6 | `SITE_URL` по умолчанию `https://autoforyou.ua` — реальный домен как дефолт | `core/settings.py:414` | Пустой дефолт + статус «не настроено» |
| 01-C7 | Email-бэкенд по умолчанию console даже в проде, без признака «не настроено» | `core/settings.py:335-338` | Проверка при старте/статус в админке, пункт LAUNCH_CHECKLIST |
| 01-C8 | Insecure SECRET_KEY в репозитории как dev-фолбэк | `core/settings.py:27` | Генерировать случайно при старте dev |
| 01-C9 | Жизнь токенов (15 мин / 7 дней) захардкожена | `core/settings.py:348-349` | `.env` (`JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`) |
| 01-C10 | HSTS: 1 год, preload, subdomains захардкожены | `core/settings.py:424-426` | `.env` |
| 01-C11 | Расписание beat задано в коде; `DatabaseScheduler` синхронизирует `CELERY_BEAT_SCHEDULE` в БД при каждом старте beat, поэтому правка времени в админке будет перезаписана (поведение django-celery-beat, не проверено запуском) | `core/settings.py:368-394` | Создавать PeriodicTask data-миграцией, а не через settings |
| 01-C12 | Описание API «Маркетплейс для автоперекупщиков» и `UserRoleEnum` без broker устарели | `core/settings.py:272,276-281` | Обновить при добавлении роли |
| 01-C13 | Celery eager-режим включается при `DEBUG=true` даже с Redis: при DEBUG=true в .env backend выполняет задачи синхронно внутри запроса, а worker простаивает | `core/settings.py:358-365`; `docker-compose.yml:36` | Отдельный флаг `CELERY_EAGER` в .env |
| 01-C14 | `LANGUAGE_CODE='ru-ru'`, интерфейс украинский — сообщения валидаторов пароля и DRF на русском | `core/settings.py:137` | `uk` (или из .env) |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 01-Q1 | важно | Нет задачи очистки токенов: `token_blacklist` копит `OutstandingToken`/`BlacklistedToken` бесконечно (каждый refresh с ротацией — новая строка); в beat нет `flushexpiredtokens` и `clearsessions` | `core/settings.py:373-394` |
| 01-Q2 | важно | В админке заявки дилера можно вручную поставить `status=approved` в форме — это обходит `approve_application`: `is_verified_dealer`/`role` не меняются, письмо не уходит. `agreed_to_processing_at` в админке не показан | `users/admin.py:88-99` |
| 01-Q3 | важно | Роль `dealer` может выбрать себе любой при регистрации (`users/serializers.py:15-18`), при этом права даёт только `is_verified_dealer`/`is_staff`. `role` фактически декоративна, `role='admin'` не даёт прав — два источника истины о правах | `users/serializers.py:15-18`; `users/services.py:49-51`; `users/models.py:35-36` |
| 01-Q4 | желательно | Логика бана продублирована в `users/admin.py` и `reports/admin.py`; бан не скрывает импортные `listings.Listing`; разбан через `update()` включает `is_active=True` всем, в т.ч. деактивированным по другой причине | `users/admin.py:9-28`; `reports/admin.py:24-33` |
| 01-Q5 | желательно | N+1 в админке: `list_display` с `owner`/`user`/`reviewed_by` без `list_select_related`; `__str__` обращается к `owner.email`/`user.email` | `users/admin.py:58,89`; `users/models.py:84,129` |
| 01-Q6 | желательно | `CustomUser.created_at` дублирует стандартный `date_joined` | `users/models.py:42` |
| 01-Q7 | желательно | `UPDATE_LAST_LOGIN` не включён — при входе через JWT `last_login` не обновляется, а админка показывает это поле | `core/settings.py:347-353`; `users/admin.py:47` |
| 01-Q8 | желательно | Признак тестового прогона вычисляется дважды (`_testing`, `_TESTING`) и только по `'test' in sys.argv` (pytest не распознаётся) | `core/settings.py:36,418` |
| 01-Q9 | желательно | Комментарий «prod without env var → Django will raise» неточен: при пустом `ALLOWED_HOSTS` Django не падает на старте, а отдаёт 400 на каждый запрос | `core/settings.py:45` |
| 01-Q10 | желательно | Одобрение/отклонение без `transaction.atomic`: заявка может стать approved, а пользователь не обновиться | `users/services.py:40-52` |
| 01-Q11 | желательно | `import from django.conf` и `celery.schedules` в середине settings (`noqa`), `DealerApplication.documents` — произвольный URL без ограничения домена/схемы | `core/settings.py:371`; `users/models.py:102` |

## Тесты

**Покрыто:** `users/tests.py` — 38 тестов:
- сервис заявок дилера (6), API заявки (4) и статуса (2), B2B-гейтинг (4), видимость wholesale в каталоге (3);
- logout/blacklist (4);
- согласие при регистрации (4), запрет самоназначения роли/is_staff (8), согласие в заявке дилера (3).
- Дополнительно `tests/test_e2e.py:100-146` — цепочка регистрация → вход → профиль, 401 без токена, неверный пароль.
- Playwright: `frontend/e2e/register.spec.ts` — форма регистрации и чекбокс согласия (5 тестов).

**Не покрыто:**
- 401 без токена для `me/calculations`, `me/shipments`, `me/trusted-shops`, `dealers/application`; чужой `trusted-shops/<pk>` → 404 (изоляция владельца).
- Throttling входа; ротация refresh (повторное использование старого refresh → 401); бан → токен перестаёт работать.
- Слабый пароль при регистрации → 400; несовпадение password2.
- Админские действия ban/unban и approve/reject через админку.
- Настройки безопасности (например, `manage.py check --deploy` в CI).

**Нужные Django-тесты (после реализации):** логин с cookie (Set-Cookie httpOnly/Secure/SameSite, отсутствие токенов в теле), CSRF-отказ без токена; 6-я неудачная попытка → 429/блокировка по аккаунту с разных IP; сброс пароля (ссылка одноразовая, истекает); смена пароля → все старые refresh в blacklist; подтверждение email; удаление аккаунта (анонимизация, токены отозваны) и выгрузка (только свои данные, 401 для анонима); роль broker видит заявки, buyer получает 403; бан отзывает токены; `flushexpiredtokens` в расписании.

**Нужные Playwright-сценарии:** вход → в `localStorage` нет токенов, cookie httpOnly; SSR-страница кабинета работает после входа; выход → кабинет недоступен; превышение попыток входа показывает понятное сообщение; сброс пароля по ссылке из письма (успех + повторное использование ссылки → ошибка); смена пароля выкидывает вторую вкладку/устройство; регистрация с капчей (demo-режим); удаление аккаунта и скачивание выгрузки.

## Итог

- Готовность пакета ≈ **45%**: регистрация, согласие, профиль с защитой от самоэскалации, ротация и blacklist refresh, заявки дилера и базовые prod-заголовки сделаны и покрыты тестами (38).
- Почти весь раздел 3 брифа по аккаунтам отсутствует: cookie вместо localStorage, email-подтверждение, сброс/смена пароля, отзыв сессий, капча, удаление/выгрузка, роль broker.
- Критично: **01-S1** (JWT в localStorage, refresh на 7 дней, CSP нет), **01-S2** (нет лимита попыток входа по аккаунту и блокировки).
- Важно (безопасность): 01-S3…01-S10, особенно 01-S8 (AllowAny по умолчанию) и 01-S9 (нет CSP).
- Важно (конфигурация): **01-C1** — S3 настроен удалёнными в Django 5.1 настройками, медиа в S3 не пойдут (проверить запуском).
- Важно (качество): 01-Q1 (blacklist-таблицы растут без очистки), 01-Q2 (одобрение дилера в форме админки обходит сервис), 01-Q3 (роль — декоративная).
- Celery beat: 4 задачи, имена совпадают с кодом; нет `flushexpiredtokens`/`clearsessions`; eager-режим привязан к DEBUG (01-C13).
