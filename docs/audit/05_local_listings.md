# Аудит: Пакет 05 «Объявления UA» (local_listings, favorites, saved_searches, reports)

## Состав

**local_listings/** (без миграций — 2 214 строк кода + 1 092 строки тестов)
| Файл | Строк | Назначение |
|---|---|---|
| local_listings/models.py | 214 | Region, City, PromotionTariff, LocalListing, LocalListingImage |
| local_listings/views.py | 453 | API каталога, детали, фото, контакт, продвижение, VIN, регионы |
| local_listings/serializers.py | 280 | list/detail/owner/create/update сериализаторы |
| local_listings/services.py | 84 | approve/reject + уведомления владельцу |
| local_listings/tasks.py | 75 | Celery: предупреждение об истечении, снятие просроченных |
| local_listings/filters.py | 96 | ручной фильтр каталога + сортировка ТОП/bump |
| local_listings/antispam.py | 54 | детектор контактов в тексте |
| local_listings/admin.py | 196 | админка, очередь модерации (proxy), actions approve/reject |
| local_listings/templates/admin/local_listings/reject_reason.html | 32 | промежуточная форма причины отказа |
| local_listings/management/commands/seed_regions.py | 181 | заливка областей/городов |
| local_listings/urls.py | 29 | маршруты |
| local_listings/apps.py | 7 | AppConfig |
| local_listings/tests.py | 1092 | 87 тестов |

Миграции: `0001_initial` — базовые модели; `0002_moderation_fields` — поля модерации; `0003_lifecycle_and_promotion` — срок действия, тарифы, ТОП/bump; `0004_seed_promotion_tariffs` — сид 4 тарифов с placeholder-ценами; `0005_locallisting_has_contact_in_text` — флаг антиспама.

**favorites/**: models.py 40, views.py 75, serializers.py 67, urls.py 8, admin.py 11, apps.py 7; миграция `0001_initial` — модель Favorite. Своих тестов нет (покрыто в tests/test_favorites_notifications_saved_searches.py).

**saved_searches/**: models.py 21, views.py 38, serializers.py 10, tasks.py 88, urls.py 8, admin.py 11, apps.py 7; миграция `0001_initial` — модель SavedSearch.

**reports/**: models.py 73, admin.py 71, serializers.py 40, views.py 8, urls.py 7, apps.py 7, tests.py 106 (7 тестов); миграция `0001_initial` — модель Report с частичными уникальными ограничениями.

**Модели:** Region, City, PromotionTariff, LocalListing (статусы draft/active/pending/rejected/expired/sold/hidden), LocalListingImage, Favorite, SavedSearch, Report.

**Эндпоинты** (core/urls.py:23,26-28):
| Метод | Путь | Доступ |
|---|---|---|
| GET/POST | `/api/v1/local/listings/` | GET — все (только active), POST — авторизованный |
| GET/PATCH/DELETE | `/api/v1/local/listings/<pk>/` | GET: active всем, свои/любые — владельцу/staff; PATCH/DELETE — владелец/staff |
| GET | `/api/v1/local/listings/<pk>/contact/` | авторизованный, throttle `contact` 20/час |
| POST | `/api/v1/local/listings/<pk>/images/` | владелец/staff |
| PATCH/DELETE | `/api/v1/local/listings/<pk>/images/<img_id>/` | владелец/staff |
| POST | `/api/v1/local/listings/<pk>/promote/` | владелец/staff |
| GET | `/api/v1/local/my-listings/` | авторизованный |
| GET | `/api/v1/local/tariffs/` | все |
| GET | `/api/v1/local/vin-prefill/<vin>/` | все |
| GET | `/api/v1/local/regions/`, `/regions/<id>/cities/` | все |
| GET/POST/DELETE | `/api/v1/favorites/`, GET `/favorites/status/` | авторизованный |
| GET/POST, PATCH/DELETE | `/api/v1/saved-searches/`, `/saved-searches/<pk>/` | авторизованный, только свои |
| POST | `/api/v1/reports/` | авторизованный |

Страницы фронта (точечно): `frontend/app/ua`, `frontend/app/local/[id]` (SSR + LocalListingDetail.tsx), `frontend/app/local/[id]/edit`, `frontend/app/local/new`, `frontend/app/sitemap.ts`.

## Функции

| Функция | Состояние | Файл:строки | Комментарий |
|---|---|---|---|
| Подача объявления | готово | local_listings/serializers.py:149-222, views.py:124-138 | статус сразу pending, согласие с правилами, лимит active+pending (`LOCAL_LISTING_MAX_ACTIVE`), антиспам soft/hard/off |
| Модерация (очередь, approve, reject с причиной) | готово | local_listings/admin.py:45-80, 144-196; services.py:19-38 | модерирует любой staff через Django Admin; отдельной роли moderator/broker нет |
| Уведомление владельца о решении | готово | local_listings/services.py:41-78 | email + in-app + Telegram; ошибки глушатся `except: pass` |
| Уведомление модераторов о новом pending | отсутствует | local_listings/serializers.py:186-222 | никто не узнаёт о новой заявке, пока не откроет админку |
| Ремодерация при правке | частично | local_listings/serializers.py:250-266, services.py:16 | active→pending только для make/model/year/price/description; фото, пробег, регион — без ремодерации; expired — без ремодерации (см. 05-S4) |
| Публикация / каталог | готово | local_listings/views.py:124-138 | только active; нет проверки `expires_at` в запросе (снятие — раз в сутки задачей) |
| Фильтры/поиск/сортировка | частично | local_listings/filters.py:9-96 | цены сравниваются без учёта валюты (05-Q3); `price_min=abc` → 500 (05-Q4) |
| Анти-N+1 каталога и кабинета | готово | local_listings/views.py:42-86 | подзапросы рейтинга/сделок; тесты на число запросов local_listings/tests.py:1025-1090 |
| Показ телефона | частично | local_listings/views.py:364-378 | только авторизованным, только active, throttle 20/час; нет журнала просмотров (05-S6) |
| Фото: загрузка/удаление/главное | частично | local_listings/views.py:251-354 | лимит количества и размера есть; тип — по заголовку клиента, EXIF не удаляется, имя файла исходное (05-S1, 05-S2) |
| Срок действия, предупреждение, снятие | готово | local_listings/tasks.py:7-75, models.py:189-193, core/settings.py:385-393 | Celery beat ежедневно |
| Платное продвижение (renew/bump/top) | частично | local_listings/views.py:383-453, payments/views.py:20-49 | цены в админке (PromotionTariff), сумма серверная; разрешено для любого статуса (05-Q5); бесплатного продления нет (05-Q6) |
| Снятие/продажа владельцем | частично | local_listings/serializers.py:243-248 | можно hidden/sold, вернуть из hidden нельзя (05-Q7) |
| Удаление владельцем | частично | local_listings/views.py:146-148 | жёсткое удаление каскадом уносит сделки и жалобы (05-S5) |
| VIN-автозаполнение | готово | local_listings/views.py:205-227 | NHTSA без ключа, кэш в VinReport; без собственного лимита (05-S8) |
| Публикация объявлений UA в Telegram-канал | отсутствует | telegram_bot/signals.py:5 | сигнал только на `listings.Listing` (импорт) |
| Избранное | частично | favorites/views.py:11-75 | можно добавить скрытое/чужое pending (05-S7); невалидный id → 500 (05-Q8); без пагинации |
| Сохранённые поиски (CRUD) | готово | saved_searches/views.py:11-38 | только свои; фильтры JSON не валидируются |
| Уведомления по сохранённым поискам | частично | saved_searches/tasks.py:8-88 | раз в сутки; теряет объявления, одобренные позже (05-Q1); падает на кривом фильтре (05-Q2) |
| Жалобы (подача) | готово | reports/views.py:6-8, serializers.py:6-34 | на объявление или пользователя, защита от дубля |
| Жалобы (обработка) | частично | reports/admin.py:8-71 | обрабатывает staff в админке: скрыть/забанить/отклонить; уведомлений ни админу, ни автору, ни владельцу (05-Q9) |
| Сделки/переписка из объявления | не аудировалось | deals/, messaging/ | вне пакета |

## Сверка с BRIEF.md

| Пункт брифа | Статус | Комментарий |
|---|---|---|
| 1.2 C2C: подача, модерация, фото, фильтры, избранное, сохранённые поиски, жалобы, продвижение | совпадает в основном | все блоки есть; дыры — см. Q-находки |
| 1.3 Публикация объявлений в канал | не хватает | для C2C нет (telegram_bot/signals.py:5) |
| 2 «Всё настраивается без правки кода» | совпадает частично | лимиты/антиспам/сроки в env (core/settings.py:312-324), тарифы в админке; from-email захардкожен (local_listings/services.py:62) |
| 2 «Тестовые данные помечены» | противоречит | placeholder-цены тарифов (migrations/0004:6-13) отдаются в API без пометки demo |
| 2 `LAUNCH_CHECKLIST.md` | не хватает | файла нет; в .env.example только `LOCAL_LISTING_MAX_ACTIVE` (.env.example:73) |
| 3 «Телефон видит только ... нет утечек через списки, сериализаторы, SSR, sitemap» | совпадает частично | телефона нет в list/detail/owner-сериализаторах (serializers.py:89,134), sitemap берёт публичный список (sitemap.ts:19); но `owner_name` раскрывает часть email (05-S3) |
| 3 «Загрузки: тип, размер, EXIF, безопасные имена» | противоречит | размер — есть; тип — только заголовок клиента; EXIF и имена — нет (05-S1, 05-S2) |
| 3 «Тест 401/403 на каждый эндпоинт с личными данными» | частично | есть для create/patch/delete/images/contact/my-listings/favorites/saved-searches/reports; нет для PATCH чужого saved-search, DELETE чужого favorite, promote anon |
| 3 «Логирование без личных данных» | не хватает | просмотры телефона не журналируются вообще |
| 3 «Роли buyer/dealer/broker/admin» | частично | модерация и жалобы — любой staff; `seller_type=dealer` пользователь выставляет сам (serializers.py:160) без проверки роли |
| 4 Этап 4 «подача → модерация → публикация → поиск → контакт → сделка → продвижение» | частично | цикл работает, «сделка» — в deals/ (вне пакета) |
| CLAUDE.md п.3 «ставки с valid_from/valid_to» | противоречит | PromotionTariff без периода действия (models.py:38-59) |

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 05-S1 | критично | Тип фото проверяется только по `content_type` от клиента; Pillow-проверки нет (`objects.create` не валидирует ImageField); исходное имя и расширение сохраняются. Можно загрузить `x.html`/`x.svg` с заголовком `image/jpeg` — nginx отдаёт `/media/` с того же домена без `nosniff`/CSP → хранимый XSS | local_listings/views.py:251,292,303-307; models.py:203; nginx/nginx.conf:24-27 | Открывать файл через Pillow (`verify()`), пересохранять в JPEG/WebP, имя — uuid, расширение по реальному формату; `X-Content-Type-Options: nosniff` на /media/ |
| 05-S2 | критично | EXIF (включая GPS) не удаляется — в проекте нет ни одного вызова `getexif`/`ImageOps` (проверено grep). Фото машины у дома раскрывает адрес продавца | local_listings/views.py:301-310 | Пересохранять изображение без EXIF при загрузке (вместе с S1) |
| 05-S3 | важно | `owner_name` при пустых имени/фамилии возвращает локальную часть email — в публичном списке, детали, SSR-HTML | local_listings/serializers.py:92-95 | Отдавать «Продавець» / отображаемое имя, не производное от email |
| 05-S4 | важно | Обход модерации: правка expired-объявления не переводит в pending (только active/rejected), а оплата RENEW сразу делает его active | local_listings/serializers.py:259-266; payments/views.py:33-38 | Любая существенная правка не-active → pending; RENEW после правки — через модерацию |
| 05-S5 | важно | Жёсткое DELETE владельцем каскадом удаляет сделки/отзывы и жалобы на объявление — продавец стирает репутацию и улики | local_listings/views.py:146-148; deals/models.py:12-15; reports/models.py:26-31 | Мягкое удаление (статус `deleted`/`hidden`), сделки и жалобы не каскадить |
| 05-S6 | важно | Показ телефона не журналируется (кто/когда/какое объявление); лимит только 20/час на аккаунт — массовый сбор номеров через несколько аккаунтов не обнаружить | local_listings/views.py:364-378; core/settings.py:238 | Модель ContactView (user_id, listing_id, ts, без номера), суточный лимит, алерт при аномалии |
| 05-S7 | важно | В избранное можно добавить любое объявление по id, включая чужое pending/rejected/hidden; `FavoriteSerializer` затем отдаёт его заголовок, цену и фото — утечка непубличных объявлений | favorites/views.py:31-38; favorites/serializers.py:25-67 | При добавлении требовать status=active; в списке скрывать данные не-active |
| 05-S8 | желательно | VIN-prefill открыт анонимам без отдельного throttle, VIN не проверяется на допустимые символы, каждый новый VIN пишется в БД и дергает NHTSA | local_listings/views.py:205-227 | Regex VIN `[A-HJ-NPR-Z0-9]{17}`, throttle scope `expensive` |
| 05-S9 | желательно | Фото добавляются/удаляются в active-объявлении без ремодерации — после одобрения можно заменить фото на запрещённый контент | local_listings/views.py:266-354 | Изменение фото active → pending (или пост-модерация фото) |
| 05-S10 | желательно | Жалоба принимает любой id объявления/пользователя (включая скрытые, админов) — перебор существования id по 400/201 | reports/serializers.py:6-9 | Ограничить queryset active-объявлениями и не-staff пользователями |

## Готовность к конфигурации

| ID | Что захардкожено / заглушка | Файл:строка | Куда вынести |
|---|---|---|---|
| 05-C1 | Placeholder-цены тарифов (49/29/99/299 UAH) в data-миграции, API не помечает их как демо | local_listings/migrations/0004_seed_promotion_tariffs.py:3-13; views.py:383-390 | Флаг `is_demo`/баннер до заполнения владельцем; пункт в LAUNCH_CHECKLIST |
| 05-C2 | PromotionTariff без `valid_from`/`valid_to` (требование CLAUDE.md п.3) | local_listings/models.py:38-51 | Поля периода в модели админки |
| 05-C3 | From-адрес `noreply@autoforyou.ua` захардкожен, игнорирует `DEFAULT_FROM_EMAIL` | local_listings/services.py:62 | `settings.DEFAULT_FROM_EMAIL` (.env) |
| 05-C4 | Порог предупреждения «за 3 дня» захардкожен | local_listings/tasks.py:16 | .env `LOCAL_LISTING_EXPIRY_WARN_DAYS` |
| 05-C5 | Лимит 10 объявлений в уведомлении сохранённого поиска, частота «раз в сутки» | saved_searches/tasks.py:33; core/settings.py:380-383 | .env |
| 05-C6 | ANTISPAM_MODE, THROTTLE_CONTACT_RATE, LOCAL_LISTING_MAX_PHOTOS/PHOTO_MAX_SIZE_MB/EXPIRY_DAYS, SELLER_BADGE_THRESHOLD читаются из env, но отсутствуют в .env.example; LAUNCH_CHECKLIST.md нет | core/settings.py:238,312-324; .env.example:72-73 | Добавить в .env.example и LAUNCH_CHECKLIST |
| 05-C7 | Описание эндпоинта промо обещает «LiqPay SANDBOX» — поведение при ненастроенном LiqPay (честный статус) не проверено; Payment создаётся до вызова checkout | local_listings/views.py:393-441 | Проверить адаптер payments (пакет payments) |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 05-Q1 | важно | Сохранённый поиск ищет по `created_at > last_notified_at`, а объявление становится active только после модерации. Если между подачей и одобрением прошёл запуск задачи с другими совпадениями, объявление никогда не попадёт в уведомление. Нужно поле `published_at` (moderated_at) | saved_searches/tasks.py:27-31,43 |
| 05-Q2 | важно | Фильтры сохранённого поиска — JSON без валидации; `int('abc')` в `_apply_filters` роняет всю задачу — уведомления перестают приходить всем пользователям. Логика фильтра продублирована с filters.py и расходится (нет `search`, `region` без int) | saved_searches/serializers.py:6-10; tasks.py:60-88; local_listings/filters.py:9-96 |
| 05-Q3 | важно | `price_min/price_max` и сортировка по цене сравнивают числа в разных валютах (UAH/USD/EUR вперемешку) | local_listings/filters.py:41-50,88-94 |
| 05-Q4 | важно | `price_min=abc` → django `ValidationError` при `filter()` не ловится (ловятся только ValueError/TypeError) → 500 (исключение проверено в shell, сам 500 по HTTP не проверен) | local_listings/filters.py:41-50 |
| 05-Q5 | важно | Промо можно оплатить для pending/rejected/hidden/sold объявления; эффект (ТОП/bump) применится к невидимому объявлению | local_listings/views.py:405-417 |
| 05-Q6 | важно | Продление истёкшего объявления только платное (RENEW); бесплатного «Продовжити», о котором пишет уведомление, нет — вопрос владельцу | local_listings/tasks.py:66; payments/views.py:33-38 |
| 05-Q7 | важно | Владелец может скрыть объявление (hidden), но вернуть его в каталог не может | local_listings/serializers.py:243-248 |
| 05-Q8 | важно | Избранное: `listing_id='abc'` → ValueError → 500 (проверено в shell); несуществующий id на Postgres, вероятно, IntegrityError → DoesNotExist → 500 (не проверено); нет CHECK «ровно один FK»; DELETE без `listing_type` удаляет по imported | favorites/views.py:26-58,66-75; favorites/models.py:27-36 |
| 05-Q9 | важно | Никто не уведомляется о новых жалобах и новых pending-объявлениях; владелец не получает уведомления при скрытии по жалобе (без причины) | reports/views.py:6-8; reports/admin.py:8-18; local_listings/serializers.py:186-222 |
| 05-Q10 | важно | Фронт определяет «владельца» сравнением `owner_name` с именем/префиксом email текущего пользователя — тёзки видят кнопки владельца, API не отдаёт `is_owner` | frontend/app/local/[id]/LocalListingDetail.tsx:38 |
| 05-Q11 | важно | Публикация C2C-объявлений в Telegram-канал отсутствует (бриф п.1.3) | telegram_bot/signals.py:5 |
| 05-Q12 | желательно | Индексы: `icontains` по make/model/description не использует btree-индексы (`ll_make_idx` бесполезен), нет составного индекса `(status, created_at)` под основную сортировку | local_listings/filters.py:28,30,72-75; models.py:180-187 |
| 05-Q13 | желательно | Каталог не проверяет `expires_at` — просроченное объявление видно до суточного запуска `expire_listings` | local_listings/views.py:137-138; tasks.py:44-57 |
| 05-Q14 | желательно | Смена статуса в форме админки обходит `approve_listing/reject_listing` — нет moderated_by и уведомлений | local_listings/admin.py:113-118 |
| 05-Q15 | желательно | Ошибки уведомлений глушатся `except Exception: pass` без логирования | local_listings/services.py:65-78; saved_searches/tasks.py:47-52 |
| 05-Q16 | желательно | Гонка при двойной жалобе: проверка в сериализаторе, а уникальное ограничение даёт IntegrityError → 500 | reports/serializers.py:22-29; reports/models.py:51-62 |
| 05-Q17 | желательно | `ReportSerializer` не используется (мёртвый код); автор не видит статус своих жалоб | reports/serializers.py:37-40 |
| 05-Q18 | желательно | Экшен `ban_reported_user` банит владельца объявления без подтверждения; дублирует логику users/admin.py:9-19 | reports/admin.py:23-41 |
| 05-Q19 | желательно | Sitemap берёт только первую страницу (20) C2C-объявлений | frontend/app/sitemap.ts:18-21 |
| 05-Q20 | желательно | Антиспам: `tg` без границы слова — ложные срабатывания; `contact_phone` не валидируется по формату | local_listings/antispam.py:34-38; models.py:150 |
| 05-Q21 | желательно | `LocalListingListSerializer` отдаёт полное `description` в списке; избранное и сохранённые поиски без пагинации и лимита количества | local_listings/serializers.py:83; favorites/views.py:14-22; saved_searches/views.py:14-22 |
| 05-Q22 | желательно | Пользователь сам ставит `seller_type=dealer` без проверки роли | local_listings/serializers.py:160 |

## Тесты

**Покрыто:**
- local_listings/tests.py — 87 тестов: создание/pending/401, модерация и видимость rejected, ремодерация, лимит объявлений, владение (PATCH/DELETE 403), my-listings, фильтры, VIN, регионы, загрузка/удаление/primary фото (401/403, тип, лимит), срок действия и задачи, промо (создание Payment, 403, 400), применение тарифов в callback (идемпотентность), ТОП-сортировка, контакт (анон 401, только active, нет телефона в list/detail), антиспам, бан, видимость по статусам, число SQL-запросов.
- reports/tests.py — 7 тестов: создание на объявление/пользователя, анон 401, дубль, без цели, обе цели, на себя.
- tests/test_favorites_notifications_saved_searches.py — избранное 7 тестов (401, добавление, дубль, чужой видит пусто, удаление, status), сохранённые поиски 6 (401, CRUD, чужой не видит/не удаляет), задача 3 (создаёт уведомление, не дублирует, не совпадает).
- Прогон: `DATABASE_URL= python manage.py test local_listings reports tests.test_favorites_notifications_saved_searches` — см. итог ниже (без DATABASE_URL тест идёт на sqlite; с DATABASE_URL из .env требуется хост `db` — не поднимался).

**Не покрыто (нужны Django-тесты):**
- фото: подмена content-type (HTML как image/jpeg), удаление EXIF, переименование файла;
- избранное: добавление чужого pending/hidden, невалидный/несуществующий `listing_id`, DELETE чужого;
- saved-search: PATCH чужого (404), кривой JSON фильтров не ломает задачу, объявление одобрено после запуска задачи;
- фильтры: `price_min=abc` → 400, мультивалютность;
- промо: анон 401, промо не-active объявления, неизвестный тариф 404;
- обход модерации: правка expired + RENEW → должно быть pending;
- DELETE объявления со сделками/жалобами;
- контакт: 429 после лимита, журнал просмотров;
- жалобы: на скрытое объявление, гонка дублей, admin-actions hide/ban/dismiss.

**Playwright (сейчас C2C-сценариев нет — только ссылка на /ua и SSR /ua в frontend/e2e/ssr.spec.ts:18):**
- успех: подача объявления → появляется в «Мої оголошення» как pending → (админ одобряет) → видно в /ua → «Показати телефон» у залогиненного;
- ошибка/обход: аноним нажимает «Показати телефон» → предложение войти; чужой пользователь открывает /local/<id>/edit → 403; загрузка не-изображения → ошибка;
- избранное: добавить/убрать, сохранить поиск; жалоба на объявление; оплата ТОП в sandbox.

## Итог (≤15 строк)

Готовность пакета ≈ 70 %: полный цикл C2C (подача → модерация с причиной и уведомлениями → каталог с фильтрами без N+1 → телефон по отдельному эндпоинту → продвижение через LiqPay с ценами из админки) работает и хорошо покрыт тестами (~110).
Критично: **05-S1** загрузка фото без реальной проверки формата и с исходным именем → хранимый XSS через /media/; **05-S2** EXIF/GPS не удаляется.
Важно (безопасность): 05-S3 email-префикс в `owner_name` (список/SSR), 05-S4 обход модерации через правку expired + RENEW, 05-S5 жёсткое удаление стирает сделки и жалобы, 05-S6 нет журнала просмотров телефона, 05-S7 избранное раскрывает непубличные объявления.
Важно (функции): 05-Q1/Q2 сохранённые поиски теряют объявления и падают на кривом фильтре, 05-Q3/Q4 фильтр цены без валюты и 500 на мусоре, 05-Q5 промо для скрытых объявлений, 05-Q6/Q7 нет бесплатного продления и возврата из hidden, 05-Q9 нет уведомлений о жалобах/новых pending, 05-Q10 «владелец» на фронте по имени, 05-Q11 нет публикации C2C в Telegram-канал.
Конфигурация: 05-C1 placeholder-цены тарифов без пометки demo, 05-C2 нет valid_from/valid_to, 05-C6 нет LAUNCH_CHECKLIST.
Модерирует любой staff через админку; отдельной роли модератора нет.
