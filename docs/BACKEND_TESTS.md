# Backend-тесты

Разбор 433 тестов Django: что покрыто, как распределено по типам, где дыры.

E2E-тесты Playwright — отдельно, [`docs/TEST_CASES.md`](TEST_CASES.md).

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

### Изоляция

Под тест-раннером (`'test' in sys.argv`, флаг `_TESTING` в `core/settings.py`) результат не зависит от `.env`:

- обнуляются `OPENDATABOT_API_KEY`, `APIFY_TOKEN`, `LIQPAY_PUBLIC_KEY`/`LIQPAY_PRIVATE_KEY`, `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`, `TELEGRAM_BOT_TOKEN`, `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY`; `CAPTCHA_PROVIDER='off'`; почта — `locmem`. Любой новый ключ внешнего провайдера добавляется в этот блок. Тесту, которому нужен ключ (например, подпись LiqPay), его задаёт `override_settings` с фиксированным тестовым значением.
- кэш — всегда `LocMemCache`, Celery — eager с `memory://`, даже при заданном `REDIS_URL`.
- сетевой предохранитель (`core/test_runner.py`, `IsolatedDiscoverRunner`): исходящие соединения запрещены, кроме `localhost`, `127.0.0.1`, `::1` и хоста БД из `DATABASES`. Попытка даёт `ExternalNetworkBlocked: Внешний сетевой запрос в тесте: <host>:<port>. Замокайте провайдер`. Тот же раннер после прогона чистит кэш `Update.event_type` aiogram (защита от segfault 139).
- `tests.base.CleanCacheTestCase` очищает кэш в `setUpClass` (после `super()`), `setUp` и `tearDownClass`: откат транзакции не трогает LocMem-кэш, и тарифы удалённых seed-строк иначе переживали бы класс. Классы с seed тарифов наследуются от него, seed — в `setUpTestData`. Страховочные тесты: `tests/test_environment.py`, `pricing.tests.TestNoStaleTiersAfterSeededClass`.

Playwright запускается только из `frontend/` (см. [`TEST_CASES.md`](TEST_CASES.md)).

БД для тестов создаётся и удаляется автоматически. Прогон занимает около 4,5 минут.

---

## Распределение

| Приложение | Тестов | Основные темы |
|---|---:|---|
| `local_listings` | 87 | Модерация, права владельца, фильтры, фото, продвижение, антиспам, видимость по статусам |
| `pricing` | 64 | Калькулятор, акциз, аукционные сборы, кэш тарифов, курс НБУ |
| `integrations` | 46 | VIN-провайдеры, импорт лотов, троттлинг платных API |
| `users` | 38 | Заявки дилеров, B2B-гейтинг, JWT, согласия, эскалация привилегий |
| `tests/test_e2e.py` | 38 | Сквозные сценарии через API |
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

### Калькулятор — 64 теста

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
| `TestAuctionFeeBoundary`, `TestIAAITierBoundaryDB` | Границы тиров — классический источник ошибок на единицу |
| `TestZeroPriceEdgeCase` | Нулевая цена |
| `TestPricingCacheInvalidation` | Правка ставки инвалидирует кэш |
| `TestLandedCostE2ECopartBroker` | Сквозной расчёт через API |

### Модерация и права — `local_listings`, 87 тестов

`TestModerationService`, `TestRemoderation` — публикация, отклонение с причиной, возврат на модерацию при правке существенных полей.

`TestLocalListingOwnership`, `TestListingImage*` — чужое объявление и чужие фото недоступны.

`TestListingVisibilityByStatus` — объявление вне `active` видят только владелец и `staff`. Проверяются все статусы по отдельности.

`TestAntispamListing`, `TestContactEndpoint` — телефон не отдаётся в списке и не отдаётся до модерации.

`TestBannedUser` — забаненный не получает JWT, его объявления скрыты, новые подать нельзя.

### Разграничение доступа

| Класс | Что закрывает |
|---|---|
| `TestB2BGating`, `TestB2BGatingE2E` | Оптовая доска только верифицированным дилерам |
| `TestWholesaleListingDetailGating` | Прямой доступ по ID к оптовому лоту — 404 |
| `TestRoleIsNotSelfAssignable` | Пользователь не назначает себе `role: admin` ни при регистрации, ни через профиль |
| `TestShipmentAccess` | Контейнеры и VIN внутри — только тем, кто их отслеживает |
| `TestConversationDetailAPI` | Чужая переписка недоступна |
| `TestRegistryRequiresAuth`, `VinReportAccessTest` | Платные внешние API под аутентификацией |

---

## Негативные сценарии

Их заметно больше, чем в E2E, — API проверяется полнее, чем интерфейс.

| Тема | Примеры |
|---|---|
| **Отказ в доступе** | Аноним — 401, посторонний — 403 или 404, обычный пользователь на B2B — 403 |
| **Невалидный ввод** | Нечисловая и отрицательная сумма платежа, неизвестная валюта и `purpose`, несуществующий листинг, `role: admin` при регистрации |
| **Нарушение бизнес-правил** | Дубликат заявки дилера — 409, повторное подтверждение сделки, отзыв на неподтверждённую сделку, сообщение самому себе, превышение лимита активных объявлений и лимита фото |
| **Ограничения БД** | `TestListingChoiceConstraints` — статус, канал и валюта вне `choices` отклоняются и при `create`, и при `update` |
| **Троттлинг** | `TestExpensiveEndpointThrottle`, `TestRegistryThrottleE2E` — после лимита 429 |
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

**`TestTokenDisabledInTests`** — токен Telegram пуст под тест-раннером. Страхует от возврата к сетевым вызовам в тестах.

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
TOTAL    4463    753    83%
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
