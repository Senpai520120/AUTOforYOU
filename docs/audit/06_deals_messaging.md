# Аудит: 06 — Сделки и общение (deals, messaging, notifications, payments)

Ветка `finish-site` @ `d4cbfab`, 2026-09-25. Код не менялся.

## Состав

### Файлы (строк)
| Приложение | Файл | Строк |
|---|---|---|
| deals | models.py 88, services.py 163, views.py 107, serializers.py 53, urls.py 19, admin.py 29, apps.py 7, tests.py 321 | 787 |
| messaging | models.py 75, services.py 177, views.py 129, serializers.py 117, urls.py 15, admin.py 32, apps.py 7, tests.py 213 | 765 |
| notifications | models.py 33, services.py 16, views.py 38, serializers.py 10, urls.py 9, admin.py 16, apps.py 7 (tests.py нет) | 129 |
| payments | models.py 79, liqpay_client.py 119, views.py 182, serializers.py 48, urls.py 8, admin.py 12, apps.py 7, tests.py 66 | 521 |

Миграции:
- `deals/migrations/0001_initial.py` — Deal + Review, UniqueConstraint (listing, buyer).
- `messaging/migrations/0001_initial.py` — Conversation (+M2M participants) и Message.
- `notifications/migrations/0001_initial.py` — Notification.
- `notifications/migrations/0002_notification_deal_types.py` — добавлены типы deal_* / review_received в choices.
- `payments/migrations/0001_initial.py` — Payment.
- `payments/migrations/0002_local_listing_promote.py` — FK local_listing, tariff, purpose local_listing_promote.

### Модели
- `Deal` (deals/models.py:6) — listing→LocalListing, seller, buyer, status proposed/confirmed/cancelled, confirmed_at.
- `Review` (deals/models.py:56) — OneToOne к Deal, author, target, rating 1–5, text.
- `Conversation` (messaging/models.py:6) — initiator, local_listing | imported_listing, participants M2M, last_message_at.
- `Message` (messaging/models.py:56) — conversation, sender, text, read_at. Вложений нет.
- `Notification` (notifications/models.py:5) — user, type (9 типов), title, text, link, is_read.
- `Payment` (payments/models.py:5) — user, listing, local_listing, tariff, order_id, amount/currency, purpose, status, liqpay_*.

### Эндпоинты (core/urls.py:22-29)
| Метод | Путь | View |
|---|---|---|
| GET/POST | `/api/v1/deals/` | DealListCreateView (deals/views.py:18) |
| POST | `/api/v1/deals/<pk>/confirm/` | DealConfirmView (deals/views.py:40) |
| POST | `/api/v1/deals/<pk>/cancel/` | DealCancelView (deals/views.py:52) |
| POST | `/api/v1/deals/<pk>/review/` | DealReviewView (deals/views.py:64) |
| GET | `/api/v1/deals/seller-rating/<user_id>/` | SellerRatingView, AllowAny (deals/views.py:83) |
| GET | `/api/v1/deals/listing-buyers/<listing_id>/` | ListingBuyersView (deals/views.py:91) |
| POST | `/api/v1/messages/start/` | StartConversationView, throttle `messages` (messaging/views.py:33) |
| GET | `/api/v1/messages/conversations/` | ConversationListView (messaging/views.py:57) |
| GET/POST | `/api/v1/messages/conversations/<pk>/` | ConversationDetailView (messaging/views.py:78) |
| GET | `/api/v1/messages/unread-count/` | UnreadCountView (messaging/views.py:125) |
| GET | `/api/v1/notifications/` | NotificationListView (notifications/views.py:11) |
| POST | `/api/v1/notifications/mark-read/` | MarkReadView (notifications/views.py:19) |
| GET | `/api/v1/notifications/unread-count/` | UnreadCountView (notifications/views.py:34) |
| POST | `/api/v1/payments/liqpay/checkout/` | LiqPayCheckoutView (payments/views.py:66) |
| POST | `/api/v1/payments/liqpay/callback/` | LiqPayCallbackView, без auth, csrf_exempt (payments/views.py:133) |

Смежное (не аудируется, но связано): `POST /api/v1/local/listings/<pk>/promote/` — LocalListingPromoteView (local_listings/views.py:402-455) создаёт Payment по серверной цене тарифа.
Фронтенд-страницы: `frontend/app/me/deals/page.tsx`, `frontend/app/me/messages/page.tsx`, `frontend/app/me/notifications/page.tsx`, `frontend/components/local/PromoteModal.tsx`, `frontend/api/deals.ts`.

## Функции

| Функция | Состояние | Файл:строки | Комментарий |
|---|---|---|---|
| Предложение сделки продавцом | частично | deals/services.py:22-61 | Нет проверки статуса объявления (можно предложить по sold/hidden); после отмены повторно предложить тому же покупателю нельзя (services.py:44 + UniqueConstraint models.py:41) |
| Подтверждение сделки покупателем | частично | deals/services.py:64-90 | Нет `select_for_update` и проверки «у объявления уже есть подтверждённая сделка» — два покупателя могут подтвердить параллельные сделки; прочие proposed-сделки не отменяются |
| Отмена сделки | частично | deals/services.py:93-113 | Повторная отмена уже отменённой разрешена и шлёт уведомление повторно |
| Переходы статусов | частично | deals/services.py | proposed→confirmed (buyer), proposed→cancelled (обе стороны); confirmed — финальный. Нет машины состояний в модели; admin может менять status произвольно (deals/admin.py:14) |
| Отзыв после сделки | готово | deals/services.py:116-141 | Только покупатель, один раз, после confirmed. Продавец отзыв о покупателе оставить не может (по дизайну) |
| Рейтинг продавца / бейдж | готово | deals/services.py:144-163 | Порог из .env `SELLER_BADGE_THRESHOLD` (core/settings.py:316) |
| Список покупателей для продавца | готово | deals/views.py:91-107 | Отдаёт email покупателей (см. 06-S5) |
| Начало диалога | готово | messaging/services.py:21-70 | local: покупатель↔автор; imported: покупатель↔первый is_staff |
| Отправка ответа | готово | messaging/views.py:100-122 | Проверка участника есть; отдельного спам-лимита нет (06-S6) |
| Доступ только участникам | готово | messaging/views.py:25-30, 89-90 | 403 чужому; is_staff видит все imported-диалоги |
| Антиспам контактов в сообщениях | частично | messaging/services.py:107-122 | soft/hard/off из .env; в режиме hard при старте диалога — 500 (06-Q1) |
| Прочитано / счётчик непрочитанных | готово | messaging/services.py:85-104 | mark_as_read вызывается в GET (побочный эффект) |
| Вложения в сообщениях (фото/файлы) | отсутствует | messaging/models.py:56-75 | Только text |
| Блокировка/жалоба на собеседника в чате | отсутствует | — | Жалобы есть в `reports/` (не проверено, покрывают ли сообщения) |
| In-app уведомления | готово | notifications/* | Список (последние 50), отметка прочитанным, счётчик |
| Telegram-уведомления | готово | deals/services.py:15-19, messaging/services.py:173-177 | Через Celery `integrations.tasks.send_notification` (integrations/tasks.py:53); без токена — no-op с логом |
| Email-уведомления о сообщениях/сделках | отсутствует | — | Email шлётся только в local_listings (модерация), не в этом пакете |
| Настройки уведомлений пользователя (opt-out по каналам) | отсутствует | — | |
| Шаблоны уведомлений | хардкод | deals/services.py:53-140, messaging/services.py:149-153 | Строки в коде, не в админке |
| LiqPay checkout общий | сломано (небезопасно) | payments/views.py:66-115 | Сумма, purpose, listing_id, result_url, server_url — от клиента (issue #24); фронтом не используется |
| LiqPay checkout продвижения | готово | local_listings/views.py:402-455 | Цена из PromotionTariff (админка); но нет server_url/result_url (06-C3) |
| LiqPay callback | частично | payments/views.py:137-182 | Подпись проверяется; сумма/валюта не сверяются; пустой ключ = подделка (06-S1) |
| Идемпотентность callback | частично | payments/views.py:166-169 | Только completed→completed; нет блокировки строки; failed→completed повторно применяет тариф |
| Sandbox-режим | частично | core/settings.py:303, liqpay_client.py:75, 111 | По умолчанию sandbox=true; статус `sandbox` засчитывается как оплата и в боевом режиме (06-S4) |
| Возврат (reversed) | заглушка | payments/views.py:171-180 | Статус меняется, эффект (продвижение/unlock) не откатывается |
| История платежей пользователя | отсутствует | — | Эндпоинта нет; платежи видит только админ (payments/admin.py) |
| Цены продвижения | готово | local_listings/models.py:38-56 | Модель PromotionTariff в админке. Цен для listing_unlock/listing_vip нет нигде |

## Сверка с BRIEF.md

**Совпадает**
- Раздел 1, C2C: «сделки, переписка, платное продвижение» реализованы на уровне API и страниц `/me/deals`, `/me/messages`.
- Раздел 2: цены продвижения — в админке (`PromotionTariff`); ключи LiqPay, режим sandbox, антиспам, лимит сообщений, порог бейджа — в `.env` (core/settings.py:237, 301-316).
- Раздел 3: переписка закрыта для чужих (403, тесты `messaging/tests.py` stranger_*); уведомления фильтруются по `user=request.user` (notifications/views.py:15, 29).
- Раздел 1 п.3: Telegram-уведомления пользователям о сообщениях и сделках идут через Celery.

**Противоречит**
- Раздел 2 «внешние API через адаптеры с real + demo реализацией, честный статус «не настроено»»: у LiqPay нет интерфейса/адаптера и demo-реализации; при пустых ключах checkout всё равно выдаёт ссылку на LiqPay с пустым `public_key` (liqpay_client.py:67-89), а callback принимает подпись, сделанную пустым ключом (06-S1). Статуса интеграции в админке нет.
- Раздел 2 «Все цены в админке»: для `listing_unlock`/`listing_vip` цены нет вообще, сумма от клиента (payments/serializers.py:18-26, issue #24).
- Раздел 3 «email и телефон видит только владелец»: email контрагента отдаётся в сделках, переписке, списке покупателей и в тексте уведомления (06-S5).
- Раздел 3 «Роли buyer/dealer/broker/admin»: роли broker нет (users/models.py:25-28); диалоги по импортным лотам получает «первый is_staff» (messaging/services.py:17-18, 63), а видят их все is_staff (messaging/views.py:62-65).

**Не хватает**
- Раздел 3 «удаление аккаунта / выгрузка данных»: Deal, Review, Message, Conversation — `on_delete=CASCADE` на пользователя (deals/models.py:20,26; messaging/models.py:16,64) — удаление аккаунта одной стороны стирает историю сделок и сообщения у второй. Выгрузки сделок/сообщений/платежей нет.
- Раздел 3 «тест 401/403 на каждый эндпоинт с личными данными»: нет 403-тестов для чужого confirm/cancel/review через API, для `listing-buyers` чужим, для платежей; нет `notifications/tests.py` (тесты лежат в `tests/test_favorites_notifications_saved_searches.py`).
- Раздел 5 «Playwright-тесты»: для сделок, переписки, уведомлений, оплаты — нет ни одного (frontend/e2e/*.spec.ts не содержит этих сценариев).
- Раздел 2 `docs/LAUNCH_CHECKLIST.md` — файла нет (docs/ не содержит), переменные LIQPAY_*, THROTTLE_MESSAGES_RATE, ANTISPAM_MODE, SELLER_BADGE_THRESHOLD никуда не сведены.
- Email-канал уведомлений о новых сообщениях/сделках.

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 06-S1 | критично | При пустом `LIQPAY_PRIVATE_KEY` (дефолт `''`) подпись = `sha1(data)` — любой может подделать callback и перевести любой платёж в completed (бесплатное продвижение/unlock) | payments/liqpay_client.py:44-46, 98-103; core/settings.py:302 | Если ключ не задан — callback отвечает 503 «не настроено», checkout недоступен |
| 06-S2 | критично | Общий checkout: сумма от клиента, `purpose=listing_unlock` + чужой `listing_id` без проверки владения; после оплаты 0.01 `unlock_listing` меняет статус любого `Listing` на in_stock (issue #24) | payments/serializers.py:24-26, 41-48; payments/views.py:74-97; payments/models.py:76-79 | Серверный прайс (модель в админке) по purpose, проверка прав на listing; до этого — отключить эндпоинт (фронт его не использует) |
| 06-S3 | важно | Callback не сверяет `amount`/`currency`/`action` из данных LiqPay с Payment | payments/views.py:154-179 | Сравнить decoded amount/currency с payment, при расхождении — статус failed + лог |
| 06-S4 | важно | LiqPay-статус `sandbox` засчитывается как оплата и при `LIQPAY_SANDBOX=false` | payments/liqpay_client.py:111 | Принимать `sandbox` только если sandbox-режим включён |
| 06-S5 | важно | Email контрагента раскрывается: DealUserSerializer, ParticipantSerializer, список покупателей, текст уведомления (уходит и в Telegram); фронт показывает его | deals/serializers.py:13-17; messaging/serializers.py:9-12; deals/views.py:101-104; deals/services.py:57; frontend/app/me/deals/page.tsx:102 | Отдавать только id + отображаемое имя; email — только владельцу/админу |
| 06-S6 | важно | Спам-лимит только на старт диалога; ответы в существующем диалоге ограничены лишь общим `user` 300/hour | messaging/views.py:35-36, 100; core/settings.py:215, 237 | Повесить ScopedRateThrottle `messages` (или отдельный scope) на POST детали |
| 06-S7 | важно | `result_url` и `server_url` задаёт клиент — открытый редирект через LiqPay и увод callback на чужой сервер | payments/serializers.py:33-34; payments/views.py:80-81 | Строить оба URL на сервере из `SITE_URL`/отдельной env |
| 06-S8 | важно | Гонка/идемпотентность callback: нет `select_for_update`; переход completed→failed→completed повторно применяет тариф; reversed не откатывает эффект | payments/views.py:158-179 | Транзакция + блокировка строки, эффект применять один раз (флаг applied_at) |
| 06-S9 | важно | Все is_staff видят и получают уведомления по всем диалогам импортных лотов, включая текст переписки; нет роли broker | messaging/views.py:62-65; messaging/services.py:157-161; users/models.py:25-28 | Ввести роль broker и ограничить доступ ей/admin |
| 06-S10 | желательно | Сравнение подписи через `!=`, не constant-time | payments/liqpay_client.py:99 | `hmac.compare_digest` |
| 06-S11 | желательно | Удаление пользователя каскадно удаляет сделки/сообщения/отзывы второй стороны; выгрузки данных нет | deals/models.py:20,26,64; messaging/models.py:16,64 | SET_NULL/анонимизация + выгрузка в кабинете |
| 06-S12 | желательно | `SellerRatingView` AllowAny по любому user_id — перечисление пользователей (утекают только счётчики) | deals/views.py:83-88 | Отдавать рейтинг только для продавцов с публичными объявлениями |
| 06-S13 | желательно | Ответ callback раскрывает order_id и текст ошибки подписи внешнему вызывающему | payments/views.py:149, 162 | Короткий нейтральный ответ, детали — в лог |

## Готовность к конфигурации

| ID | Что захардкожено / заглушка | Файл:строка | Куда вынести |
|---|---|---|---|
| 06-C1 | Нет цены для `listing_unlock` / `listing_vip` — сумма от клиента | payments/serializers.py:18-26 | Модель тарифов в админке (аналог PromotionTariff) |
| 06-C2 | LiqPay без адаптера/demo-реализации и без статуса «не настроено»; пустые ключи не блокируют checkout | payments/liqpay_client.py:33-40; local_listings/views.py:435 | Интерфейс PaymentProvider (real/demo), переключатель в .env, статус в админке |
| 06-C3 | Checkout продвижения не передаёт `server_url`/`result_url` — callback не придёт, если не настроен кабинет LiqPay; пользователь не возвращается на сайт | local_listings/views.py:436-441 | Собирать из `SITE_URL` (core/settings.py:414) / новой env `LIQPAY_SERVER_URL` |
| 06-C4 | URL LiqPay захардкожены | payments/liqpay_client.py:19-20 | Допустимо (константы API); при желании — .env |
| 06-C5 | Тексты уведомлений (сделки, сообщения) хардкодом в коде | deals/services.py:53-140; messaging/services.py:149-153 | Модель шаблонов уведомлений в админке (или хотя бы i18n) |
| 06-C6 | Текст предупреждения антиспама | messaging/views.py:118-121 | Допустимо; при желании — настройки в админке |
| 06-C7 | Лимит 50 уведомлений в списке | notifications/views.py:15 | Пагинация DRF |
| 06-C8 | Получатель импортных диалогов — «первый is_staff по pk» | messaging/services.py:17-18 | Настройка/роль broker в админке |
| 06-C9 | Дефолт валюты Payment `USD`, CURRENCIES список в коде | payments/models.py:48; payments/serializers.py:7 | Допустимо; валюта должна браться из тарифа |
| 06-C10 | Переменные LIQPAY_*, THROTTLE_MESSAGES_RATE, ANTISPAM_MODE, SELLER_BADGE_THRESHOLD не описаны в LAUNCH_CHECKLIST (файла нет); в .env.example нет THROTTLE_MESSAGES_RATE/ANTISPAM_MODE/SELLER_BADGE_THRESHOLD | core/settings.py:237, 301-316; .env.example:47-49 | docs/LAUNCH_CHECKLIST.md + .env.example |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 06-Q1 | важно | В режиме `ANTISPAM_MODE=hard` `_add_message` бросает PermissionError, а StartConversationView ловит только ValueError → 500 | messaging/services.py:116-117; messaging/views.py:41-49 |
| 06-Q2 | важно | confirm_deal без блокировки и без проверки других подтверждённых сделок по объявлению; остальные proposed не отменяются | deals/services.py:64-80 |
| 06-Q3 | важно | propose_deal не проверяет статус объявления (sold/hidden/expired) | deals/services.py:31-45 |
| 06-Q4 | важно | Нельзя повторно предложить сделку покупателю после отмены (проверка существования включает cancelled + UniqueConstraint) | deals/services.py:44; deals/models.py:41-44 |
| 06-Q5 | важно | Исключения уведомлений глушатся `except Exception: pass` без логирования | deals/services.py:13-19; messaging/services.py:171-177 |
| 06-Q6 | важно | N+1: `get_other_participant` делает `.exclude().first()` мимо prefetch — запрос на каждый диалог; список грузит все сообщения всех диалогов (prefetch messages__sender) без пагинации | messaging/serializers.py:63-77; messaging/views.py:69-72 |
| 06-Q7 | желательно | `.delay()` Celery внутри `@transaction.atomic` — нужно `transaction.on_commit` | deals/services.py:17, 22; messaging/services.py:21, 175 |
| 06-Q8 | желательно | Нечисловой `listing_id` в POST /deals/ и `id` в mark-read → ValueError → 500 (listing_id не в сериализаторе) | deals/views.py:31-32; notifications/views.py:27-29 |
| 06-Q9 | желательно | Гонка при создании Conversation (filter→create), IntegrityError → 500 | messaging/services.py:39-46, 55-62 |
| 06-Q10 | желательно | Дублирование get_subject_title/get_subject_url в двух сериализаторах | messaging/serializers.py:44-61, 90-107 |
| 06-Q11 | желательно | mark_as_read в GET — побочный эффект; staff, открывший импортный диалог, помечает прочитанным | messaging/views.py:97 |
| 06-Q12 | желательно | cancel_deal разрешает отменять уже отменённую сделку (повторное уведомление) | deals/services.py:98-102 |
| 06-Q13 | желательно | Нет составного индекса (user, is_read) у Notification; нет пагинации сообщений в деталях | notifications/models.py:17-27; messaging/serializers.py:84 |
| 06-Q14 | желательно | `unlock_listing` в модели — бизнес-логика вне сервисного слоя; `_apply_local_listing_promote` во views | payments/models.py:76-79; payments/views.py:20-50 |
| 06-Q15 | желательно | Смешение языков в verbose_name (рус./укр.) | payments/models.py:7-16 |
| 06-Q16 | желательно | Импорт внутри функции `ReviewSerializer` | deals/views.py:79 |

## Тесты

**Покрыто**
- `deals/tests.py` — 31 тест: сервисы propose/confirm/cancel/review/rating + API happy-path и 401 на список.
- `messaging/tests.py` — 23 теста: создание/повтор диалога, самосообщение, неактивное объявление, 401, 403 чужому на чтение и отправку, прочтение, счётчик.
- `payments/tests.py` — 8 тестов: валидация checkout.
- `tests/test_e2e.py:276-405` — 11 тестов LiqPay: checkout, callback с верной/неверной подписью, unlock, идемпотентность дубля.
- `local_listings/tests.py:676-820` — 10 тестов promote + callback (renew/bump/top, дубль).
- `tests/test_favorites_notifications_saved_searches.py:50-142` — 12 тестов уведомлений (сервис, API, 401, чужие не видны, mark-read, создание при модерации/сообщении).

**Не покрыто**
- API 403 чужому на confirm/cancel/review; 403 на `listing-buyers` чужим; утечка email в ответах.
- Параллельное подтверждение двух сделок; propose по sold-объявлению; повторное предложение после отмены.
- Antispam hard/soft в сообщениях (06-Q1); throttle сообщений.
- Callback: пустой ключ (06-S1), несовпадение суммы (06-S3), статус sandbox в боевом режиме (06-S4), failed→completed, reversed.
- Checkout listing_unlock чужого листинга (06-S2); mark-read чужого уведомления по id; некорректный id → 400.
- Отсутствие роли broker, доступ staff к импортным диалогам.
- Нет ни одного Playwright-сценария для этого пакета.

**Нужны Django-тесты**: все пункты «не покрыто» выше, плюс проверка, что Telegram-задача ставится через on_commit (мок `send_notification.delay`).

**Нужны Playwright-сценарии**
- Покупатель пишет продавцу → продавец видит диалог и отвечает → счётчики непрочитанного; попытка открыть чужой `/me/messages?conv=<id>` → ошибка доступа.
- Продавец помечает «продано» → выбирает покупателя → покупатель подтверждает → отзыв → бейдж/рейтинг; покупатель отменяет → статус «скасовано».
- Уведомления: колокольчик, отметить прочитанным, «прочитать все».
- Продвижение: выбор тарифа → редирект на LiqPay (sandbox, мок) → возврат → объявление в ТОП; ошибка оплаты → статус не меняется.

## Итог (≤15 строк)

Готовность пакета ~60%: сделки, переписка и in-app/Telegram-уведомления работают на уровне API и страниц кабинета, доступ к диалогам закрыт 403-проверкой. Главный риск — платежи.
Критично: 06-S1 — при пустом LIQPAY_PRIVATE_KEY (дефолт) подпись callback подделывается, любой платёж можно перевести в completed; 06-S2 (issue #24) — общий checkout принимает сумму, purpose и чужой listing_id от клиента, оплата 0.01 меняет статус любого Listing (фронт этот эндпоинт не использует — его можно отключить).
Важно: callback не сверяет сумму и валюту (06-S3); статус `sandbox` засчитывается и в боевом режиме (06-S4); email контрагента виден в сделках, чате и уведомлениях (06-S5); у ответов в чате нет отдельного спам-лимита (06-S6); result_url и server_url задаёт клиент (06-S7); нет блокировки строки при callback, reversed не откатывает эффект (06-S8); все is_staff видят импортные диалоги, роли broker нет (06-S9).
Функции: нет вложений, email-канала, настроек уведомлений и истории платежей; тексты уведомлений захардкожены (06-C5); у LiqPay нет адаптера, demo-режима и статуса «не настроено» (06-C2); promote не передаёт server_url (06-C3).
Ошибки: при ANTISPAM_MODE=hard старт диалога падает с 500 (06-Q1); гонка при подтверждении двух сделок (06-Q2); сделку можно предложить по проданному объявлению (06-Q3); N+1 в списке диалогов (06-Q6).
Тесты: 95 Django-тестов по пакету, 0 Playwright, нет негативных тестов на платежи и 403 для сделок.
