# Backend-тесты

Разбор 442 тестов Django: что покрыто, как распределено по типам, где дыры.

E2E-тесты Playwright — отдельно, [`docs/TEST_CASES.md`](TEST_CASES.md). Стек для них поднимается с `docker-compose.e2e.yml` и `.env.e2e` (боевой `.env` не используется), перед прогоном — `redis-cli FLUSHALL` на e2e-стеке (иначе 429 на логин и расчёт); команды — в разделе «E2E» там же.

---

## Как запускать

Рабочее окружение — `.venv`. Запускать через скрипты:

```powershell
scripts/test-backend.ps1        # Windows
scripts/test-backend.sh         # Linux/Mac/Git Bash
```

Скрипты обнуляют `DATABASE_URL` и `REDIS_URL`. Причина: локальный `.env` — docker-шаблон с хостами `db`/`redis`, а `core/settings.py` подгружает его через `load_dotenv`. Без обнуления тесты идут в Postgres/Redis из `.env` или падают. Голый `python manage.py test` без этого не рекомендуется.

Токен Telegram обнуляется в настройках при работе тест-раннера — иначе `post_save` на `Listing` запускал бы `post_listing_to_channel`, а с `CELERY_TASK_ALWAYS_EAGER=True` в тестах это уходило бы настоящими запросами в `api.telegram.org`.

```powershell
scripts/test-backend.ps1 local_listings              # одно приложение
scripts/test-backend.ps1 users.tests.TestB2BGating   # один класс
scripts/test-backend.ps1 -v2                         # с именами тестов
```

### Изоляция (задача 0.2)

Под тест-раннером (`'test' in sys.argv`, флаг `_TESTING` в `core/settings.py`) результат не зависит от `.env`:

- обнуляются `OPENDATABOT_API_KEY`, `APIFY_TOKEN`, `LIQPAY_PUBLIC_KEY`/`LIQPAY_PRIVATE_KEY`, `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY`; `CAPTCHA_PROVIDER='off'`; почта — `locmem`. Любой новый ключ внешнего провайдера добавляется в этот блок. Тесту, которому нужен ключ (например, подпись LiqPay), его задаёт `override_settings` с фиксированным тестовым значением.
- кэш — всегда `LocMemCache`, Celery — eager с `memory://`, даже при заданном `REDIS_URL`.
- сетевой предохранитель (`core/test_runner.py`, `IsolatedDiscoverRunner`): исходящие соединения запрещены, кроме `localhost`, `127.0.0.1`, `::1` и хоста БД из `DATABASES`. Попытка даёт `ExternalNetworkBlocked: Внешний сетевой запрос в тесте: <host>:<port>. Замокайте провайдер`. Тот же раннер после прогона чистит кэш `Update.event_type` aiogram (защита от segfault 139).
- `tests.base.CleanCacheTestCase` очищает кэш в `setUpClass` (после `super()`), `setUp` и `tearDownClass`: откат транзакции не трогает LocMem-кэш, и тарифы удалённых seed-строк иначе переживали бы класс. Классы с seed тарифов наследуются от него, seed — в `setUpTestData`. Страховочные тесты: `tests/test_environment.py`, `pricing.tests.TestNoStaleTiersAfterSeededClass`.

Playwright запускается только из `frontend/` (см. [`TEST_CASES.md`](TEST_CASES.md)).

БД для тестов создаётся и удаляется автоматически. Прогон занимает около 4,5 минут.

### Тестовые данные: `tests/factories.py` (задача 0.6)

Простые функции без `factory_boy`: `make_user` (email по счётчику, `is_email_verified=True`; `verified=False` — неподтверждённый), `make_dealer`, `make_staff(superuser=...)`, `auth_client(user)` (JWT через `RefreshToken`), `make_region_city`, `make_local_listing`, `make_vehicle`, `make_listing`. Локальные `_make_user`/`_auth_client` в тестах не заводят; допустимы только тонкие обёртки с особой сигнатурой (`_make_listing` в `local_listings`, `make_listing` в `tests/test_favorites…`). Точечные проверки (B2B-гейтинг, wholesale в каталоге, согласие, 409, registry 401/429) живут в тестах своего приложения, а `tests/test_e2e.py` содержит только сквозные цепочки.

### Тесты используют собственный seed, а не данные админки

Ожидаемые цифры калькулятора привязаны к placeholder-значениям `seed_rates`/`seed_auction_fees`, которые тест создаёт сам в `setUpTestData`. Правка тарифов в админке тесты не ломает; правка seed-команд — ломает (обновлять ожидания в `pricing/tests.py` и `tests/test_e2e.py::TestCalculatorAPIE2E`). Подробнее — [`TEST_CASES.md`](TEST_CASES.md).

---

## Распределение

| Приложение | Тестов | Основные темы |
|---|---:|---|
| `local_listings` | 87 | Модерация, права владельца, фильтры, фото, продвижение, антиспам, видимость по статусам |
| `pricing` | 68 | Калькулятор, акциз, аукционные сборы, кэш тарифов, курс НБУ |
| `integrations` | 46 | VIN-провайдеры, импорт лотов, троттлинг платных API |
| `users` | 42 | Заявки дилеров, B2B-гейтинг, JWT, согласия, эскалация привилегий |
| `tests/test_e2e.py` | 25 | Сквозные цепочки через API: регистрация → JWT → профиль, калькулятор, LiqPay, заявка дилера |
| `tests/test_environment.py` | 6 | Страховка изоляции окружения (0.2) |
| `tests/test_factories.py` | 3 | Общие фабрики `tests/factories.py` (0.6) |
| `users/tests_e2e_seed.py` | 5 | Команда `e2e_seed` (данные для Playwright, 0.4) |
| `deals` | 31 | Сделки, отзывы, рейтинг продавца |
| `tests/test_favorites…` | 28 | Избранное, уведомления, сохранённые поиски |
| `telegram_bot` | 41 | Команды бота через webhook, привязка аккаунта, middleware, задачи, автопост |
| `messaging` | 23 | Переписка, непрочитанные, права доступа |
| `listings` | 12 | B2B-гейтинг детали, N+1, ограничения БД |
| `shipments` | 10 | Доступ к контейнерам, утечка VIN |
| `payments` | 8 | Валидация чекаута LiqPay |
| `reports` | 7 | Жалобы на объявления и пользователей |

---

## Что покрыто хорошо

### Калькулятор — 68 тестов

Самая проверенная часть, и это оправдано: ошибка тут стоит пользователю денег.

| Класс | Что проверяет |
|---|---|
| `TestCalcAgeCoeff` | Коэффициент возраста, включая границы |
| `TestExcisePetrol2000cc8years`, `TestExciseDiesel…` | Акциз по реальным кейсам с проверкой цифры |
| `TestExciseEV60kwh`, `TestPHEV` | Электро и гибриды — акциз от киловатт, а не от объёма |
| `TestUSOriginDuty10Percent` | Пошлина для США |
| `TestCalculateLandedCost*` | Полная разбивка, все статьи и итог |
| `TestCalculateLandedCostDecimalPrecision` | Только `Decimal`, никаких `float` |
| `TestCopart*`, `TestIAAI*` | Тиры аукционных сборов, фиксированные и процентные |
| `TestAuctionFeeBoundary`, `TestIAAITierBoundaryDB` | Выбор тира на границах диапазона (`_lookup_tier`): `TestAuctionFeeBoundary` создаёт тиры сам, `TestIAAITierBoundaryDB` — на seed-данных IAAI. Классический источник ошибок на единицу |
| `TestZeroPriceEdgeCase` | Нулевая цена |
| `TestPricingCacheInvalidation` | Правка ставки инвалидирует кэш |
| `TestLandedCostE2ECopartBroker` | Сквозной расчёт на внутренних функциях (`pricing/tests.py`), без HTTP. Через API считает `tests/test_e2e.py::TestCalculatorAPIE2E` |

### Модерация и права — `local_listings`, 87 тестов

`TestModerationService`, `TestRemoderation` — публикация, отклонение с причиной, возврат на модерацию при правке существенных полей.

`TestLocalListingOwnership`, `TestListingImage*` — чужое объявление и чужие фото недоступны.

`TestListingVisibilityByStatus` — объявление вне `active` видят только владелец и `staff`. Проверяются все статусы по отдельности.

`TestAntispamListing` — телефон и ссылка в описании помечают объявление для модерации, обычные числа — нет. `TestContactEndpoint` — телефон не отдаётся в списке и в детали, контакт — только авторизованному (аноним — 401).

`TestBannedUser` — забаненный не получает JWT, его объявления скрыты, новые подать нельзя.

### Разграничение доступа

| Класс | Что закрывает |
|---|---|
| `TestB2BGating` | Оптовая доска только верифицированным дилерам |
| `TestWholesaleListingDetailGating` | Прямой доступ по ID к оптовому лоту — 404 |
| `TestRoleIsNotSelfAssignable` | Пользователь не назначает себе `role: admin` ни при регистрации, ни через профиль |
| `TestShipmentAccess` | Контейнеры и VIN внутри — только тем, кто их отслеживает |
| `TestConversationDetailAPI` | Чужая переписка недоступна |
| `TestRegistryRequiresAuth`, `VinReportAccessTest` | Платные внешние API под аутентификацией |

---

## Безопасность, бриф §3

### Матрица прав `tests/test_authz_matrix.py` (задача 1.11)

Одна строка `Case` = один (url_name, метод). На строку генерируются отдельные тест-методы (БД откатывается между ними, фикстуры строятся один раз в `setUpTestData`, ~340 тестов за ~10 с):

| Проверка | Что утверждает |
|---|---|
| `__anon` | аноним получает 401, данные владельца не изменились |
| `__other` | посторонний (`b`) получает код из строки (403/404; для «своих» эндпоинтов - 200 над СВОИМИ данными), данные владельца не изменились, в ответе нет чужих маркеров и id (списки) |
| `__owner` | владелец получает код из строки; в списках видит свои объекты |
| `__role_<роль>` | staff / broker / moderator / admin / dealer / unverified - код из строки (отказ не меняет данные) |
| `__no_csrf` | cookie-сессия владельца без `X-CSRFToken` на небезопасном методе - 403, данные не изменились |

Тест полноты (`AuthzMatrixCompletenessTests`) обходит `get_resolver()`: каждый именованный маршрут `api/...`, которого нет в белом списке `PUBLIC`, обязан иметь строку на каждый обработчик (get/post/put/patch/delete). Новый приватный эндпоинт без строки роняет тест с именем URL; белый список проверяется (view в нём должен быть `AllowAny`, без `get_permissions`). `test_detects_endpoint_missing_from_matrix` и `test_detects_missing_method_row` проверяют сам детектор. Админка Django в обход не входит: у неё свои права (`AdminRolesTests`: moderator/broker/staff/buyer на платежи, настройки сайта, заявки, очередь модерации).

Состояние 36 эндпоинтов матрицы из `docs/audit/23_TESTS.md` (раздел 3; сам аудит заморожен) и новых эндпоинтов этапа 1:

| Эндпоинт | Статус |
|---|---|
| `auth/me/calculations`, `auth/me/shipments`, `auth/me/trusted-shops[/<pk>]`, `dealers/application`, `dealers/apply` (23-D6...D9) | в матрице |
| `deals/`, `deals/<pk>/confirm|cancel|review`, `deals/listing-buyers/<id>` (23-D10, 1.9) | в матрице; точечные - `deals.tests.DealsOutsiderAPITest`, `ListingBuyersAPITest` |
| `messages/start`, `messages/conversations[/<pk>]`, `messages/unread-count` (23-D11) | в матрице |
| `notifications/*`, `favorites/*`, `saved-searches[/<pk>]` (23-D12, D13) | в матрице; GET `saved-searches/<pk>/` не реализован во view (нет строки; появится - тест полноты потребует) |
| `telegram/link-token`, `telegram/link` DELETE (23-D91) | в матрице; точечные - `telegram_bot.tests.TelegramUnlinkApiTest` |
| `shipments/`, `shipments/<pk>/`, фото трекинга `shipments/<pk>/events/<id>/photo/` (1.10) | в матрице |
| `local/listings/` POST, `<pk>` PATCH/DELETE, `contact`, `images`, `images/<img_id>`, `promote`, `my-listings` (23-D14) | в матрице; фото чужого листинга через свой `pk` - `local_listings.tests.TestForeignListingImageViaOwnListing` |
| `password-change/`, `token/logout-all/`, `verify-email/resend/`, `profile/` GET/PATCH/PUT (1.6, 1.7) | в матрице |
| `leads/mine/`, `broker/leads/*` (2.1a, 2.4), в т.ч. DELETE заявки (405 всем, 403 buyer/moderator/staff/dealer) | в матрице; роль moderator - 403, админка - `AdminRolesTests` |
| `vehicles/<vin>/report|registry`, `lot-import`, `b2b/board`, `reports/` | в матрице |
| `listings/create/` (23-D49) | в матрице как «любой вошедший», **ждёт задачу 2.8** |
| `payments/liqpay/checkout/`, чужой `listing_unlock` (23-D72) | в матрице как «любой вошедший», сумма задаётся клиентом (#24), **ждёт задачу 4.1** |
| чужое pending в избранном (23-D15) | **ждёт задачу 4.4** |
| `vehicles/` (VIN wholesale в публичном списке, 23-D16) | публичный, **ждёт задачу 2.8** |
| `pricing/rates/` (суммы только staff/broker, 23-D47) | публичный, **ждёт задачу 2.6** |
| `auth/profile/` DELETE, `auth/me/export/`, `auth/profile/cancel-deletion/` (1.8) | в матрице; подробно - `users.tests_account_data` |

### Таблица «требование брифа §3 -> тест» (пункты 1-36 из `docs/audit/21_SECURITY.md`)

| # | Требование | Тест | Задача | Статус |
|---|---|---|---|---|
| 1 | JWT в httpOnly cookie | `users.tests.CookieAuthTests` | 1.3 | покрыто |
| 2 | CSRF при cookie | `CookieAuthTests`, `users.tests_password.TestCookieCsrf`, `leads.tests_api.LeadCsrfTests`, `__no_csrf` матрицы (все небезопасные приватные методы) | 1.3 | покрыто |
| 3 | SSR работает | `frontend/e2e/ssr.spec.ts` (Playwright) | 1.4 | покрыто (e2e) |
| 4 | Подтверждение email | `users.tests_email_verify.TestRegisterSendsVerification`, `TestUnverifiedRestricted`, `TestResendVerification` | 1.6 | покрыто |
| 5 | Согласие на обработку | `users.tests.TestRegistrationConsent`, `TestConsentLogRegistration`, `TestDealerApplicationConsent` | 1.14 | покрыто |
| 6 | Капча | `integrations.tests_captcha.TestRegisterCaptcha`, `TestLoginCaptcha`, `TestDealerApplyCaptcha`, `leads.tests_api.LeadCaptchaTests`, `TestPasswordResetCaptcha` | 1.6 | покрыто |
| 7 | Стандартное хеширование | `users.tests.TestUserModel.test_password_is_stored_hashed` | 1.11 | покрыто |
| 8 | Валидаторы сложности | `users.tests_email_verify.TestRegisterValidation.test_weak_password_returns_400`, `users.tests.TestDealerApplyAPI` | 1.6 | покрыто |
| 9 | Сброс пароля, ссылка одноразовая и со сроком | `users.tests_password.TestPasswordResetRequest`, `TestPasswordResetConfirm` | 1.7 | покрыто |
| 10 | Смена пароля | `users.tests_password.TestPasswordChange`, строка `auth-password-change` матрицы | 1.7 | покрыто |
| 11 | Отзыв сессий при смене пароля | `users.tests_password.TestLogoutAll`, `TestSessionVersion`, `TestRevokeService`, `TestBanAdminAction` | 1.7 | покрыто |
| 12 | Лимит попыток по IP | `users.tests_lockout.TestScopedThrottle` | 1.5 | покрыто |
| 13 | Лимит попыток по аккаунту | `users.tests_lockout.TestAccountLockout`, `TestLockoutCacheCheck` | 1.5 | покрыто |
| 14 | Временная блокировка | `TestAccountLockout`, `TestAdminLoginLockout` | 1.5 | покрыто |
| 15 | ПДн видит только владелец; брокер/админ по роли | матрица `tests.test_authz_matrix` (`__other`, `__role_*`), `users.tests.TestImportedConversationsVisibility`, `TestModeratorBoundaries` | 1.2, 1.11 | покрыто |
| 16 | 401/403 для чужого на каждый эндпоинт с ПДн | матрица + тест полноты | 1.11 | покрыто |
| 17 | Нет утечек через списки | список-изоляция матрицы (`ids`: me/calculations, me/shipments, deals, conversations, notifications, favorites, saved-searches, local/my-listings, leads/mine, shipments) | 1.11 | покрыто; публичный `vehicles/` (VIN) - ждёт задачу 2.8 |
| 18 | Нет утечек через сериализаторы | `deals.tests.ListingBuyersAPITest`, `users.tests.PublicDisplayNameTest`, `frontend/e2e/pii-leaks.spec.ts` | 1.9 | покрыто |
| 19 | Нет утечек через тексты ошибок | `integrations.tests.*test_opendatabot_error_logged_masked` (ключ в логе); `str(exc)` клиенту: `pricing/views.py:282`, `integrations/views.py:240` теста нет | не назначено | пробел: кода-исправления нет, задачи нет (в отчёт 1.11) |
| 20 | Нет утечек через sitemap | `frontend/e2e/ssr.spec.ts` (содержит каталог); отсутствие ПДн отдельным тестом не проверяется | 1.9 | частично |
| 21 | Нет утечек через SSR-HTML | `frontend/e2e/pii-leaks.spec.ts` | 1.9 | покрыто (e2e) |
| 22 | Удаление аккаунта | `users.tests_account_data.AccountDeletionRequestTests`, `AnonymizeTests`, `AdminAnonymizeTests`, `leads.tests.AnonymizeUserLeadsTests`, `frontend/e2e/account-data.spec.ts` | 1.8 | покрыто |
| 23 | Выгрузка своих данных | `users.tests_account_data.DataExportTests`, `frontend/e2e/account-data.spec.ts` | 1.8 | покрыто |
| 24 | Политика конфиденциальности/cookie | `frontend/e2e/legal.spec.ts`, `cookie-banner.spec.ts`, `consent.spec.ts` | 1.14 | покрыто (e2e) |
| 25 | Проверка типа файла | `tests.test_uploads.SanitizeImageTests`, `ValidateImageUploadTests` | 1.10 | покрыто |
| 26 | Проверка размера | `SanitizeImageTests` (лимит из настроек), `local_listings.tests` (лимит фото) | 1.10 | покрыто |
| 27 | Удаление EXIF | `SanitizeImageTests`, `shipments.tests.TestTrackingPhotoSanitized`, `local_listings.tests` (EXIF фото объявления) | 1.10 | покрыто |
| 28 | Безопасные имена файлов | `SanitizeImageTests` (uuid-имя), `PrivateStorageTests`, `shipments.tests.TestTrackingPhotoAccess` | 1.10 | покрыто |
| 29 | Секреты только в `.env` | CI-джоб gitleaks (`.github/workflows`, `.gitleaks.toml`) | 1.1 | покрыто в CI |
| 30 | HTTPS | - | 7.1 | **ждёт задачу 7.1** |
| 31 | HSTS | - | 7.1 | **ждёт задачу 7.1** |
| 32 | Заголовки безопасности (CSP) | - | 7.1 | **ждёт задачу 7.1** |
| 33 | Порт БД не наружу | `tests.test_authz_matrix.InfraExposureTests` | 1.11 | покрыто |
| 34 | Бэкапы Postgres | - | 7.4 | **ждёт задачу 7.4** |
| 35 | Логи без ПДн | - | 7.2 | **ждёт задачу 7.2** |
| 36 | Роли buyer/dealer/broker/moderator/admin | `users.tests.TestRoleHelpers`, `TestRoleIsNotSelfAssignable`, `TestModeratorBoundaries`, `TestBareAdminRoleGivesNothing`, `core.tests.TestPermissionAudit`, `__role_*` и `AdminRolesTests` матрицы | 1.2 | покрыто |

Известные расхождения, найденные при написании матрицы (не подгонялись под поведение):
- `AdminRolesTests.test_moderator_sees_pending_queue_section` помечен `expectedFailure`: раздел «Черга модерації» (прокси `PendingLocalListingProxy`) даёт модератору 403, права группы выданы на `locallisting`, а не на прокси. Модерировать можно через общий список объявлений.

---

## Негативные сценарии

Их заметно больше, чем в E2E, — API проверяется полнее, чем интерфейс.

| Тема | Примеры |
|---|---|
| **Отказ в доступе** | Аноним — 401, посторонний — 403 или 404, обычный пользователь на B2B — 403 |
| **Невалидный ввод** | Нечисловая и отрицательная сумма платежа, неизвестная валюта и `purpose`, несуществующий листинг, `role: admin` при регистрации |
| **Нарушение бизнес-правил** | Дубликат заявки дилера — 409, повторное подтверждение сделки, отзыв на неподтверждённую сделку, сообщение самому себе, превышение лимита активных объявлений и лимита фото |
| **Ограничения БД** | `TestListingChoiceConstraints` — статус, канал и валюта вне `choices` отклоняются и при `create`, и при `update` |
| **Троттлинг** | `TestExpensiveEndpointThrottle` — ответ 429, когда `ScopedRateThrottle.allow_request` замокан в `False`. Сам счётчик лимита (11-й запрос подряд) не проверяется (13-Q11) |
| **Подделка платежа** | Неверная подпись LiqPay отклоняется, листинг не трогается |
| **Идемпотентность** | Повторный колбэк LiqPay не задваивает платёж, повторный импорт лота не создаёт дубль |
| **Отсутствие согласия** | Регистрация без галочки — 400, объявление без согласия с правилами — 400, заявка дилера без согласия на обработку — 400 |
| **Отсутствие ключей** | Провайдеры без API-ключа отдают демо-данные, а не падают |

---

## Тесты, которые проверяют не результат, а свойство

Их стоит выделить: они ловят класс ошибок, а не конкретный случай.

**`TestListingListQueryCount`, `TestCatalogQueryCount`** — количество SQL-запросов не зависит от количества записей. Ловят N+1 при любом будущем изменении сериализатора.

**`TestCalculateLandedCostDecimalPrecision`** — в разбивке нет `float`. Ловит потерю копеек.

**`TestAuctionFeeBoundary`, `TestIAAITierBoundaryDB`** — границы тиров: ставка на первом рубле нового тира.

**`TelegramTokenDisabledInTestsTest`** (`telegram_bot/tests.py`) — токен Telegram пуст под тест-раннером. Страхует от возврата к сетевым вызовам в тестах.

**`TestPricingCacheInvalidation`** — правка ставки в БД делает кэш недействительным.

---

## Покрытие

```bash
pip install coverage
coverage run --source=. \
  --omit="*/migrations/*,*/tests.py,tests/*,.venv/*,venv/*,manage.py,frontend/*" \
  manage.py test
coverage report --skip-empty
```

```
TOTAL    7969    582    93%
```

`coverage` не входит в `requirements.txt` — это инструмент разработчика, в проде он не нужен.

## Чего не покрыто

Модули с нулевым покрытием — ровно те, что ниже. Это не оценка, а вывод `coverage report`.

| Модуль | Строк | Причина |
|---|---:|---|
| `integrations/management/commands/import_lot.py` | 64 | Требует внешних сервисов или больших фикстур |
| `integrations/management/commands/upload_lot_photos.py` | 43 | То же |
| `telegram_bot/management/commands/set_webhook.py` | 27 | Ходит в Telegram API |
| `pricing/management/commands/fetch_nbu_rates.py` | 25 | Сама задача покрыта (`TestFetchNbuRatesTask`), обёртка-команда — нет |
| `telegram_bot/management/commands/unset_webhook.py` | 24 | Ходит в Telegram API |
| `core/wsgi.py`, `core/asgi.py` | 8 | Точки входа, тестировать нечего |

Рантайм бота (`handlers`, `middleware`, `run_bot`) покрыт: апдейты идут через настоящий webhook и диспетчер aiogram, подменён только выход в Telegram API. Остались `set_webhook`/`unset_webhook` — разовые административные команды.

Кроме того, не проверяются автотестами:

| Область | Причина |
|---|---|
| Реальная оплата LiqPay | Нужны боевые ключи и публичный HTTPS для колбэка |
| Отправка email | Бэкенд в тестах консольный, доставка не проверяется |
| Интерфейс админки | Действия админа вызываются напрямую, сам интерфейс — нет |

---

## Что стоит добавить

1. **Тесты админ-действий** `hide_listing` и `ban_reported_user` через `django.test.Client` с логином админа: сейчас проверяется только сервисный слой под ними.
2. **Property-based тесты калькулятора** — например, hypothesis на диапазонах объёма и года: границы тиров это ровно тот случай, где перебор находит больше, чем набор примеров.
3. **Тест миграций с нуля на PostgreSQL** — в CI это уже происходит косвенно в E2E-джобе, но отдельной явной проверки нет.
