# Аудит: Пакет 11 — Фронтенд: юридичне і SEO

## Состав

| Файл | Строк | Назначение |
|---|---|---|
| frontend/app/privacy/page.tsx | 106 | Политика конфиденциальности (шаблон) |
| frontend/app/terms/page.tsx | 90 | Условия использования (шаблон) |
| frontend/app/rules/page.tsx | 115 | Правила размещения объявлений (шаблон) |
| frontend/app/refund/page.tsx | 145 | Политика возврата средств (шаблон) |
| frontend/app/cookies/page.tsx | 164 | Политика cookie/хранилища + блок настроек `CookieSettings` |
| frontend/app/robots.ts | 22 | robots.txt |
| frontend/app/sitemap.ts | 59 | sitemap.xml (статические + лоты импорта + местные объявления) |
| frontend/lib/consent.ts | 77 | Хранение согласия (`cookie_consent` в localStorage), гейт `hasAnalyticsConsent()` |

Связанные файлы метаданных (прочитаны точечно): frontend/app/layout.tsx (46), app/page.tsx, app/listings/page.tsx, app/listings/[id]/page.tsx, app/local/[id]/page.tsx, app/ua/page.tsx, app/calculator/layout.tsx, app/login/layout.tsx, app/register/layout.tsx, app/me/layout.tsx, app/not-found.tsx. Связка: components/layout/Footer.tsx, components/ui/CookieBanner.tsx, components/ui/CookieSettings.tsx, app/register/page.tsx, app/dealers/apply/page.tsx, components/local/LocalListingForm.tsx.

Модели/эндпоинты в пакете отсутствуют. Страницы: `/privacy`, `/terms`, `/rules`, `/refund`, `/cookies`, `/robots.txt`, `/sitemap.xml`.

## Функции

| Функция | Состояние | Файл:строки | Комментарий |
|---|---|---|---|
| Политика конфиденциальности | частично | frontend/app/privacy/page.tsx:8-106 | Шаблон с плашкой «потребує перевірки юристом» (:11-13); нет владельца ПДн, email/срок/дата — placeholder'ы (:77, :85, :101); перечень данных не соответствует моделям |
| Условия использования | частично | frontend/app/terms/page.tsx:7-90 | Шаблон; описывает только импорт из США (:29-32), нет C2C/платных услуг/применимого права; email и дата — placeholder (:80, :86) |
| Правила размещения | частично | frontend/app/rules/page.tsx:8-115 | Пользователю выводится буквальный текст `{LOCAL_LISTING_MAX_ACTIVE}` (:229); срок 30 дней захардкожен (:185); реквизиты — placeholder (:200) |
| Политика возврата | частично | frontend/app/refund/page.tsx:8-145 | Содержательно наиболее полная; таблица услуг захардкожена (:27-47) при наличии модели `PromotionTariff`; email/дата — placeholder (:116, :140) |
| Политика cookie + настройки | готово (как описание текущего кода) | frontend/app/cookies/page.tsx:8-164 | Точно отражает текущие ключи `access`/`refresh`/`cookie_consent` (:87-107); но фиксирует хранение JWT в localStorage, что противоречит брифу §3 |
| Cookie-баннер | готово | components/ui/CookieBanner.tsx:13-55, frontend/lib/consent.ts:41-77 | Две кнопки («Лише необхідні»/«Прийняти всі»), без мигания при гидратации; до согласия ставится только необходимое |
| Отзыв согласия | готово | components/ui/CookieSettings.tsx:107-114, frontend/lib/consent.ts:53-58 | `clearConsent()` возвращает баннер |
| Гейт аналитики | готово (не используется) | frontend/lib/consent.ts:64-66 | `hasAnalyticsConsent()` нигде не вызывается — аналитики нет (grep `gtag|next/script|googletagmanager` — 0 совпадений) |
| Реквизиты владельца (issue #10) | отсутствует | rules/page.tsx:200; privacy/page.tsx:18-22; Footer.tsx:9-10 | Нигде нет юр. названия, ЄДРПОУ/РНОКПП, адреса |
| Механизм прав субъекта (удаление/выгрузка) | отсутствует | users/urls.py:26-40; users/views.py:52 | Эндпоинтов удаления/экспорта аккаунта нет, `ProfileView` — только Retrieve/Update; в `/me` нет UI; privacy ссылается лишь на placeholder-email (privacy/page.tsx:75-78) |
| Связка страниц (футер) | готово | components/layout/Footer.tsx:11-17 | Все 5 документов в футере |
| Связка с регистрацией | готово | app/register/page.tsx:68-81 | Чекбокс + ссылки на `/terms`, `/privacy` |
| Связка с формой объявления | готово | components/local/LocalListingForm.tsx:392-407 | `/rules`, `/terms` (через `<a>`, не `Link`) |
| Связка с заявкой дилера | готово | app/dealers/apply/page.tsx:129-138 | `/privacy` |
| Перекрёстные ссылки документов | частично | privacy:93 → cookies; cookies:296 → privacy; rules:263 → refund; refund:94 → rules | terms не ссылается ни на privacy, ни на rules/refund |
| robots.txt | частично | frontend/app/robots.ts:5-21 | `'/me/'` и `'/b2b/'` не матчат `/me` и `/b2b` (префикс со слэшем); `/local/new` не закрыт; `/calculator` разрешён, но noindex |
| sitemap.xml | частично | frontend/app/sitemap.ts:23-58 | Только 1-я страница каждого списка (PAGE_SIZE=20, core/settings.py:241); URL лотов не совпадают с canonical; `/calculator` с noindex включён |
| Корневые метаданные | готово | frontend/app/layout.tsx:10-29, :33 | `metadataBase`, template, OG `locale: uk_UA`, `<html lang="uk">` |
| Метаданные юр. страниц | частично | privacy:4-6, terms:3-5, rules:4-6, refund:4-6, cookies:5-7 | Нет `description`; title с суффиксом `| AUTOforYOU` + template из layout.tsx:14 → двойной суффикс |
| Метаданные карточки лота | готово | app/listings/[id]/page.tsx:27-62 | canonical, OG, twitter |
| Метаданные местного объявления | частично | app/local/[id]/page.tsx:20-35 | Нет canonical и twitter |
| Метаданные каталогов | частично | app/listings/page.tsx:11-20, app/ua/page.tsx:14-23 | Нет canonical при фильтрах/пагинации |
| noindex приватных страниц | частично | me/layout.tsx:3-6, login/layout.tsx, register/layout.tsx, calculator/layout.tsx:6 | `/b2b`, `/local/new`, `/dealers/apply` — client-страницы без layout-метаданных, наследуют `index: true` из layout.tsx:25-28 |
| JSON-LD (Organization/Vehicle/Offer/Breadcrumb) | отсутствует | — | grep `application/ld+json` по frontend/app — 0 |
| OG-картинка по умолчанию | отсутствует | frontend/app/layout.tsx:17-21 | Нет `opengraph-image`/`images`; в app есть только favicon.ico |
| hreflang / язык | готово (одноязычный) | layout.tsx:33, :20 | Сайт только на украинском, hreflang не нужен |

## Сверка с BRIEF.md

| Пункт брифа | Статус | Комментарий |
|---|---|---|
| §3 «политика конфиденциальности и cookie (страницы уже есть — проверить связку)» | совпадает частично | Связка футер/регистрация/форма объявления/заявка дилера есть; содержимое — шаблон с placeholder'ами |
| §3 права пользователя: удаление аккаунта, выгрузка данных | не хватает | Нет ни бэкенд-механизма, ни UI, ни ссылки на него из privacy (11-S2) |
| §3 JWT не в localStorage (httpOnly cookie) | противоречит | cookies/page.tsx:87-107 документирует `access`/`refresh` в localStorage — так и есть в lib/auth-context.tsx:60-61, :88-89. После миграции на cookie страницу нужно переписать (11-S5) |
| §3 нет утечек через sitemap / SSR-HTML | совпадает | sitemap берёт только `id`/`updated_at` публичных записей (sitemap.ts:44-57); публичный список local — только ACTIVE (local_listings/views.py:137-138); телефон исключён из публичного сериализатора (local_listings/serializers.py:89) |
| §2 всё настраивается без правки кода | противоречит | Email для обращений, реквизиты, срок хранения, срок объявления, перечень платных услуг захардкожены в TSX (см. «Готовность к конфигурации») |
| §2 тестовые пометки исчезают автоматически | противоречит | Плашки «Шаблон — потребує перевірки юристом» (privacy:11, terms:10, rules:207-210, refund:11, cookies:11) и строка в футере (Footer.tsx:18-20) статичны, не управляются флагом |
| §2 `docs/LAUNCH_CHECKLIST.md` | не хватает | Файл отсутствует; `NEXT_PUBLIC_SITE_URL` и юр. данные туда не занесены |
| §4 этап 6 — SEO | частично | Базовые метаданные есть; нет JSON-LD, canonical каталогов, OG-картинки, полной sitemap |
| §5 п.4 нет хардкода контактов | противоречит | privacy:77 / terms:80 содержат домен `autoforyou.ua` в placeholder |

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 11-S1 | критично | Не указан владелец (володілець) ПДн — юр. название, код ЄДРПОУ/РНОКПП, адрес; ЗУ «Про захист персональних даних» (ст. 12) требует сообщать субъекту владельца. Issue #10 | privacy/page.tsx:18-22; rules/page.tsx:200; terms/page.tsx:78-81; Footer.tsx:9-10 | Модель «Реквізити компанії» (singleton в админке) + вывод в privacy/terms/refund/rules/футер |
| 11-S2 | критично | Права субъекта (копия данных, удаление, отзыв согласия) заявлены, но механизма нет: нет эндпоинтов удаления/экспорта, `ProfileView` только Retrieve/Update, в `/me` нет кнопок | privacy/page.tsx:67-78; users/urls.py:26-40; users/views.py:52-57 | Эндпоинты `DELETE /api/v1/auth/profile/` и `GET /api/v1/auth/me/export/` + кнопки в `/me` + ссылка из privacy |
| 11-S3 | важно | Перечень собираемых данных не соответствует моделям. Не упомянуты: переписка (messaging/models.py:67), сделки и отзывы (deals/models.py:6, :79), жалобы (reports/models.py:6), объявления с телефоном, который выдаётся другим пользователям (local_listings/models.py:150, local_listings/views.py:378), фото объявлений, заявка дилера — ФИО/компания/телефон (users/models.py:99-101), контакты партнёров (users/models.py:68), сохранённые поиски, избранное, уведомления, платежи, отслеживание контейнеров, VIN-отчёты. Заявленные «переглянуті оголошення» не собираются (трекинга просмотров нет — grep пуст) | privacy/page.tsx:26-33 | Переписать §2 по фактическим моделям, по категориям и целям |
| 11-S4 | важно | Не названы третьи лица-получатели: LiqPay, SMTP-провайдер, провайдеры VIN/реестров (NHTSA, carVertical, Opendatabot), S3/R2, CDN Copart/IAAI; нет раздела о трансграничной передаче (Telegram, облачные хранилища — ст. 29 Закона) | privacy/page.tsx:55-64 | Дополнить §5 списком получателей и трансграничной передачей |
| 11-S5 | важно | Страница cookie юридически закрепляет хранение JWT в localStorage (противоречит брифу §3); при переходе на httpOnly-cookie текст станет ложным | cookies/page.tsx:87-110 | Обновить таблицу одновременно с задачей миграции JWT (этап 1) |
| 11-S6 | важно | Нет срока хранения («[X] років») и не указано право жаловаться Уповноваженому ВР з прав людини (ст. 8 Закона) | privacy/page.tsx:85, :67-78 | Заполнить срок из настроек и добавить пункт о жалобе Омбудсмену |
| 11-S7 | желательно | Согласие на cookie хранится без версии политики и даты — нельзя доказать, на какую редакцию дано согласие и перезапросить при изменении | frontend/lib/consent.ts:15, :47-51 | Хранить `{level, version, ts}`, при смене версии показывать баннер снова |
| 11-S8 | желательно | Нет упоминания возрастного ограничения (дети) и порядка обработки ПДн несовершеннолетних | privacy/page.tsx | Добавить пункт |

Проверено и в порядке: до согласия никаких аналитических/рекламных скриптов не грузится (grep `gtag|next/script|googletagmanager|plausible|clarity|facebook` по frontend/app, components, lib — 0); `cookie_consent` — единственный «несвязанный с входом» ключ; sitemap не содержит приватных URL и ПДн (sitemap.ts:30-57).

## Готовность к конфигурации

| ID | Что захардкожено / placeholder | Файл:строка | Куда вынести |
|---|---|---|---|
| 11-C1 | Реквизиты платформы `[вписати юридичну назву, ЄДРПОУ, адресу, контакти]` | rules/page.tsx:200 | Модель админки `CompanyDetails` (singleton) |
| 11-C2 | Email для обращений `[privacy@autoforyou.ua — заповнити]`, `[email@autoforyou.ua — заповнити]`, `[email — заповнити]` | privacy/page.tsx:77; terms/page.tsx:80; refund/page.tsx:116 | Та же модель (поля `privacy_email`, `support_email`) |
| 11-C3 | Срок хранения `[X] років` | privacy/page.tsx:85 | Модель/настройка `DATA_RETENTION_YEARS` |
| 11-C4 | Дата обновления `[дата — заповнити]` во всех 4 документах | privacy:101; terms:86; refund:140; cookies:159 | Поле `updated_at` документа (модель `LegalDocument` или константа версии) |
| 11-C5 | Плашки «Шаблон — потребує перевірки юристом» показываются публично | privacy:11-13; terms:10-12; rules:207-210; refund:11-13; cookies:11-13 | Флаг `LEGAL_DOCS_APPROVED` (.env/админка), плашка скрывается автоматически |
| 11-C6 | Буквальный текст `{LOCAL_LISTING_MAX_ACTIVE}` выводится пользователю вместо числа | rules/page.tsx:229 | Подставлять значение из API (`core/settings.py:320`, env `LOCAL_LISTING_MAX_ACTIVE`) |
| 11-C7 | Срок объявления «30 днів» захардкожен, при этом есть `LOCAL_LISTING_EXPIRY_DAYS` | rules/page.tsx:185; core/settings.py:324 | Брать из публичного эндпоинта конфигурации |
| 11-C8 | Перечень платных услуг и сроки в таблице захардкожены, хотя тарифы — модель `PromotionTariff` | refund/page.tsx:27-47; local_listings/models.py:38-48 | Рендерить таблицу из `PromotionTariff` |
| 11-C9 | Fallback домена `'https://autoforyou.ua'` продублирован в 4 местах и расходится с docker-дефолтом `http://localhost` | layout.tsx:8; listings/[id]/page.tsx:9; robots.ts:3; sitemap.ts:6; docker-compose.yml:62; Dockerfile.frontend:18 | Один модуль `lib/site.ts`; при отсутствии `NEXT_PUBLIC_SITE_URL` в проде — ошибка сборки, а не молчаливый localhost в canonical/sitemap |
| 11-C10 | `NEXT_PUBLIC_SITE_URL` вшивается на этапе сборки; нет `docs/LAUNCH_CHECKLIST.md` с этим пунктом | Dockerfile.frontend:18-19; .env.example:33 | Внести в LAUNCH_CHECKLIST.md (пересборка фронта после смены домена) |
| 11-C11 | Строка «Тестові тарифи — всі розрахунки є демонстраційними» в футере статична | components/layout/Footer.tsx:18-20 | Показывать по флагу/статусу тарифов из API (как `is_estimate`) |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 11-Q1 | важно | Sitemap берёт только `page=1` каждого списка → максимум ~60 карточек (PAGE_SIZE=20); остальные объявления не попадают в sitemap | sitemap.ts:10-13, :19; core/settings.py:241 |
| 11-Q2 | важно | URL лотов в sitemap (`/listings/{id}-{slug}`, sitemap.ts:45) не совпадают с canonical (`/listings/{id}`, listings/[id]/page.tsx:43) — sitemap из неканонических URL | sitemap.ts:45; listings/[id]/page.tsx:43 |
| 11-Q3 | важно | Двойной суффикс заголовка: юр. страницы задают `'… | AUTOforYOU'`, а корневой template `'%s | AUTOforYOU'` добавляет ещё один → «Політика конфіденційності | AUTOforYOU | AUTOforYOU» | privacy:5; terms:4; rules:5; refund:5; cookies:6; layout.tsx:14 |
| 11-Q4 | важно | robots: правила `'/me/'` и `'/b2b/'` не закрывают `/me` и `/b2b` (префикс со слэшем); `/local/new` не закрыт; `/b2b`, `/local/new`, `/dealers/apply` — client-страницы без noindex, наследуют `index: true` | robots.ts:10-11; layout.tsx:25-28; app/b2b/page.tsx:1; app/local/new/page.tsx:1; app/dealers/apply/page.tsx:1 |
| 11-Q5 | желательно | `/calculator` в sitemap и в allow robots, но с `noindex` — противоречивые сигналы | sitemap.ts:27; robots.ts:7; calculator/layout.tsx:6 |
| 11-Q6 | желательно | Нет canonical у каталогов `/listings`, `/ua` (фильтры/пагинация → дубли) и у `/local/[id]` | listings/page.tsx:11-20; ua/page.tsx:14-23; local/[id]/page.tsx:26-34 |
| 11-Q7 | желательно | Нет JSON-LD (Organization, Vehicle/Offer, BreadcrumbList) ни на одной странице | frontend/app (grep 0) |
| 11-Q8 | желательно | Нет `description` у 5 юр. страниц; нет OG-картинки по умолчанию | privacy:4-6 и др.; layout.tsx:17-21 |
| 11-Q9 | желательно | Terms описывает только импорт из США, не C2C-объявления, платные услуги, применимое право/споры; не ссылается на privacy/rules/refund; показывает пользователю технический термин `is_estimate: true` | terms/page.tsx:29-37 |
| 11-Q10 | желательно | Разметка юр. страниц на 4/5 дублируется (плашка, обёртки `section/h2`, строка даты) — просится общий компонент `LegalPage` | все 5 page.tsx |
| 11-Q11 | желательно | `hasAnalyticsConsent()` не используется — ожидаемо (задел), но без теста гейт может деградировать незаметно | consent.ts:64-66 |
| 11-Q12 | желательно | Ошибка backend при генерации sitemap молча даёт пустой список объявлений (serverGet → null); при сборке в Docker без backend — пустая sitemap до revalidate (не проверено в рантайме) | sitemap.ts:14, :20; lib/server-api.ts:35-38 |

## Тесты

Покрыто (Playwright, frontend/e2e):
- register.spec.ts (5 тестов): ссылки из чекбокса регистрации на `/terms` и `/privacy` открываются (:35-62), футер содержит 4 из 5 ссылок (:64-73) — «Повернення коштів» не проверяется.
- ssr.spec.ts (4 теста): sitemap содержит `/ua` (:44).
- Во всех остальных спеках баннер просто подавляется записью `cookie_consent` (catalog.spec.ts:37, home.spec.ts:14 и др.).
Django-тестов по пакету нет (бэкенд-части нет).

Не покрыто и нужно:
- Playwright: баннер показывается при первом визите; «Лише необхідні»/«Прийняти всі» скрывают его и пишут значение; «Відкликати згоду» на `/cookies` возвращает баннер; до согласия нет сетевых запросов к сторонним доменам (кроме изображений).
- Playwright: `/robots.txt` — закрыты `/me`, `/b2b`, `/local/new`, `/admin/`, `/api/`; `/sitemap.xml` — не содержит `/me`, `/b2b`, `/local/new`, неактивных объявлений, URL лотов совпадают с canonical.
- Playwright: у каждой публичной страницы `<title>` без двойного суффикса, есть `meta description`, `html[lang=uk]`; у приватных — `noindex`.
- Playwright: на юр. страницах нет строк `[... заповнити]`, `{LOCAL_LISTING_MAX_ACTIVE}` и плашки «Шаблон» при включённом флаге одобрения; футер содержит все 5 ссылок.
- Django (после реализации 11-S2): удаление аккаунта и экспорт данных — 200 для владельца, 401 для анонима; экспорт содержит данные всех моделей из 11-S3.
- Unit (vitest/jest, если появится): `consent.ts` — безопасность при недоступном localStorage.

## Итог (≤15 строк)

Готовность пакета ~55%: структура есть (5 документов, баннер, robots, sitemap, базовые метаданные), связка футер/регистрация/форма объявления/заявка дилера работает; аналитики до согласия нет, sitemap без ПДн.
Критично: 11-S1 — нигде нет реквизитов владельца ПДн (issue #10); 11-S2 — права на удаление/выгрузку заявлены, но механизма нет ни на бэкенде, ни в UI.
Важно: 11-S3 политика не соответствует фактическим данным (переписка, сделки, жалобы, телефон в объявлениях, заявка дилера; «просмотры» не собираются); 11-S4 не названы LiqPay/SMTP/VIN-провайдеры/хранилища; 11-S5 cookie-страница фиксирует JWT в localStorage (против брифа §3); 11-S6 нет срока хранения и права жалобы Омбудсмену.
SEO: 11-Q1 sitemap только первые 20 записей каждого списка; 11-Q2 URL лотов в sitemap ≠ canonical; 11-Q3 двойной суффикс title на юр. страницах; 11-Q4 robots не закрывает `/me`, `/b2b`, `/local/new`, у них нет noindex.
Конфигурация: 11-C1…C11 — все контакты/реквизиты/даты/сроки/тарифы захардкожены в TSX, пользователю выводится литерал `{LOCAL_LISTING_MAX_ACTIVE}` (11-C6), плашки «Шаблон» и «Тестові тарифи» статичны, fallback-домен дублирован в 4 файлах, `docs/LAUNCH_CHECKLIST.md` отсутствует.
