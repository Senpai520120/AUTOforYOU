# Аудит: 04 «Пригон» — listings/, vehicles/, cars/, shipments/

## Состав

### Файлы (строк)
| App | Файл | Строк |
|---|---|---|
| listings | models.py 93, views.py 107, serializers.py 45, permissions.py 19, urls.py 13, admin.py 12, apps.py 5, tests.py 166 | 460 |
| vehicles | models.py 50, views.py 23, serializers.py 17, urls.py 8, admin.py 17, apps.py 5, tests.py 2 (пустой) | 122 |
| cars (legacy) | views.py 71, models.py 29, serializers.py 16, urls.py 8, admin.py 15, apps.py 5, tests.py 2 (пустой) | 146 |
| shipments | models.py 96, admin.py 50, serializers.py 62, views.py 56, urls.py 8, apps.py 5, tests.py 99 | 376 |

Миграции:
- listings/0001–0003 — начальные схемы Listing; 0004 — `express_buyout_until`; 0005 — индексы status/channel/price; 0006 — нормализация `status='active'`→`in_stock` + CheckConstraint на status/channel/currency.
- vehicles/0001 — Vehicle, VehicleImage; 0002 — `VehicleImage.source_url`; 0003 — индекс fuel_type.
- cars/0001–0002 — Car, CarImage.
- shipments/0001 — Shipment, TrackingEvent.

### Модели
- `Vehicle`, `VehicleImage` — vehicles/models.py:4, :40
- `Listing` (+ `ListingCurrency/Channel/Status`) — listings/models.py:29
- `Shipment`, `TrackingEvent` — shipments/models.py:7, :78
- `Car`, `CarImage` (legacy) — cars/models.py:5, :27
- Модели дилера живут в `users`: флаг `CustomUser.is_verified_dealer` (users/models.py:36), `CustomUser.Role` без broker (users/models.py:25-28), `DealerApplication` (users/models.py:87-129); сервис одобрения — users/services.py:20-74; админ-действия — users/admin.py:65-101; эндпоинты `/api/v1/dealers/apply/`, `/api/v1/dealers/application/` — users/urls.py:38-41. Модели `DealerProfile` нет.

### Эндпоинты (core/urls.py)
| Путь | View | Доступ |
|---|---|---|
| GET `/api/v1/listings/` | ListingListView listings/views.py:52 | AllowAny (retail; дилер/staff — всё) |
| GET `/api/v1/listings/<pk>/` | ListingDetailView listings/views.py:69 | AllowAny (wholesale → 404 не-дилеру) |
| POST `/api/v1/listings/create/` | ListingCreateView listings/views.py:84 | IsAuthenticated (любой) |
| GET `/api/v1/b2b/board/` | B2BBoardView listings/views.py:97 | IsVerifiedDealerOrAdmin |
| GET `/api/v1/vehicles/`, `/api/v1/vehicles/<pk>/` | vehicles/views.py:11, :21 | AllowAny (дефолт core/settings.py:223-225) |
| GET `/api/v1/shipments/`, `/api/v1/shipments/<pk>/` | shipments/views.py:30, :51 | IsAuthenticated + фильтр watchers/staff |
| GET `/api/v1/auth/me/shipments/` | MyShipmentsView users/views.py:76 (соседний модуль) | IsAuthenticated, watchers |
| GET `/api/calculate/`, `/api/list/` | cars/views.py:26, :58 (legacy) | AllowAny |
| POST `/api/v1/lots/import/` | integrations/views.py:206 (соседний) | IsAdminUser — единственный источник лотов |

Страницы фронтенда: `/listings` (frontend/app/listings/page.tsx, SSR), `/listings/[id]`, `/b2b` (frontend/app/b2b/page.tsx), `/me/shipments` (frontend/app/me/shipments/page.tsx), `/dealers/apply` (frontend/app/dealers/apply/page.tsx).

## Функции

| Функция | Состояние | Файл:строки | Комментарий |
|---|---|---|---|
| Каталог лотов (список) | частично | listings/views.py:52-63; frontend/app/listings/page.tsx:56-80 | Работает: SSR, пагинация (PAGE_SIZE=20, core/settings.py:240-241; UI — frontend/app/listings/ListingsGrid.tsx:49-61), поиск make/model/VIN, сортировка price/created_at, фильтры status/fuel_type/currency/max_price. Нет фильтров по году, марке, пробегу, аукциону, повреждению. Невалидный `max_price` → 500 (см. 04-Q1). |
| Источник данных каталога | частично | integrations/importer.py:16-77; integrations/views.py:206-236; integrations/providers.py:369-374 | Лоты попадают только через ручной admin-импорт (`/api/v1/lots/import/`, manual или Apify). Нет периодической синхронизации, нет «живого» каталога Copart/IAAI. При отсутствии `final_bid` цена листинга = 0 (importer.py:60,67). Фото — хотлинк `source_url` на аукцион (issue #11). |
| Карточка лота | готово | listings/views.py:69-78; frontend/components/listings/ListingDetail.tsx | Показывает VIN, лот, фото (`image` или `source_url`). |
| N+1 в каталоге | готово | listings/views.py:10-11; listings/tests.py:94-116 | select_related vehicle/seller + prefetch images; тест фиксирует 3 запроса. |
| Создание листинга через API | сломано (по смыслу) | listings/views.py:84-86; listings/serializers.py:34-45 | Любой зарегистрированный пишет в каталог пригона без модерации (см. 04-S1). UI не использует. Нет update/delete. |
| B2B-доска | частично | listings/views.py:97-107; listings/permissions.py:4-19; frontend/app/b2b/page.tsx:17-27 | Бэкенд проверяет `is_verified_dealer or is_staff`. Фронт грузит только 1-ю страницу без фильтров (`b2bBoard({})`, page.tsx:23) и решает доступ по `role==='admin'` вместо `is_staff` (page.tsx:17). Срочный выкуп сортируется вверх; истёкший `express_buyout_until` всё равно поднимает листинг (ordering по `is_express_buyout`, views.py:103). |
| Заявка дилера → верификация | готово (минимально) | users/services.py:20-63; users/admin.py:65-101 | Заявка → admin action «Одобрить» → `is_verified_dealer=True, role='dealer'`. Уведомление — email `fail_silently=True` (users/services.py:74), Telegram нет. Нет отзыва верификации через заявку; поле `status` редактируется в форме админки напрямую без смены флага (users/admin.py:98-101, см. 04-Q6). Документы — только URL (users/models.py:102). |
| Wholesale-гейтинг в каталоге | готово | listings/views.py:61-62, :76-77 | Покрыто тестами. Обходится через `/api/v1/vehicles/` (04-S2). |
| Контейнеры: создание/статусы | частично | shipments/admin.py:14-33; shipments/models.py:17-25, :62-75 | Создание и смена статуса только в админке. Автосоздание TrackingEvent при смене статуса есть (admin.py:26-33), но админка обходит `VALID_TRANSITIONS`; `advance_status()` нигде не вызывается (мёртвый код). |
| Контейнеры: кто видит | готово | shipments/views.py:8-20, :36-41, :55-56; shipments/tests.py | Только watchers и staff; аноним 401, чужой 404. Покрыто 10 тестами. |
| Привязка клиента к контейнеру | заглушка | shipments/models.py:47-50; frontend/app/me/shipments/page.tsx:130 | Watchers добавляет только админ вручную («Зверніться до менеджера»). Нет связи с заявкой/сделкой клиента. |
| Уведомление клиента о смене статуса | отсутствует | shipments/admin.py:26-33 | Ни email, ни Telegram, ни in-app (grep по notifications/, telegram_bot/ — упоминаний Shipment нет). |
| Детальная страница контейнера (история событий) | отсутствует во фронте | shipments/views.py:51; frontend/app/me/shipments/page.tsx | API деталей есть, фронт показывает только список с прогресс-баром, без событий/фото/ETA-истории. Порт выводится сырым кодом (`s.arrival_port_eu`, page.tsx:159). |
| Загрузка фото (VehicleImage, TrackingEvent) | частично | vehicles/models.py:42; shipments/models.py:87; vehicles/admin.py:6-9; shipments/admin.py:7-11 | Только через админку. Тип проверяет ImageField/Pillow; размер, EXIF, переименование — нет (04-S4). |
| Legacy cars `/api/calculate/`, `/api/list/` | работает, устарело | cars/views.py:26-71; core/urls.py:34 | Владелец решил не трогать — только констатация (04-S3, 04-C1). Фронт его не вызывает. |

## Сверка с BRIEF.md

**Совпадает**
- Раздел 1: каталог лотов, отслеживание контейнера, B2B для верифицированных — каркас есть.
- Раздел 3 «Доступ к данным»: контейнеры закрыты от чужих, тесты 401/404 есть (shipments/tests.py:44-99); wholesale-detail закрыт (listings/tests.py:48-75).
- Раздел 3 «Роли»: B2B-доступ по `is_staff`, а не самоназначаемому `role` (listings/permissions.py:8-19).

**Противоречит**
- Раздел 2 «всё из админки, без хардкода»: legacy `/api/calculate/` на захардкоженных ставках и `float`, без `is_estimate` (cars/views.py:29-52) — публичный и в OpenAPI.
- Раздел 3 «Загрузки файлов: тип, размер, EXIF, безопасные имена»: EXIF нигде не удаляется (grep `exif` по проекту — пусто), лимита размера для VehicleImage/TrackingEvent нет, имена оригинальные (`upload_to='vehicle_photos/'`, `'tracking_photos/'`).
- Раздел 3 «Нет утечек через списки»: `/api/v1/vehicles/` публично отдаёт все автомобили, включая wholesale-only и находящиеся в контейнерах (04-S2).
- Раздел 1 «B2B для верифицированных перекупщиков»: любой залогиненный может сам разместить wholesale/retail листинг (04-S1).
- Раздел 6 «Никаких молчаливых заглушек»: импорт ставит `make/model='Unknown'`, `year=2000`, `price=0` при отсутствии данных (integrations/importer.py:38-41, :60).

**Не хватает**
- Уведомления клиенту о смене статуса контейнера (раздел 1 + раздел 5 брифа «Telegram-бот: уведомления»).
- Привязка контейнера к заявке/клиенту, самостоятельное отслеживание клиентом.
- Роль broker (users/models.py:25-28 — только buyer/dealer/admin) — брокер ведёт контейнеры через is_staff.
- Адаптер «источник лотов» с real/demo и статусом в админке — частично в integrations (не аудируется здесь), периодического обновления каталога нет.
- Уведомление брокера о новой дилерской заявке (есть только письмо заявителю после решения).
- Playwright-тесты на B2B, контейнеры, заявку дилера.

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 04-S1 | критично | `POST /api/v1/listings/create/` открыт любому залогиненному: можно опубликовать листинг на **любой** `vehicle` (чужой импортированный лот с фото), с любой ценой, `channel=wholesale`, `status=sold`, `is_express_buyout`, привязать чужой `calculation`; без модерации сразу в публичном каталоге пригона. UI этот эндпоинт не использует. | listings/views.py:84-86; listings/serializers.py:34-45 | Закрыть на `IsAdminUser`/брокера (или убрать URL), валидировать владение `calculation`, ввести модерацию. |
| 04-S2 | важно | `/api/v1/vehicles/` и `/<pk>/` — AllowAny, `fields='__all__'`: отдают VIN, номер лота, повреждения всех авто, в т.ч. только wholesale и привязанных к контейнерам клиентов. Обходит B2B-гейтинг и смысл фикса shipments (shipments/views.py:12-16). | vehicles/views.py:11-23; vehicles/serializers.py:12-17; core/settings.py:223-225 | Ограничить выборку авто, у которых есть retail-листинг, либо закрыть эндпоинт (фронт его не использует). |
| 04-S3 | важно | Legacy `/api/calculate/` публичен, считает на захардкоженных ставках, `float`, без `is_estimate`, в OpenAPI (deprecated). Риск: сторонний/старый клиент покажет пользователю «точную» цену. Владелец решил не трогать — фиксируем. | cars/views.py:26-54; core/urls.py:34 | (по решению владельца) — минимум: отключить URL флагом или добавить `is_estimate: true`. |
| 04-S4 | важно | Фото VehicleImage/TrackingEvent: нет удаления EXIF (GPS с телефона брокера в порту), нет лимита размера, имена файлов оригинальные. Tracking-фото отдаются публично через `/media/` (nginx/nginx.conf:24-25) при закрытом API контейнера. | vehicles/models.py:42; shipments/models.py:87; nginx/nginx.conf:24 | Общий валидатор/`save()`-хук: Pillow re-save без EXIF, лимит из .env, `uuid`-имя; tracking-фото — через приватный storage/подписанные URL. |
| 04-S5 | желательно | `ListingSerializer` отдаёт `seller` (id пользователя) и `calculation` (id расчёта) публично — перечисление id сотрудников/расчётов. | listings/serializers.py:17-19 | Убрать `seller`/`calculation` из публичного сериализатора. |
| 04-S6 | желательно | Фронт B2B решает доступ по `user.role === 'admin'` вместо `is_staff` — расхождение с бэкендом (users/serializers.py:51-54 описывает именно этот баг для шапки). Утечки нет (бэкенд 403), но UX ломается. | frontend/app/b2b/page.tsx:17 | Заменить на `user.is_staff`. |
| 04-S7 | желательно | Верификация дилера — только флаг; отозвать можно лишь снятием `is_verified_dealer` вручную, смена `status` заявки в форме админки флаг не трогает. Документы — внешний URL без проверки. | users/admin.py:98-101; users/models.py:102; users/services.py:40-50 | `status` в readonly, действие «Отозвать верификацию» через сервис. |

## Готовность к конфигурации

| ID | Что захардкожено / заглушка | Файл:строка | Куда вынести |
|---|---|---|---|
| 04-C1 | Ставки legacy-калькулятора: аукцион 10%/600, доставка 2200, акциз 50/75, пошлина 10%, НДС 20% | cars/views.py:34-42 | Не трогать по решению владельца; при выключении — флаг `.env` `LEGACY_CARS_API_ENABLED`. |
| 04-C2 | Порты ЕС — только Клайпеда/Гданьск в TextChoices | shipments/models.py:27-29 | Модель-справочник портов в админке. |
| 04-C3 | Импорт: фолбэки `'Unknown'`, `year=2000`, `price=0`, `status=in_transit`, `channel=retail` | integrations/importer.py:38-45, :60-70 | Не подставлять фейк — отклонять импорт/помечать черновиком; дефолтный канал — настройка. |
| 04-C4 | Адрес отправителя `noreply@autoforyou.ua` в письме о решении по заявке дилера (соседний модуль) | users/services.py:74 | `DEFAULT_FROM_EMAIL` из .env. |
| 04-C5 | «промт 7»/«промт 11» TODO: перенос фото в S3, Telegram-уведомление дилеру | vehicles/models.py:43; users/services.py:8, :73 | Закрыть задачами; `source_url` — хотлинк на Copart/IAAI (issue #11). |
| 04-C6 | Размер страницы каталога 20 — глобально | core/settings.py:241 | Допустимо; при желании — `.env`. |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 04-Q1 | важно | `max_price=abc` → необработанный `django.core.exceptions.ValidationError` при `filter()` → HTTP 500 (проверено в shell: исключение ValidationError, а `except` ловит только ValueError/TypeError). Каталог публичный и SSR. | listings/views.py:29-33 |
| 04-Q2 | важно | Нет уведомлений клиенту при смене статуса контейнера; `advance_status()` — мёртвый код, админка обходит `VALID_TRANSITIONS`. | shipments/models.py:62-75; shipments/admin.py:26-33 |
| 04-Q3 | важно | Истёкший срочный выкуп остаётся вверху B2B-доски (сортировка по булеву флагу, а не по `is_express_active`). | listings/views.py:103; listings/serializers.py:26-31 |
| 04-Q4 | желательно | Дублирование: `MyShipmentsView` повторяет `ShipmentListView` (тот же фильтр watchers). | users/views.py:76-86; shipments/views.py:30-41 |
| 04-Q5 | желательно | N+1 в админке: `vehicle_count` → `obj.vehicles.count()` на каждую строку; `TrackingEvent.__str__` дергает `shipment`. | shipments/admin.py:22-23; shipments/models.py:95-96 |
| 04-Q6 | желательно | Поле `status` DealerApplication редактируемо в форме админки — одобрение через форму не выставляет `is_verified_dealer`. | users/admin.py:98-101 |
| 04-Q7 | желательно | Нет индекса под дефолтную сортировку каталога `-created_at` (Listing) и под `Shipment.status`; `VehicleImage` без `ordering` и без ограничения «одно главное фото». | listings/models.py:62-68; shipments/models.py:54-57; vehicles/models.py:48-50 |
| 04-Q8 | желательно | Бесполезный `try/except` вокруг ленивого `filter()`; фильтры status/channel/currency не валидируются против choices (молча пустой ответ). | listings/views.py:14-34 |
| 04-Q9 | желательно | Фронт `/me/shipments` показывает сырой код порта и не выводит историю событий/фото; B2B-страница без пагинации и фильтров. | frontend/app/me/shipments/page.tsx:159; frontend/app/b2b/page.tsx:23 |
| 04-Q10 | желательно | Смешение языков: docstring/комменты shipments — украинский, listings — русский (не критично, для единообразия). | shipments/views.py:9-17; shipments/tests.py:1-6 |
| 04-Q11 | желательно | Legacy `cars` — мёртвое приложение с моделью, миграциями и публичными URL; `float` для денег. Оставлено по решению владельца. | cars/views.py:29-45; cars/models.py:16-17 |

## Тесты

**Покрыто (Django)**
- listings/tests.py — 12 тестов: wholesale-detail гейтинг (5), число запросов каталога (2), CheckConstraint (5).
- shipments/tests.py — 10 тестов: доступ аноним/чужой/watcher/staff, отсутствие VIN у чужого.
- users/tests.py:129-200 — B2B-гейтинг доски (4) и фильтр wholesale в каталоге (3); сервис/API заявки дилера (users/tests.py:36-125, 364+).
- tests/test_e2e.py:403-500 — B2B-гейтинг и полный цикл «заявка → одобрение → доступ» (≈10).
- vehicles/tests.py, cars/tests.py — пустые (0).

**Playwright**: frontend/e2e/catalog.spec.ts — 2 теста на каталог (200 + отсутствие демо-баннера), остальные — калькулятор. B2B, контейнеры, заявка дилера, карточка лота, фильтры/пагинация — не покрыты.

**Нужны Django-тесты**
- `/api/v1/listings/create/`: buyer → 403 (после фикса 04-S1); чужой `calculation` → 400.
- `/api/v1/vehicles/`: аноним не видит VIN wholesale-only/контейнерных авто.
- `max_price=abc` → 400/игнор, не 500.
- B2B: истёкший срочный выкуп не выше обычного.
- Смена статуса контейнера → создаётся TrackingEvent и уходит уведомление watchers (мок Telegram/email); недопустимый переход отклоняется.
- Одобрение/отзыв дилера через админ-действия; повторная заявка → 409.
- Загрузка фото: EXIF удалён, превышение размера отклонено, имя заменено.

**Нужны Playwright-сценарии**
- Каталог: фильтр + пагинация (успех), невалидный `max_price` в URL — страница не падает (ошибка).
- Карточка лота: retail открывается, wholesale по прямой ссылке — 404 для гостя (обход).
- B2B: buyer видит «Доступ обмежено», верифицированный дилер видит доску, staff без роли admin — доска доступна.
- Заявка дилера: отправка без согласия блокируется; успешная — статус pending в кабинете.
- `/me/shipments`: watcher видит контейнер и прогресс; гость → редирект на /login; чужой контейнер по API — 404.

## Итог

Готовность пакета «Пригон» — около 55%. Каталог (SSR, пагинация, поиск, отсутствие N+1) и закрытие контейнеров/wholesale работают и покрыты тестами. Но лоты попадают в каталог только через ручной admin-импорт, а уведомлений клиенту о смене статуса контейнера нет.
Критично: **04-S1** — любой залогиненный через `POST /api/v1/listings/create/` публикует листинг на любой импортированный лот (включая wholesale) без модерации.
Важно: **04-S2** — публичный `/api/v1/vehicles/` раскрывает VIN/лоты wholesale- и контейнерных авто в обход B2B; **04-S3** — legacy `/api/calculate/` на хардкод-ставках (не трогаем по решению владельца, риск зафиксирован); **04-S4** — нет EXIF/лимита размера/безопасных имён для фото, tracking-фото публичны через /media/; **04-Q1** — `max_price=abc` роняет каталог с 500; **04-Q2** — нет уведомлений о статусе контейнера, переходы в админке не валидируются; **04-Q3** — истёкший срочный выкуп висит вверху B2B.
Верификация дилера — флаг `users.CustomUser.is_verified_dealer` + `users.DealerApplication` (модели DealerProfile нет); отзыва верификации нет, роли broker нет.
Для фронта нужны: B2B-пагинация/фильтры, детали контейнера и Playwright-тесты на B2B, контейнеры и заявку дилера.
