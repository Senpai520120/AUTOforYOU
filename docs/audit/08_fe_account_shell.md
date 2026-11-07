# Аудит: 08 — Фронтенд: аккаунт и каркас

## Состав

Middleware (`frontend/middleware.*`, `frontend/proxy.*`) — **отсутствует**.

| Файл | Строк | Назначение |
|---|---|---|
| frontend/api/client.ts | 80 | Клиентский fetch-обёртка, JWT из localStorage, refresh по 401 |
| frontend/api/me.ts | 16 | API кабинета: trusted-shops, shipments |
| frontend/lib/auth-context.tsx | 110 | AuthProvider: login/logout/refresh, профиль |
| frontend/lib/server-api.ts | 51 | Серверные (SSR) анонимные GET-запросы, белый список query |
| frontend/lib/types.ts | 421 | TS-типы API |
| frontend/lib/utils.ts | 15 | `listingSlug` |
| frontend/lib/consent.ts | 77 | (пакет 11) согласие на хранилище — связь см. ниже |
| frontend/next.config.ts | 38 | remotePatterns для next/image |
| frontend/app/layout.tsx | 46 | Корневой layout, metadata, AuthProvider, Header/Footer/CookieBanner |
| frontend/app/page.tsx | 227 | Главная (SSR, force-dynamic) |
| frontend/app/error.tsx | 38 | Error boundary |
| frontend/app/global-error.tsx | 30 | Глобальный error boundary |
| frontend/app/not-found.tsx | 25 | 404 |
| frontend/app/login/{layout,page}.tsx | 10 + 55 | Вход |
| frontend/app/register/{layout,page}.tsx | 10 + 99 | Регистрация |
| frontend/app/me/layout.tsx, loading.tsx, page.tsx | 10 + 20 + 71 | Кабинет: меню |
| frontend/app/me/calculations/page.tsx | 63 | Мои расчёты |
| frontend/app/me/deals/page.tsx | 207 | Сделки и отзывы |
| frontend/app/me/favorites/page.tsx | 104 | Избранное |
| frontend/app/me/local-listings/page.tsx | 302 | Мои объявления (C2C), продвижение, «продано» |
| frontend/app/me/messages/page.tsx | 262 | Переписка |
| frontend/app/me/notifications/page.tsx | 118 | Уведомления |
| frontend/app/me/saved-searches/page.tsx | 117 | Сохранённые поиски |
| frontend/app/me/shipments/page.tsx | 87 | Контейнеры |
| frontend/app/me/telegram/page.tsx | 131 | Привязка Telegram |
| frontend/app/me/trusted-shops/page.tsx | 99 | Партнёры (СТО и т.п.) |
| frontend/components/layout/Header.tsx | 107 | Шапка, счётчики непрочитанных |
| frontend/components/layout/Footer.tsx | 24 | Подвал |
| frontend/components/ui/Badge, CookieBanner, CookieSettings, DemoBanner, Skeleton, Spinner | 20/55/67/23/28/6 | UI-примитивы |

Итого ~3270 строк. Моделей нет (фронтенд).

Страницы: `/`, `/login`, `/register`, `/me`, `/me/{calculations,deals,favorites,local-listings,messages,notifications,saved-searches,shipments,telegram,trusted-shops}`, 404/ошибки.

Используемые эндпоинты бэкенда: `POST /api/v1/auth/token/` (auth-context.tsx:81), `POST /api/v1/auth/token/refresh/` (auth-context.tsx:53, client.ts:6), `GET /api/v1/auth/profile/` (auth-context.tsx:39), `POST /api/v1/auth/register/` (register/page.tsx:24), `/api/v1/auth/me/trusted-shops/`, `/api/v1/auth/me/shipments/` (api/me.ts:6-15), `/api/v1/telegram/link-token/`, `/api/v1/telegram/link/` (telegram/page.tsx:35,48), SSR: `/api/v1/listings/?channel=retail`, `/api/v1/pricing/rates/` (page.tsx:35,49).
**Не используется:** `POST /api/v1/auth/token/logout/` (users/urls.py:29) — есть на бэкенде, фронтенд его не вызывает.

## Функции

| Функция | Состояние | файл:строки | Комментарий |
|---|---|---|---|
| Вход по email/паролю | готово | lib/auth-context.tsx:80-92, app/login/page.tsx:15-26 | Любая ошибка (в т.ч. 429/500) → «Невірний email або пароль» (auth-context.tsx:86) |
| Хранение JWT | сломано (по брифу) | auth-context.tsx:29-30,60-61,88-89; api/client.ts:4,13,22,71 | access и refresh в `localStorage` |
| Обновление access-токена | сломано | api/client.ts:3-15,31-38 | Ротированный refresh не сохраняется (client.ts:13), при `ROTATE_REFRESH_TOKENS`+`BLACKLIST_AFTER_ROTATION` (core/settings.py:350-351) сессия рвётся; гонка параллельных refresh (см. 08-Q1) |
| `refreshToken` в контексте | мёртвый код | auth-context.tsx:49-67 | Никем не вызывается; вторая, расходящаяся реализация refresh |
| Выход | частично | auth-context.tsx:28-33, Header.tsx:27-30, me/page.tsx:66 | Только чистит localStorage; refresh не отзывается на сервере |
| Регистрация | частично | app/register/page.tsx:16-36 | Согласие есть (66-85); капчи, подтверждения email нет; редирект на `/login?registered=1`, но login параметр не читает |
| Подтверждение email | отсутствует | — | Поле `is_email_verified` есть в модели (users/models.py:40), флоу нет |
| Капча / антибот | отсутствует | register/page.tsx | — |
| Сброс пароля по email | отсутствует | login/page.tsx:49-51 | Нет ссылки «Забули пароль?», нет страниц |
| Смена пароля в кабинете | отсутствует | me/page.tsx:17-28 | — |
| Редактирование профиля (имя, телефон) | отсутствует | me/page.tsx | PATCH `/auth/profile/` есть на бэкенде, UI нет |
| Удаление аккаунта | отсутствует | me/page.tsx | — |
| Выгрузка своих данных | отсутствует | me/page.tsx | — |
| Отзыв всех сессий | отсутствует | — | — |
| Защита приватных страниц | частично | каждая `me/*/page.tsx` (напр. me/page.tsx:11-15) | Только клиентский `useEffect → router.push('/login')`; middleware нет; без `?next=` возврата |
| SSR-запросы | готово (анонимно) | lib/server-api.ts:32-40, app/page.tsx:33-56 | Авторизованного SSR нет — утечки ПДн в SSR-HTML отсутствуют; но и SSR приватных страниц невозможен |
| CSRF | отсутствует | — | Сейчас не нужен (Bearer), но обязателен после перехода на cookie |
| Кабинет брокера | отсутствует | me/page.tsx:17-28, lib/types.ts:9 | Роли `broker` нет ни в типе, ни в модели (users/models.py:25-28) |
| Кабинет: меню | готово | me/page.tsx:17-64 | Метка роли не знает broker (42) |
| Мои расчёты | частично | me/calculations/page.tsx | Только первая страница, ошибки → пустое состояние |
| Сделки/отзывы | готово | me/deals/page.tsx | Ошибка загрузки → «Угод поки немає» |
| Избранное | готово | me/favorites/page.tsx | Ошибки удаления глотаются (32-34) |
| Мои объявления | готово | me/local-listings/page.tsx | `alert/confirm` вместо UI; модалка без a11y |
| Сообщения | частично | me/messages/page.tsx | Не адаптировано под мобильный (145) |
| Уведомления | готово | me/notifications/page.tsx | «Прочитать все» оптимистично даже при ошибке (50-51) |
| Сохранённые поиски | готово | me/saved-searches/page.tsx | Оптимистичные update/delete при ошибке (38-46) |
| Контейнеры | готово | me/shipments/page.tsx | Нет catch (34) |
| Telegram | готово | me/telegram/page.tsx | Имя бота захардкожено (107) |
| Партнёры | частично | me/trusted-shops/page.tsx | Нет обработки ошибок create/delete (27,34), удаление без подтверждения |
| Шапка | частично | components/layout/Header.tsx | На мобильных навигация скрыта без бургера (41) |
| Подвал | частично | components/layout/Footer.tsx | Нет реквизитов/контактов (issue #10) |
| 404 / error / global-error | готово | not-found.tsx, error.tsx, global-error.tsx | Нет отправки ошибок в мониторинг; global-error не подключает globals.css (не проверено визуально) |
| Главная | готово | app/page.tsx | Хардкод ставок в тексте (85-89) |
| Демо-баннер | частично | components/ui/DemoBanner.tsx:4 | Флаг есть, но дубли «Тестові тарифи» в Footer/Home не зависят от него |
| Cookie-баннер / настройки | готово | CookieBanner.tsx, CookieSettings.tsx | Связь с consent.ts (пакет 11) — см. ниже |

**Связь с `lib/consent.ts` (пакет 11):** consent.ts:4 прямо фиксирует «Сайт зберігає дані в localStorage, а не в cookie», а текст баннера (CookieBanner.tsx:30) — «Ми зберігаємо у вашому браузері дані, потрібні для входу в акаунт». После миграции JWT в httpOnly cookie (08-S1) нужно синхронно переписать consent.ts:1-11, текст CookieBanner и страницу `/cookies` (она сама читает localStorage — app/cookies/page.tsx, 4 упоминания).

## Сверка с BRIEF.md

| Пункт брифа | Статус | Детали |
|---|---|---|
| §3 JWT не в localStorage, httpOnly+Secure+SameSite cookie, CSRF, SSR работает | **противоречит** | localStorage (08-S1), CSRF нет (08-S3) |
| §3 Регистрация: подтверждение email | не хватает | 08-S4 |
| §3 Согласие на обработку данных | совпадает | register/page.tsx:66-85, бэкенд проверяет (users/serializers.py:11) |
| §3 Капча или эквивалент | не хватает | 08-S4 |
| §3 Сброс пароля по email, смена пароля в кабинете, отзыв всех сессий | не хватает | 08-S5 |
| §3 Лимит попыток входа | не хватает на фронте (сообщения), бэкенд — другой пакет | auth-context.tsx:86 маскирует 429 (08-S8) |
| §3 Нет утечек через SSR-HTML | совпадает | SSR только анонимный (server-api.ts:1-9); приватные страницы — клиентские |
| §3 Удаление аккаунта, выгрузка данных | не хватает | 08-S6 |
| §3 Политика конфиденциальности/cookie — связка | совпадает частично | ссылки в Footer.tsx:11-17 и register; тексты завязаны на localStorage |
| §3 Роли buyer/dealer/broker/admin | не хватает broker | lib/types.ts:9, me/page.tsx:42 (08-Q8) |
| §3 Безопасные заголовки (CSP, HSTS) | не хватает на уровне Next | next.config.ts без `headers()` (08-S9) — возможно, решается в nginx (не проверено) |
| §1 Кабинет брокера со статусами заявок | отсутствует | 08-Q8 |
| §2 Всё настраивается без кода | противоречит частично | 08-C1…C5 |
| §2 Тестовые данные помечены и пометка исчезает автоматически | противоречит | «Тестові тарифи» захардкожено в Footer.tsx:18-20 и page.tsx:118-120, не зависит от флага (08-C2) |
| §4 Этап 6: мобильная версия, пустые состояния, ошибки, доступность | частично | 08-Q4, Q5, Q6, Q11 |
| §5 Нет хардкода контактов | противоречит | имя бота (08-C4); реквизитов нет вовсе (08-C1, issue #10) |
| §5 Playwright на функции | не хватает | нет тестов login/logout/me |

## Безопасность и личные данные

| ID | Уровень | Проблема | файл:строка | Как исправить |
|---|---|---|---|---|
| 08-S1 | критично | access и refresh JWT хранятся в `localStorage` — любой XSS крадёт refresh на 7 дней (core/settings.py:349) | lib/auth-context.tsx:29-30,60-61,88-89; api/client.ts:4,13,22,71 | Выдавать токены в httpOnly+Secure+SameSite cookie с бэкенда, `credentials: 'include'`, убрать localStorage |
| 08-S2 | важно | Выход не отзывает refresh: `/api/v1/auth/token/logout/` не вызывается | lib/auth-context.tsx:28-33; users/urls.py:29 | В `logout()` вызывать POST token/logout/ (или сервер чистит cookie + blacklist) |
| 08-S3 | важно | Нет CSRF-инфраструктуры (нужна при cookie-аутентификации) | api/client.ts:23-27 | При переходе на cookie — CSRF-токен (double-submit) в заголовке `X-CSRFToken` для небезопасных методов |
| 08-S4 | важно | Регистрация без подтверждения email и без капчи; `is_email_verified` не используется | app/register/page.tsx:24-28; users/models.py:40 | Письмо с одноразовой ссылкой + Turnstile/hCaptcha (бесплатно), UI «перевірте пошту» |
| 08-S5 | важно | Нет сброса пароля, смены пароля и «выйти со всех устройств» | app/login/page.tsx:49-51; app/me/page.tsx:17-28 | Страницы `/password-reset`, `/password-reset/confirm`, `/me/security` |
| 08-S6 | важно | Нет удаления аккаунта и выгрузки данных (ЗУ «Про захист персональних даних») | app/me/page.tsx:17-28 | Раздел «Мої дані»: экспорт JSON и удаление с подтверждением паролем |
| 08-S7 | желательно | Приватные страницы защищены только на клиенте, middleware нет, нет возврата на исходную страницу | app/me/page.tsx:11-15 (и аналоги во всех me/*) | `middleware.ts` по наличию cookie-сессии + `?next=` |
| 08-S8 | желательно | Любая ошибка входа (429 блокировка, 500, сеть) показывается как «Невірний email або пароль» | lib/auth-context.tsx:86 | Различать 400/401, 429 («спробуйте через N хв»), 5xx |
| 08-S9 | желательно | Нет security-заголовков (CSP, X-Frame-Options, HSTS, Referrer-Policy) на уровне Next | next.config.ts:12-36 | `async headers()` в next.config или в reverse-proxy (проверить пакет инфраструктуры) |
| 08-S10 | желательно | `remotePatterns` c `*.cloudfront.net`, `*.amazonaws.com` — оптимизатор картинок проксирует любой чужой дистрибутив | next.config.ts:28-33 | Конкретные хосты из `.env` |
| 08-S11 | желательно | Показ email контрагентов (минимизация ПДн): продавца/покупателя в сделках, всех написавших в модалке «продано» | app/me/deals/page.tsx:102; app/me/local-listings/page.tsx:133-134 | Показывать имя/маску; проверить сериализаторы deals (другой пакет) |
| 08-S12 | желательно | `router.push(item.link)` без проверки, что ссылка относительная | app/me/notifications/page.tsx:46 | Разрешать только пути, начинающиеся с `/` |

Положительное: SSR-слой анонимен и с белым списком query (lib/server-api.ts:14-29); регистрация не позволяет выбрать admin (users/serializers.py:12-18); B2B-ссылка в шапке по `is_verified_dealer || is_staff` (Header.tsx:48).

## Готовность к конфигурации

| ID | Что захардкожено / заглушка | файл:строка | Куда вынести |
|---|---|---|---|
| 08-C1 | В подвале нет реквизитов компании, контактов, телефона, email, адреса (issue #10) | components/layout/Footer.tsx:9-20 | Модель настроек сайта в админке (SiteSettings) → SSR-запрос |
| 08-C2 | «Тестові тарифи — всі розрахунки є демонстраційними» захардкожено, не зависит от `NEXT_PUBLIC_DEMO_MODE`/`is_estimate` | components/layout/Footer.tsx:18-20; app/page.tsx:118-120 | Использовать `DemoBanner`/флаг из `.env` или признак из API |
| 08-C3 | Ставки в тексте главной: «Акциз: 50–150 €/л», «Мито 10%», «ПДВ 20%», порты Клайпеда/Гданськ | app/page.tsx:83-90 | Выводить из `/api/v1/pricing/rates/` (тарифы — данные) или обобщить текст |
| 08-C4 | Имя бота `@AUTO_F_Y_bot` и «Посилання діє 30 хвилин» | app/me/telegram/page.tsx:107,109 | Имя из ответа link-token / `NEXT_PUBLIC_TELEGRAM_BOT`; срок из `expires_at` (есть в ответе, строка 9) |
| 08-C5 | Фолбэки `http://localhost:8000` (5 мест) и `https://autoforyou.ua` — в проде без переменной сайт молча пойдёт на localhost/чужой домен | api/client.ts:1; lib/auth-context.tsx:6; lib/server-api.ts:10; app/page.tsx:7; next.config.ts:6; app/layout.tsx:8 | Единый `lib/config.ts`, падать на сборке в production без переменных |
| 08-C6 | Текст демо-баннера по умолчанию | components/ui/DemoBanner.tsx:16-18 | Допустимо; при желании — текст из админки |
| 08-C7 | «Зверніться до менеджера» без контакта | app/me/shipments/page.tsx:49 | Контакт менеджера из SiteSettings |
| 08-C8 | Хосты Copart/IAAI/CDN в remotePatterns | next.config.ts:27-33 | `.env` (список хостов) |

## Качество кода

| ID | Уровень | Проблема | файл:строка |
|---|---|---|---|
| 08-Q1 | критично | Принудительный выход через 15–30 мин: (1) `refreshAccessToken` не сохраняет новый refresh при ротации — старый уже в blacklist (core/settings.py:350-351), второй refresh гарантированно падает → очистка и редирект на /login; (2) гонка: Header параллельно опрашивает 2 эндпоинта каждые 30 с (Header.tsx:18-23), после истечения access оба получают 401 и оба шлют один и тот же refresh — второй получает «blacklisted» → logout. Нужен единый in-flight promise refresh | api/client.ts:3-15,31-38 |
| 08-Q2 | важно | `apiFetch` при любом 401 без refresh делает `window.location.href='/login'` — гость, попавший на эндпоинт с 401, выбрасывается на логин; также `localStorage` на сервере упадёт | api/client.ts:22,31-38 |
| 08-Q3 | желательно | Две расходящиеся реализации refresh; `refreshToken`, `tokens` из контекста не используются | lib/auth-context.tsx:49-67,100 vs api/client.ts:3-15 |
| 08-Q4 | важно | Мобильная шапка: `nav` `hidden md:flex` без бургер-меню — на телефоне нет ссылок на каталоги/калькулятор/B2B; правая часть (2 иконки + имя + «Вийти») рискует не влезть в 360px (не проверено) | components/layout/Header.tsx:41,57-91 |
| 08-Q5 | важно | Сообщения не адаптированы: список диалогов фиксированной ширины `w-72` рядом с тредом | app/me/messages/page.tsx:143-145 |
| 08-Q6 | важно | Ошибки API маскируются под пустое состояние («нічого немає»): `.catch(() => {})` или отсутствие catch | me/calculations:19; me/shipments:34; me/trusted-shops:22; me/favorites:25; me/notifications:38; me/saved-searches:35; me/deals:40; me/local-listings:54; me/messages:42-43 |
| 08-Q7 | важно | Оптимистичные изменения применяются даже при ошибке; create/delete без try/catch → unhandled rejection без сообщения | me/saved-searches:38-46; me/notifications:49-52; me/trusted-shops:25-36; me/favorites:32-34 |
| 08-Q8 | важно | Нет роли broker и кабинета брокера (заявки со статусами — главный сценарий §1) | lib/types.ts:9; app/me/page.tsx:17-28,42; users/models.py:25-28 |
| 08-Q9 | важно | Нет редактирования профиля (имя, телефон), хотя API есть | app/me/page.tsx |
| 08-Q10 | желательно | `/login?registered=1` — параметр не обрабатывается, пользователь не видит «акаунт створено» | app/register/page.tsx:28; app/login/page.tsx |
| 08-Q11 | желательно | Доступность: `<label>` не связаны с полями (нет htmlFor/id) в login и register; поля партнёров только с placeholder; звёзды без aria-label; модалка «продано» без `role="dialog"`/`aria-modal`/Esc/фокус-трапа; сообщения об ошибке без `role="alert"`; Spinner без `role="status"`; кнопка «↻» только с title; эмодзи-иконки меню без aria-hidden | login/page.tsx:34-41; register/page.tsx:51-52,58-59; me/trusted-shops:56-71; me/deals:140-145; me/local-listings:114; login:43, register:87; ui/Spinner.tsx:4; me/messages:203-209; me/page.tsx:56 |
| 08-Q12 | желательно | Смешение языков в UI: «Запчасти» (рус.), «Погрузка» (рус.), «Перекупам UA» (сленг), англ. «buyer fee, gate, environmental, virtual bid», «ETA», «Алерти»; ошибки бэкенда могут прийти на русском (напр. `'refresh обязателен.'`, users/views.py:31); русские комментарии в UA-файлах | me/trusted-shops:10; me/shipments:18,66; Header.tsx:38; app/page.tsx:83; me/saved-searches:79,93; ui/DemoBanner.tsx:1-3; lib/consent.ts:18-19 |
| 08-Q13 | желательно | `DealCard` объявлен внутри рендера (перемонтируется каждый рендер); `timeAgo` продублирован | me/deals:90; me/notifications:17-24 = me/messages:9-16 |
| 08-Q14 | желательно | Главная дублирует серверный fetch вместо `serverGet` | app/page.tsx:7,33-56 vs lib/server-api.ts:32 |
| 08-Q15 | желательно | Нет пагинации в кабинете — показывается только первая страница | me/calculations:19; me/shipments:34; me/trusted-shops:22; me/local-listings:53 |
| 08-Q16 | желательно | Сообщение ошибки = `res.statusText` (пусто на HTTP/2); `Content-Type: application/json` на GET/DELETE → лишний CORS preflight | api/client.ts:23-24,43 |
| 08-Q17 | желательно | error/global-error только `console.error`, нет отправки в мониторинг; `<a>` вместо `Link`; global-error не импортирует globals.css (стили могут не примениться — не проверено) | app/error.tsx:11-13,29; app/global-error.tsx:1-30 |
| 08-Q18 | желательно | Удаление без подтверждения; `alert/confirm` вместо UI | me/trusted-shops:33-36,90; me/saved-searches:38-41,95-100; me/local-listings:59,64,86 |
| 08-Q19 | желательно | Опрос счётчиков каждые 30 с и в фоновых вкладках | components/layout/Header.tsx:23 |
| 08-Q20 | желательно | Смешение `.then(setX)` без обработки и ранний `return null` без индикатора (пустой экран при загрузке профиля) | me/page.tsx:15; me/favorites:37; me/telegram:27 |

## Тесты

Покрыто (Playwright, `frontend/e2e/`, только проект Desktop Chrome — playwright.config.ts:34-38):
- `register.spec.ts` — 5 тестов: поля/чекбокс согласия, блок без согласия, ссылки на terms/privacy, футер.
- `negative.spec.ts` — 4 теста регистрации (email, несовпадение паролей, дубль, простой пароль) + 5 калькулятора.
- `test-1.spec.ts` — 5 тестов шапки для гостя.
- `home.spec.ts` — 5 тестов главной; `ssr.spec.ts`, `catalog.spec.ts` — вне пакета.
- Django: `users/tests.py` — 38 тестов (logout/blacklist, регистрация с согласием, роль admin запрещена и др.) — бэкенд, другой пакет.

Не покрыто: вход (успех/ошибка/429), выход (отзыв refresh), refresh-токена и параллельные 401, редирект гостя с `/me/*`, все страницы кабинета, мобильная шапка, пустые/ошибочные состояния, a11y.

Нужные сценарии:
- Playwright: login успех → /me; неверный пароль → сообщение; гость на `/me/*` → /login и возврат по `next`; logout → повторный запрос с тем же refresh отклонён; «сессия живёт >15 мин» (мок времени/короткий ACCESS_TOKEN_LIFETIME в тестовом окружении) с параллельными запросами; проверка, что токенов нет в `localStorage` (после 08-S1) и cookie `HttpOnly`; мобильный проект (Pixel/iPhone) — бургер, messages; API 500 → видимое сообщение об ошибке, а не пустое состояние; axe-проверка login/register/me; сброс/смена пароля, удаление/экспорт аккаунта (после реализации).
- Django: refresh с ротацией + повторное использование старого refresh → 401; CSRF обязателен для cookie-аутентификации; эндпоинты экспорта/удаления — 401 для гостя, 403/404 для чужого.

## Итог (≤15 строк)

Готовность пакета ~55%: каркас (layout, шапка, подвал, 404/ошибки), вход/регистрация с согласием и 10 разделов кабинета работают, SSR анонимный — утечек ПДн в HTML нет.
Критично: **08-S1** JWT (access+refresh) в localStorage — прямое противоречие брифу §3; **08-Q1** refresh не сохраняет ротированный токен и гоняется при параллельных 401 → пользователя выкидывает на /login через 15–30 мин.
Важно: нет отзыва refresh при выходе (08-S2), CSRF (08-S3), подтверждения email/капчи (08-S4), сброса/смены пароля и отзыва сессий (08-S5), удаления/выгрузки аккаунта (08-S6); нет роли и кабинета брокера (08-Q8), редактирования профиля (08-Q9).
UX: мобильная шапка без бургера (08-Q4), сообщения не адаптивны (08-Q5), ошибки API выдаются за пустые состояния (08-Q6), оптимистичные изменения при ошибках (08-Q7).
Конфигурация: подвал без реквизитов (08-C1, issue #10), «Тестові тарифи» захардкожено вне демо-флага (08-C2), ставки акциза/мита/ПДВ в тексте главной (08-C3), имя бота (08-C4), фолбэки localhost/домена (08-C5).
Связь с пакетом 11: consent.ts и CookieBanner описывают хранение входа в localStorage — переписать вместе с 08-S1.
Тестов на вход/выход/кабинет/мобильную версию нет.

Счётчик: критично 2 / важно 15 / желательно 23.
