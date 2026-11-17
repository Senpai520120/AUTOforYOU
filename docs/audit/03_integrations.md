# Аудит: 03 «Интеграции» (`integrations/`)

Ветка `finish-site` @ `d4cbfab`. Тесты не запускались (прогоны ведутся отдельно в STATUS.md). Одна проверка поведения httpx выполнена локально интерпретатором `.venv` без сети (см. 03-S1).

## Состав

| Файл | Строк | Назначение |
|---|---|---|
| `integrations/providers.py` | 374 | Интерфейсы (ABC) и реализации: VIN-отчёт (stub), NHTSA vPIC, история торгов (stub BidFax), Opendatabot (stub + real), лоты (Manual + Apify), фабрики `get_*_provider` |
| `integrations/views.py` | 241 | 4 API-вью: VIN-отчёт, VIN-декод NHTSA, реестр UA (Opendatabot), импорт лота |
| `integrations/tasks.py` | 104 | Celery: `import_lot_task`, `send_notification` (Telegram) |
| `integrations/importer.py` | 77 | Сервис `import_lot`: upsert Vehicle + VehicleImage + Listing |
| `integrations/models.py` | 40 | `RegistryReport`, `VinReport` (кэш ответов провайдеров) |
| `integrations/admin.py` | 19 | Админка кэшей (только чтение) |
| `integrations/serializers.py` | 21 | `LotImportRequestSerializer` |
| `integrations/tests.py` | 590 | 46 тестов |
| `integrations/management/commands/import_lot.py` | 111 | CLI-импорт лота (manual/apify) |
| `integrations/management/commands/upload_lot_photos.py` | 74 | Перекачка фото лотов из `source_url` в хранилище |
| `integrations/apps.py` | 5 | AppConfig |
| `migrations/0001_initial.py` | 31 | Создание `VinReport` |
| `migrations/0002_registryreport.py` | 28 | Создание `RegistryReport` |

**Модели:** `RegistryReport` (`integrations/models.py:4`): vin, plate, provider, payload JSON, demo, created_at, без индексов и уникальности. `VinReport` (`integrations/models.py:24`): vin, provider, report_data JSON, demo, `unique_together (vin, provider)` (`:35`).

**Эндпоинты** (`core/urls.py:15-18`):
| Путь | Вью | Доступ | Throttle |
|---|---|---|---|
| `GET /api/v1/vehicles/<vin>/report/` | `VinReportView` (`views.py:34`) | IsAuthenticated | `expensive` |
| `GET /api/v1/vehicles/<vin>/decode/` | `VinDecodeView` (`views.py:91`) | AllowAny (по умолчанию, `core/settings.py:222`) | `expensive` |
| `GET /api/v1/vehicles/<vin>/registry/?plate=` | `RegistryReportView` (`views.py:140`) | IsAuthenticated | `expensive` |
| `POST /api/v1/lots/import/` | `LotImportView` (`views.py:206`) | IsAdminUser | нет |

Фронтенд ни один из этих четырёх эндпоинтов не вызывает (grep по `frontend/` — совпадений нет). Реально используется только `NHTSAVinDecodeProvider` через `local_listings/views.py:217` (`/api/v1/local/vin-prefill/<vin>/`, `frontend/api/local.ts:46`) и `send_notification` из `deals/services.py:16`, `local_listings/services.py:75`, `local_listings/tasks.py:10,47`, `messaging/services.py:127`, `saved_searches/tasks.py:48`.

## Функции

| Функция | Состояние | файл:строки | Комментарий |
|---|---|---|---|
| VIN-декод NHTSA vPIC | готово | `providers.py:70-117`, `views.py:91-117` | Реальный бесплатный API, таймаут 10 с, кэш в `VinReport`. Нет demo-реализации и логов ошибок |
| VIN-отчёт (ДТП, пробег, владельцы — carVertical и т.п.) | заглушка | `providers.py:23-50`, `:244-245` | Фабрика всегда возвращает `StubVinProvider`; реального клиента carVertical нет вообще |
| История торгов (BidFax) | заглушка | `providers.py:128-144`, `:248-249` | Только stub, реализации нет |
| Реестры UA (Opendatabot) | частично | `providers.py:175-239`, `views.py:140-183` | Real-клиент есть, URL не сверены с документацией (`:149-152`), ключ утекает в ответ (03-S1), ошибки кэшируются навечно (03-Q1) |
| Агрегированный VIN-отчёт | заглушка | `views.py:44-73` | Всегда `demo: True`, кэш с жёстким `provider='stub'` (`:50`, `:71`); данные Opendatabot в него идут без их флага/ошибки |
| Импорт лота вручную (API/CLI) | готово | `providers.py:313-322`, `views.py:209-241`, `commands/import_lot.py` | Работает; нормализация может бросить исключение (03-Q3) |
| Импорт лота через Apify | заглушка | `providers.py:325-366` | ID актора захардкожен `YOUR_ACTOR_ID` (`:351`); без токена возвращает ответ без VIN → вводящая в заблуждение 400 «VIN обязателен» (03-Q6) |
| Сервис `import_lot` | частично | `importer.py:16-77` | Дубли Listing при смене статуса (03-Q2), нет `transaction.atomic`, цена = ставка аукциона |
| Celery `import_lot_task` | мёртвый код | `tasks.py:10-42` | Нигде не вызывается, в `CELERY_BEAT_SCHEDULE` нет |
| Celery `send_notification` (Telegram) | готово | `tasks.py:47-104` | Без токена тихо пропускает; autoretry фактически не срабатывает (03-Q5); лог с telegram_id (03-S4) |
| Перенос фото лотов в хранилище | частично | `commands/upload_lot_photos.py` | Нет лимита размера, проверки типа, удаления EXIF (03-S5); права на фото — issue #11 |
| Статус интеграций в админке | отсутствует | `admin.py:6-19` | В админке только кэши отчётов; модели/страницы «провайдер → настроен/demo/ошибка» нет |
| Переключатель demo/real одной переменной | отсутствует | `providers.py:244-257`, `:369-374` | Режим определяется только наличием ключа; явной `*_PROVIDER=demo|real` нет |

### Сводная таблица провайдеров (бриф, раздел 2)

| Провайдер | Где | Интерфейс | Real | Demo/sandbox | Переключатель `.env` | Без ключа | Статус в админке | Таймаут/ретраи/ошибки | Кэш | Тесты |
|---|---|---|---|---|---|---|---|---|---|---|
| Курс НБУ | `pricing/nbu.py:14-68`, `pricing/tasks.py:23` | нет | да (urllib, `nbu.py:35`, timeout 10) | нет | нет (ключ не нужен) | н/п; при сбое бросает URLError, задача логирует | нет (только таблица `ExchangeRate`) | таймаут есть, ретраи — не проверено | таблица `ExchangeRate` по дате | не проверено (пакет 02) |
| VIN / NHTSA | `integrations/providers.py:70` | нет (класс без ABC) | да | нет | нет (ключ не нужен) | н/п; ошибка → `{'error': str(exc)}` | нет | таймаут 10 с, ретраев нет, логов нет | `VinReport` без TTL | через `local_listings/tests.py` (vin-prefill); в `integrations/tests.py` только throttle (`:509`) |
| carVertical (VIN-история) | `integrations/providers.py:17-50` | да (`VinProvider`) | **нет** | да (stub, `demo: True`) | нет, фабрика жёстко stub (`:244`) | отдаёт фейк «Toyota Camry salvage» для любого VIN с `demo: True` | нет | н/п | `VinReport(provider='stub')` навсегда | только 401/доступ (`tests.py:570-590`) |
| BidFax (история торгов) | `integrations/providers.py:122-144` | да | **нет** | да (stub) | нет (`:248`) | фейк-лот с `demo: True` | нет | н/п | в составе VIN-отчёта | нет |
| Opendatabot | `integrations/providers.py:155-239` | да | да (httpx) | да (stub `:161` — мёртвый; demo-ветка внутри real `:190`) | `OPENDATABOT_API_KEY` (`core/settings.py:328`) — наличие ключа | `demo: True`, не падает | нет | таймаут 10 с, ретраев нет, логов нет, ключ в тексте ошибки (03-S1) | `RegistryReport` без TTL, ошибки тоже кэшируются | 16 тестов (`tests.py:32-240`, `:471-509`) |
| Лоты Copart/IAAI (Apify) | `integrations/providers.py:304-374` | да (`AuctionLotProvider`) | каркас (актор `YOUR_ACTOR_ID`) | Manual-провайдер (не demo, а рабочий ручной ввод) | `APIFY_TOKEN` (`core/settings.py:331`) — наличие ключа | `demo: True` без VIN → 400 «VIN обязателен» | нет | таймаут 60 с, ретраев нет | нет | 2 теста без токена (`tests.py:315-330`, `:452`) |
| LiqPay | `payments/liqpay_client.py:27-40` | нет (один класс) | да | sandbox `LIQPAY_SANDBOX` (`core/settings.py:303`, по умолчанию `true`) | `LIQPAY_SANDBOX` | не проверено (проверки пустых ключей в `from_settings` нет) | не проверено | не аудировалось | н/п | не аудировалось (пакет payments) |
| SMTP | `core/settings.py:335-344` | да (EMAIL_BACKEND Django) | smtp-backend | console-backend (по умолчанию) | `EMAIL_BACKEND` | письма в консоль; `send_mail(..., fail_silently=True)` (`users/services.py:74`, `local_listings/services.py:62`) — ошибки глотаются | нет | не проверено | н/п | не аудировалось |
| Telegram | `integrations/tasks.py:47-104`, `telegram_bot/` | нет | aiogram | нет (без токена — «пропуск») | `TELEGRAM_BOT_TOKEN` (`core/settings.py:399`) | тихо пропускает (`tasks.py:68-71`) | нет | autoretry на OSError/ConnectionError (`tasks.py:50`) | н/п | `telegram_bot/tests.py:342-363` (4 теста) |

## Сверка с BRIEF.md

| Пункт брифа | Оценка | Детали |
|---|---|---|
| §2 «Внешние API — через адаптеры: интерфейс + real + demo» | противоречит частично | ABC-интерфейсы есть для VIN, BidFax, Opendatabot, лотов (`providers.py:17,122,155,304`). У NHTSA, НБУ, LiqPay, Telegram интерфейса нет. Real-реализации carVertical и BidFax нет совсем; Apify — каркас с плейсхолдером |
| §2 «Переключение — одна переменная в `.env`» | не хватает | Нет явных `VIN_PROVIDER` / `LOTS_PROVIDER` / `INTEGRATIONS_DEMO`. Для Opendatabot/Apify режим = «ключ задан»; для VIN/BidFax переключить нельзя (фабрики жёстко stub) |
| §2 «Если ключа нет — не падает» | совпадает | Opendatabot, Apify, Telegram без ключа не падают (тесты `tests.py:32-50`, `:315-330`) |
| §2 «Не показывает фейк как реальное» | частично | Демо помечено `demo: True`, но: (а) `.env.example` содержит непустые плейсхолдеры `OPENDATABOT_API_KEY=your_opendatabot_api_key`, `APIFY_TOKEN=your_apify_token` → включается real-режим с ошибками вместо честного «не настроено» (03-C1); (б) VIN-отчёт отдаёт правдоподобные фейковые make/model/ДТП для любого VIN (`providers.py:34-47`) — UI для него нет, но API публичен для любого залогиненного |
| §2 «Админ видит статус интеграции» | не хватает | Нет ничего. `admin.py` показывает только кэши |
| §2 «Единый список для владельца (LAUNCH_CHECKLIST)» | не хватает | `docs/LAUNCH_CHECKLIST.md` отсутствует; `APIFY_ACTOR_ID` требует правки кода |
| §2 «Тестовые данные помечены и пометки исчезают сами» | частично | Для Opendatabot флаг зависит от ключа, но кэш `RegistryReport` не инвалидируется → после ввода ключа старые demo-ответы остаются навсегда (03-Q1) |
| §3 «Секреты только в `.env`, логирование без личных данных» | противоречит | Ключ Opendatabot попадает в JSON-ответ и БД (03-S1); telegram_id в info-логах (03-S4) |
| §3 «Загрузки: тип, размер, EXIF» | противоречит | `upload_lot_photos` ничего из этого не делает (03-S5) |
| §4 этап 3 «Адаптеры + demo + статус для всех провайдеров» | не хватает | См. сводную таблицу: из 8 провайдеров полный набор нет ни у одного |
| §6 «Никаких молчаливых заглушек» | противоречит | `import_lot_task` — мёртвый код; `StubOpendatabotProvider` не используется (`providers.py:161`); `send_notification` при отсутствии токена молча возвращает `sent: False` без статуса для админа |

## Безопасность и личные данные

| ID | Уровень | Проблема | файл:строка | Как исправить |
|---|---|---|---|---|
| 03-S1 | критично | API-ключ Opendatabot передаётся в query (`params={'apikey': ...}`). При HTTP-ошибке `str(exc)` от httpx содержит полный URL с `?apikey=<КЛЮЧ>` (проверено: `"Client error '401 Unauthorized' for url '...?apikey=SECRET123'"`). Этот текст возвращается любому залогиненному пользователю в поле `error` и сохраняется в `RegistryReport.payload` (видно в админке и отдаётся из кэша всем) | `providers.py:209`, `:212-219`; `views.py:173-183` | Возвращать общий текст ошибки, детали — в лог с маскировкой; ключ передавать в заголовке, если API позволяет |
| 03-S2 | важно | Поле `raw` (полный ответ Opendatabot) и `owners` отдаются любому залогиненному пользователю и хранятся бессрочно. Если там есть данные владельцев — это персональные данные третьих лиц (формат ответа не проверен) | `providers.py:236-238`; `views.py:183` | Отдавать только белый список полей, `raw` не отдавать; TTL/очистка кэша |
| 03-S3 | важно | VIN/номер валидируются только по длине. Django декодирует `%3F`/`%23` в path-параметре, значение подставляется в URL внешнего API через `.format()` без экранирования → можно менять путь/query запроса к Opendatabot/NHTSA; plate длиннее 20 символов упадёт на Postgres (500) | `views.py:45-47`, `:96-101`, `:146-158`; `providers.py:80`, `:203-205` | Regex `^[A-HJ-NPR-Z0-9]{17}$` для VIN, `^[A-ZА-ЯІЇЄ0-9]{4,10}$` для номера; `httpx.URL` с экранированием |
| 03-S4 | желательно | В info-лог пишутся `telegram_id` и user pk (идентификатор человека) | `tasks.py:103` | Логировать только pk или ничего |
| 03-S5 | важно | `upload_lot_photos` скачивает по любому `source_url` с `follow_redirects=True`, без лимита размера (весь ответ в память), без проверки, что это изображение (расширение по Content-Type, иначе `.jpg`), без удаления EXIF; права на фото — issue #11 | `commands/upload_lot_photos.py:59-71` | Стримить с лимитом, проверять через Pillow, пересохранять без EXIF, whitelist доменов |
| 03-S6 | желательно | `VinDecodeView` открыт анонимам (AllowAny по умолчанию) и возвращает текст исключения httpx; внутренних секретов нет, но раскрываются детали | `views.py:91-117`; `providers.py:85-86` | Общий текст ошибки + лог |
| 03-S7 | желательно | `VinReportView` отдаёт залогиненному пользователю правдоподобный фейковый отчёт (ДТП, salvage, 2 владельца) по любому VIN; флаг `demo: True` есть, но риск показа как реального при подключении UI | `providers.py:29-50`, `views.py:59-69` | При отсутствии провайдера отдавать `{'configured': false}`, без фейковых полей |

## Готовность к конфигурации

| ID | Что захардкожено / заглушка / placeholder | файл:строка | Куда вынести |
|---|---|---|---|
| 03-C1 | `.env.example` содержит непустые плейсхолдеры `OPENDATABOT_API_KEY=your_opendatabot_api_key`, `APIFY_TOKEN=your_apify_token` (также `LIQPAY_*`). Копия `.env.example` → `.env` включает real-режим с заведомо неверным ключом | `.env.example` (раздел External APIs / LiqPay) | Оставить пустыми или закомментировать; фабрики должны считать плейсхолдер «не настроено» |
| 03-C2 | ID актора Apify `YOUR_ACTOR_ID` прямо в коде | `providers.py:351` | `.env`: `APIFY_ACTOR_ID` |
| 03-C3 | Базовые URL провайдеров (NHTSA, Opendatabot) в коде; Opendatabot помечен «сверить» | `providers.py:56`, `:149-152` | `.env` (необязательно) + сверка с документацией |
| 03-C4 | Фабрики VIN и BidFax жёстко возвращают stub, переключения нет | `providers.py:244-249` | `.env`: `VIN_REPORT_PROVIDER=demo|carvertical`, `AUCTION_HISTORY_PROVIDER=demo|bidfax` |
| 03-C5 | Нет единого «режима интеграции» и статуса: нет модели/страницы админки `IntegrationStatus` (провайдер, настроен, режим, последняя ошибка, время последнего успеха) | `admin.py:1-19` | Модель админки или страница-дашборд, читающая settings + журнал ошибок |
| 03-C6 | TTL кэша отчётов отсутствует (навсегда) | `views.py:50`, `:103`, `:165-167` | `.env`/админка: `VIN_REPORT_CACHE_DAYS`, `REGISTRY_CACHE_DAYS` |
| 03-C7 | Демо-строки ответов (`'Toyota'`, `'Copart Dallas'`, `sale_price_usd: 8500`) и тексты уведомлений на смеси RU/UA | `providers.py:34-49`, `:136-141`, `:171`, `:196` | Убрать фейковые поля; тексты — в i18n |
| 03-C8 | Дефолты импорта `year=2000`, `make='Unknown'`, `fuel_type='petrol'` — выдуманные данные попадают в каталог как реальные | `providers.py:281-283`, `:293`; `importer.py:38-42` | Требовать поля или помечать лот как неполный |
| 03-C9 | Таймауты (10 с, 60 с, 15 с) захардкожены | `providers.py:82`, `:209`, `:358`; `upload_lot_photos.py:59` | `.env` (желательно) |
| 03-C10 | Отправитель письма `'noreply@autoforyou.ua'` захардкожен вместо `DEFAULT_FROM_EMAIL` (вне пакета, отмечено) | `users/services.py:74`, `local_listings/services.py:62` | `settings.DEFAULT_FROM_EMAIL` |

## Качество кода

| ID | Уровень | Проблема | файл:строка |
|---|---|---|---|
| 03-Q1 | важно | `RegistryReportView` сохраняет в кэш любой ответ, включая `error` и `demo: True`, и отдаёт его всегда (`.first()` без TTL). Один сетевой сбой или запрос до ввода ключа «замораживает» ответ по этому VIN/номеру навсегда; после ввода ключа пометка «демо» сама не исчезнет | `views.py:163-181` |
| 03-Q2 | важно | `import_lot` ищет Listing по `(vehicle, status=IN_TRANSIT)`: если объявление сменило статус (активно/продано), повторный импорт создаёт второе объявление на тот же Vehicle | `importer.py:62-70` |
| 03-Q3 | важно | `_normalize_lot` заявлен как «не кидает исключений», но `int(raw.get('year'))`, `int(engine_cc)`, `int(mileage_km)` бросают ValueError на нечисловом значении → необработанная 500 в `LotImportView` (исключение до `try`) | `providers.py:293-297`; `views.py:218` |
| 03-Q4 | важно | `VinReportView`: кэш по жёсткому `provider='stub'`; данные Opendatabot (в т.ч. реальные при наличии ключа) вшиваются в отчёт с общим `demo: True`, ошибка Opendatabot теряется; `RegistryReport` при этом не пишется — повторные платные вызовы при разных VIN | `views.py:50-71` |
| 03-Q5 | важно | `autoretry_for=(OSError, ConnectionError)`: исключения httpx не наследуют OSError (проверено: `issubclass(httpx.ConnectError, OSError) == False`); для aiogram сетевые ошибки в основном тоже не OSError (не проверено полностью) → ретраи фактически не работают. В самих провайдерах ретраев нет | `tasks.py:12`, `:50` |
| 03-Q6 | важно | Apify без токена возвращает `demo: True, vin: None` без `error` → `LotImportView` отвечает 400 «VIN обязателен», а не «Apify не настроен»; тест принимает любой из 200/201/400 | `providers.py:338-344`; `views.py:223-229`; `tests.py:452-463` |
| 03-Q7 | желательно | Мёртвый код: `import_lot_task` нигде не вызывается; `StubOpendatabotProvider` не используется (обе ветки фабрики создают Real); `get_lot_provider` имеет две одинаковые ветки | `tasks.py:10-42`; `providers.py:161-172`, `:252-257`, `:369-374` |
| 03-Q8 | желательно | Race condition: `VinDecodeView` делает `create()` при `unique_together` → IntegrityError (500) при параллельных запросах; соседний `VinPrefillView` использует `get_or_create` — логика кэша NHTSA продублирована в двух местах | `views.py:103-115`; `local_listings/views.py:213-227` |
| 03-Q9 | желательно | NHTSA на невалидный VIN отвечает 200 с `ErrorCode`, `make=None` — условие `'error' not in data` пропускает, «пустой» ответ кэшируется навсегда | `views.py:109-115`; `providers.py:115-116` |
| 03-Q10 | желательно | `RegistryReport` без индексов по `vin`/`plate` и без уникальности → дубли при гонке, full scan на кэш-поиске | `models.py:4-21` |
| 03-Q11 | желательно | `import_lot` без `transaction.atomic`: частично созданные Vehicle/фото при ошибке на Listing | `importer.py:35-77` |
| 03-Q12 | желательно | Провайдеры ничего не логируют (`except Exception` → dict); админ не узнает о сбоях. Широкие `except Exception` | `providers.py:85`, `:212`, `:365` |
| 03-Q13 | желательно | Цена объявления = `final_bid` аукциона в USD, при 0 — объявление с ценой 0 | `importer.py:60-75` |
| 03-Q14 | желательно | `send_notification` в `integrations`, хотя это Telegram — дублирует ответственность `telegram_bot/`; `asyncio.run` + новый `Bot` на каждое сообщение | `tasks.py:47-104` |
| 03-Q15 | желательно | `LotImportView` без throttle; `import_lot` CLI берёт «первого суперюзера» как продавца по умолчанию | `views.py:206-207`; `commands/import_lot.py:101-111` |

## Тесты

**Покрыто** (`integrations/tests.py`, 46 тестов):
- Opendatabot провайдер без ключа/с ключом, mock httpx (8 тестов, `:32-127`);
- эндпоинт реестра: поля, кэш, повторный запрос, 400, поиск по номеру, запись в БД (8, `:130-240`);
- ManualLotProvider (7, `:271-312`), Apify без токена (2, `:315-330`);
- сервис `import_lot` (7, `:333-395`), эндпоинт импорта: admin/403/401/400/повтор/apify (6, `:398-463`);
- auth реестра (2, `:471-491`), throttle 429 (2, `:494-518`), идемпотентность Celery-задачи (2, `:521-567`), доступ к VIN-отчёту (3, `:570-590`).
- Вне пакета: `send_notification` — `telegram_bot/tests.py:342-363`; NHTSA через vin-prefill — `local_listings/tests.py`.

**Не покрыто:**
- `NHTSAVinDecodeProvider` и `VinDecodeView` напрямую (разбор ответа, ошибка сети, кэширование, невалидный VIN с ErrorCode);
- содержимое `VinReportView` (флаг demo, отсутствие фейка при «не настроено»);
- утечка ключа в сообщении об ошибке (03-S1) — нужен тест «error не содержит apikey»;
- «ошибка не кэшируется» / TTL (03-Q1);
- нечисловые year/mileage в лоте (03-Q3); повторный импорт после смены статуса Listing (03-Q2);
- ApifyLotProvider с токеном (mock httpx), пустой результат, ошибка;
- `upload_lot_photos`, `import_lot` management-команды — тестов нет;
- ретраи Celery;
- статус интеграций в админке (функции нет).

**Нужные сценарии:**
- Django: для каждого провайдера — «ключ пуст → `configured: false`, без фейковых полей», «плейсхолдер из .env.example → не настроено», «real с mock → `demo: false`», «сетевая ошибка → понятный текст, секрет не утёк, не кэшировано», «переключатель .env меняет реализацию»; админ-страница статуса интеграций (200 для admin, 403 для остальных).
- Playwright (после появления UI): VIN-отчёт в demo-режиме показывает баннер «Демо / не настроено»; ошибка провайдера показывает понятное сообщение; админ видит статус интеграций; попытка анонима открыть `/report/` и `/registry/` → 401.

## Итог (≤15 строк)

Готовность пакета ~40%. Каркас адаптеров (ABC + stub/real) есть для 4 провайдеров, Opendatabot и NHTSA реально работают, без ключей сайт не падает, 46 тестов.
Но требование брифа §2 не выполнено ни для одного из 8 провайдеров: нет real carVertical/BidFax, Apify — каркас с `YOUR_ACTOR_ID`, нет переключателя одной переменной `.env`, нет статуса интеграций в админке, нет LAUNCH_CHECKLIST.
Критично: **03-S1** — ключ Opendatabot утекает в JSON-ответ пользователю и в кэш БД через текст исключения httpx (проверено).
Важно: 03-S2 (сырые данные реестра и владельцы отдаются всем залогиненным), 03-S3 (VIN/номер без regex → изменение URL внешнего API), 03-S5 (upload_lot_photos без лимита/типа/EXIF), 03-Q1 (ошибки и demo-ответы кэшируются навсегда), 03-Q2 (дубли Listing при повторном импорте), 03-Q3 (500 на нечисловом year), 03-Q4 (VIN-отчёт смешивает реальные и stub-данные), 03-Q5 (autoretry не ловит ошибки httpx), 03-Q6 (Apify без токена даёт ложную ошибку), 03-C1 (плейсхолдеры в .env.example включают real-режим).
Фронтенд не использует `/report/`, `/registry/`, `/decode/`, `/lots/import/`; реально используются только NHTSA (vin-prefill) и `send_notification`.
НБУ (`pricing/nbu.py`), LiqPay (`payments/liqpay_client.py`), SMTP (`core/settings.py:335`), Telegram (`telegram_bot/`) реализованы вне пакета без общего интерфейса и статуса.

Счётчик (S+Q): критично 1 / важно 9 / желательно 12; плюс 10 конфигурационных находок 03-C1…C10.
