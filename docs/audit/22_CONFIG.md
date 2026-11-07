# 22. Конфигурация — черновик LAUNCH_CHECKLIST

Фаза C аудита. Цель — полный список того, что владелец заполняет сам (бриф §2): `.env`, таблицы админки,
внешние аккаунты, а также хардкод, который пока мешает «заполнить без кода».
Источники: grep по коду (`os.environ` / `os.getenv` / `process.env` / `NEXT_PUBLIC_*` / `${VAR}` в compose, Dockerfile, sh,
CI) по всему репозиторию, кроме `venv/`, `.venv/`, `node_modules/`, `.claude/worktrees/`; шаблоны `.env.example`
и `.env.docker.example` (реальный `.env` не читался); отчёты `01…13`. Код не менялся.

Как читать колонки:
- **Прод?** — «да» (без неё прод не работает или небезопасен), «условно» (нужна, если включаете функцию), «нет» (тюнинг).
- **В .env.example?** — `E` = `.env.example`, `D` = `.env.docker.example`, `#` = есть, но закомментирована, `—` = нет ни в одном.

## (а) Переменные окружения

### Django: ядро и безопасность

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `SECRET_KEY` | `core/settings.py:22`; проверка `deploy.sh:23-33` | да | E:12, D:18 | Пусто + `DEBUG=false` → `ImproperlyConfigured`, backend не стартует. Пусто + `DEBUG=true` → известный ключ из репо (`core/settings.py:27`, 01-S10) | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` | `docker compose exec backend python manage.py check --deploy` без W009 |
| `DEBUG` | `core/settings.py:18`; `deploy.sh:47`; compose для worker/beat принудительно `false` (`docker-compose.yml:92,117`) | да (`false`) | E:13, D:23 | `false`. При `true`: выключаются все SECURE_*, Celery в eager (01-C13) | — | Страница 404 без трейсбека; `check --deploy` |
| `ALLOWED_HOSTS` | `core/settings.py:35-46` | да | E:18, D:36 | Пусто на проде → `[]`, Django отвечает 400 на каждый запрос (не падает на старте, 01-Q9) | Домен и `www.` | `curl -I https://домен/api/v1/` ≠ 400 |
| `CORS_ALLOWED_ORIGINS` | `core/settings.py:204-209` | да | E:19, D:37 | Пусто → `http://localhost:3000`, браузер с домена получит CORS-ошибку | `https://домен` | Запрос из браузера с сайта без CORS-ошибки |
| `CORS_ALLOW_ALL_ORIGINS` | `core/settings.py:203`; `deploy.sh:54` | да (`false`) | E:15, D:29 | `false`. `true` + credentials = любой сайт ходит в API от имени пользователя | — | `deploy.sh` откажет при `true` |
| `SECURE_SSL_REDIRECT` | `core/settings.py:423` (только при `DEBUG=false`) | да | E:17, D:34 | `true`. Сейчас без TLS в nginx даёт редирект на несуществующий https (12-S2) | `false` только если редирект делает балансировщик | `curl -I http://домен/api/v1/` → 301 на https |
| `SITE_URL` | `core/settings.py:414`; `telegram_bot/tasks.py:56`; `telegram_bot/handlers.py:87`; `local_listings/services.py:83` | да | E:70 #, D:62 | `https://autoforyou.ua` (чужой/несуществующий домен в ссылках писем и постов, 01-C6/07-C6); в `local_listings/services.py:83` свой дефолт `http://localhost:3000` | Боевой URL сайта | Ссылка в посте канала и в письме о модерации ведёт на ваш домен |

### База данных, кэш, очереди

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `DATABASE_URL` | `core/settings.py:117`; `deploy.sh:40` | да | E:26, D:11 | Пусто → SQLite `db.sqlite3` внутри контейнера (данные пропадут при пересборке) | `postgres://USER:PASS@db:5432/DB` из значений ниже | `python manage.py dbshell` → Postgres; `showmigrations` |
| `POSTGRES_DB` | `docker-compose.yml:10,18` | да | E:23, D:8 | `autoforyou` | Любое имя | `docker compose ps db` healthy |
| `POSTGRES_USER` | `docker-compose.yml:11,18` | да | E:24, D:9 | `postgres` | Любое | То же |
| `POSTGRES_PASSWORD` | `docker-compose.yml:12`; `deploy.sh:35` | да | E:25, D:10 | Обязательна: без неё compose не стартует; dev-пароли отсекает `deploy.sh` | Сгенерировать (≥24 символа) | `docker compose config` без ошибки |
| `REDIS_URL` | `core/settings.py:147`, Celery `:358-365` | да | E:29, D:14 | Пусто → LocMem-кэш в процессе и Celery eager (beat-задачи НБУ, поиски, истечение объявлений идут синхронно/не идут) | `redis://redis:6379/0` (сервис compose) | `docker compose logs celery_worker` — задачи принимаются |
| `COMPOSE_PROJECT_NAME` | Docker Compose (имя volumes); `deploy.sh:72` ждёт `autoforyou-backend-1` | да | E:8 (нет в D, 12-C7) | Имя папки → при другом пути создаются новые пустые volumes | `autoforyou` | `docker volume ls` показывает `autoforyou_*` |

### Веб-сервер и процессы

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `NGINX_PORT` | `docker-compose.yml:130` | нет | E:36, D:90 | `80` | — | `curl http://домен` |
| `GUNICORN_WORKERS` | `docker/entrypoint.sh:27,30` | нет | E:37, D:93 | `3` | 2×CPU+1 | `ps` в контейнере |
| `PORT` | `docker/entrypoint.sh:27,29` | нет | — | `8000` (nginx проксирует на 8000 — менять нельзя без правки nginx) | — | — |

### Фронтенд (Next.js)

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | `frontend/api/client.ts:1`; `frontend/lib/auth-context.tsx:6`; `frontend/lib/server-api.ts:10`; `frontend/next.config.ts:6`; `frontend/app/page.tsx:7`; `frontend/app/listings/[id]/page.tsx:8`; `frontend/app/local/[id]/page.tsx:8`; build-arg `Dockerfile.frontend:15-16`, `docker-compose.yml:61` | да | E:32, D:41 | **Вшивается при сборке.** Compose-дефолт `http://localhost`, код — `http://localhost:8000`: браузеры пользователей пойдут на свой localhost | `https://домен` | DevTools → запросы идут на `https://домен/api/…`; после смены — пересобрать `frontend` |
| `NEXT_PUBLIC_SITE_URL` | `frontend/app/layout.tsx:8`; `frontend/app/robots.ts:3`; `frontend/app/sitemap.ts:6`; `frontend/app/listings/[id]/page.tsx:9`; build-arg `Dockerfile.frontend:18-19`, `docker-compose.yml:62` | да | E:33, D:44 | Вшивается при сборке. Compose → `http://localhost` в canonical/OG/sitemap; вне Docker → `https://autoforyou.ua` (11-C9) | `https://домен` | `/sitemap.xml` и `<link rel=canonical>` с вашим доменом |
| `INTERNAL_API_URL` | `frontend/lib/server-api.ts:10`; `frontend/app/page.tsx:7`; `frontend/app/listings/[id]/page.tsx:8`; `frontend/app/local/[id]/page.tsx:8`; задан в `docker-compose.yml:66` | нет (в Docker задан) | — (есть комментарий D:46) | В Docker `http://backend:8000`; вне Docker → `NEXT_PUBLIC_API_URL` | — | SSR-страница каталога отдаёт лоты |
| `NEXT_PUBLIC_DEMO_MODE` | `frontend/components/ui/DemoBanner.tsx:4` | условно | — (12-C2) | Всё, кроме `'false'`, → демо-баннер показан. В Docker не пробрасывается (нет build-arg) — выключить нельзя без правки | `false` после заполнения тарифов | Баннер «демо» на `/calculator` исчез |
| `E2E_BASE_URL` | `frontend/playwright.config.ts:25` | нет (только тесты) | — | `http://localhost`. **Не указывать боевой домен** — e2e создаёт аккаунты (13-S10) | — | — |
| `CI`, `NODE_ENV` | `frontend/playwright.config.ts:13-14`; `frontend/next.config.ts:3`; `Dockerfile.frontend:26` | служебные | — | Выставляются CI/Docker автоматически | — | — |

### Хранилище медиа (S3 / R2) — по желанию

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `S3_BUCKET_NAME` | `core/settings.py:166` | условно | E:40 #, D:83 # | Пусто → локальный volume `media`. **Внимание 01-C1:** при заданных S3-переменных хранилище всё равно не включится (устаревшие `DEFAULT_FILE_STORAGE`), а `MEDIA_URL` станет S3 → битые ссылки. Не включать до исправления | Консоль AWS S3 / Cloudflare R2 | Загрузить фото объявления, открыть по ссылке |
| `S3_REGION` | `core/settings.py:167` | условно | E:41 #, нет в D | `eu-central-1` | Регион бакета | — |
| `AWS_ACCESS_KEY_ID` | `core/settings.py:168` | условно | E:42 #, D:84 # | Пусто → S3 выключен | IAM-ключ / R2 API token | — |
| `AWS_SECRET_ACCESS_KEY` | `core/settings.py:169` | условно | E:43 #, D:85 # | То же | То же | — |
| `S3_ENDPOINT_URL` | `core/settings.py:170,184` | условно (R2/MinIO) | E:44 #, D:86 # | Пусто → AWS. С R2 `MEDIA_URL` всё равно строится под amazonaws (01-C2/12-C6) | `https://<account>.r2.cloudflarestorage.com` | — |

### Email (SMTP)

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `EMAIL_BACKEND` | `core/settings.py:335-338` | да | E:56 #, D:68 | `console` — **письма молча уходят в лог контейнера** даже на проде (01-C7) | `django.core.mail.backends.smtp.EmailBackend` | `python manage.py sendtestemail you@домен` — письмо пришло |
| `EMAIL_HOST` | `core/settings.py:339` | да | E:57 #, D:69 | `localhost` | SMTP-провайдер | То же |
| `EMAIL_PORT` | `core/settings.py:340` | да | E:58 #, D:70 | `25` | Обычно `587` | То же |
| `EMAIL_USE_TLS` | `core/settings.py:341` | да | E:59 #, D:71 | `false` | `true` для 587 | То же |
| `EMAIL_HOST_USER` | `core/settings.py:342` | да | E:60 #, D:72 | пусто | Логин SMTP | То же |
| `EMAIL_HOST_PASSWORD` | `core/settings.py:343` | да | E:61 #, D:73 | пусто | Пароль / app-password SMTP | То же |
| `DEFAULT_FROM_EMAIL` | `core/settings.py:344` | да | E:62, D:74 | `noreply@autoforyou.ua`. Два сервиса его игнорируют и шлют с захардкоженного адреса (`users/services.py:74`, `local_listings/services.py:62`) | Адрес на вашем домене (SPF/DKIM) | Заголовок From в письме модерации и в письме дилеру |

### LiqPay

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `LIQPAY_PUBLIC_KEY` | `core/settings.py:301`; `payments/liqpay_client.py:37` | условно (платное продвижение) | E:47 (плейсхолдер!), D:52 | Пусто → checkout всё равно создаётся (06-C2); плейсхолдер из E включает «боевой» режим с неверным ключом (03-C1) | Кабинет LiqPay → API | Оплата продвижения в sandbox проходит, `Payment` = completed |
| `LIQPAY_PRIVATE_KEY` | `core/settings.py:302`; `payments/liqpay_client.py:38` | условно | E:48 (плейсхолдер!), D:53 | **Пусто → подпись callback подделывается любым (06-S1, критично).** До исправления не открывать платежи без ключа | Кабинет LiqPay → API | Callback с неверной подписью → отказ |
| `LIQPAY_SANDBOX` | `core/settings.py:303`; `payments/liqpay_client.py:39` | да | E:49, D:51 | `true` (тестовые платежи). Статус `sandbox` засчитывается и при `false` (06-S4) | `false` при запуске реальных платежей | В ответе checkout `sandbox: 0`; баннер «SANDBOX» на фронте захардкожен (10-C1) |

### Telegram

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `core/settings.py:399` (в тестах обнуляется `:406-407`); `telegram_bot/tasks.py:28`; `telegram_bot/views.py:72`; `integrations/tasks.py:68`; `run_bot.py:18`; `set_webhook.py:22`; `unset_webhook.py:15`; `docker/bot_entrypoint.sh:2` | условно (бот) | E:65 #, D:57 | Пусто → бот не стартует (exit 0), уведомления и постинг пропускаются; сайт работает | @BotFather → новый токен (**старый скомпрометирован, 12-S1**) | `docker compose logs bot` без ошибок; `/start` в боте отвечает |
| `TELEGRAM_BOT_USERNAME` | `core/settings.py:408`; `telegram_bot/views.py:34` | условно | E:66 #, D:58 | Пусто → deep-link привязки не построить; фронт показывает захардкоженный `@AUTO_F_Y_bot` (08-C4) | Имя бота без `@` | В `/me/telegram` ссылка открывает ваш бот |
| `TELEGRAM_CHANNEL_ID` | `core/settings.py:409`; `telegram_bot/tasks.py:47-49` | условно | E:67 #, D:59 | Пусто → посты в канал не публикуются | `@channel` или `-100…`; бот — админ канала | Создать тестовый листинг → пост в канале |
| `TELEGRAM_B2B_CHANNEL_ID` | `core/settings.py:410`; `telegram_bot/tasks.py:47` | условно | E:68 #, D:60 | **Пусто → wholesale-лоты уходят в публичный канал (07-S2)** | Закрытый канал для дилеров | Wholesale-лот появляется только в B2B-канале |
| `TELEGRAM_WEBHOOK_SECRET` | `core/settings.py:411`; `telegram_bot/views.py:76-88`; `set_webhook.py:27` | да, если webhook | E:69 #, D:61 | Пусто при заданном токене → webhook отвечает 503; `set_webhook` при этом всё равно ставит webhook без секрета (07-C4) | Случайная строка 32+ символов | `python manage.py set_webhook`, затем `getWebhookInfo` без ошибок |

### Внешние API

| Имя | Где читается | Прод? | В шаблоне? | Дефолт и что будет, если пусто | Где взять | Как проверить |
|---|---|---|---|---|---|---|
| `OPENDATABOT_API_KEY` | `core/settings.py:328`; `integrations/providers.py:254` | условно | E:52 (плейсхолдер!), D:77 | Пусто → `demo: true`. Плейсхолдер из E включает real-режим с неверным ключом, а текст ошибки с ключом уходит пользователю (03-S1) | opendatabot.ua → API | `GET /api/v1/integrations/registry/<номер>/` → `demo: false` |
| `APIFY_TOKEN` | `core/settings.py:331`; `integrations/providers.py:371` | условно | E:53 (плейсхолдер!), D:78 | Пусто → `demo: true`; актор всё равно `YOUR_ACTOR_ID` в коде (03-C2) — импорт не заработает без правки | apify.com → Settings → Integrations | `python manage.py import_lot …` через Apify |

### Бизнес-параметры (тюнинг, все имеют разумный дефолт)

| Имя | Где читается | Прод? | В шаблоне? | Дефолт | Как проверить |
|---|---|---|---|---|---|
| `THROTTLE_ANON_RATE` | `core/settings.py:214` | нет | — | `60/hour` | 61-й анонимный запрос → 429 |
| `THROTTLE_USER_RATE` | `core/settings.py:215` | нет | — | `300/hour` | — |
| `THROTTLE_EXPENSIVE_RATE` | `core/settings.py:216` | нет | — | `10/hour` (VIN/реестры) | 11-й запрос отчёта → 429 |
| `THROTTLE_MESSAGES_RATE` | `core/settings.py:237` | нет | — | `30/hour` (только старт диалога, 06-S6) | — |
| `THROTTLE_CONTACT_RATE` | `core/settings.py:238` | нет | — | `20/hour` (показ телефона) | — |
| `AUCTION_DEFAULT_MEMBER_TYPE` | `core/settings.py:306`; `pricing/views.py:32` | нет | — | `broker`; сериализатор имеет свой дефолт и перекрывает (02-C11) | — |
| `ANTISPAM_MODE` | `core/settings.py:312`; `messaging/services.py:113`; `local_listings/serializers.py:212,268` | нет | — | `soft`. `hard` роняет старт диалога 500 (06-Q1) — не включать | — |
| `SELLER_BADGE_THRESHOLD` | `core/settings.py:316`; `deals/services.py:147`; `local_listings/serializers.py:100` | нет | — | `3` | — |
| `LOCAL_LISTING_MAX_ACTIVE` | `core/settings.py:320`; `local_listings/serializers.py:192` | нет | E:73 # | `10`. На странице правил выводится литерал `{LOCAL_LISTING_MAX_ACTIVE}` (11-C6) | — |
| `LOCAL_LISTING_MAX_PHOTOS` | `core/settings.py:322`; `local_listings/views.py:279` | нет | — | `15` (фронт захардкожен 15, 10-C2) | — |
| `LOCAL_LISTING_PHOTO_MAX_SIZE_MB` | `core/settings.py:323`; `local_listings/views.py:280` | нет | — | `8` (фронт «до 8 МБ», nginx `client_max_body_size 20M`) | — |
| `LOCAL_LISTING_EXPIRY_DAYS` | `core/settings.py:324`; `local_listings/models.py:191` | нет | — | `30` (правила пишут «30 днів» текстом, 11-C7) | — |

### Секреты GitHub Actions (не `.env`)

| Имя | Где | Прод? | Что |
|---|---|---|---|
| `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `SSH_PORT` | `.github/workflows/ci-cd.yml:187-190` | условно (автодеплой) | Доступ к серверу; джоба вызывает внешний `/opt/autoforyou/redeploy.sh`, которого нет в репо (12-C4) |

**Итого:** 55 переменных `.env` (43 читает Django в `core/settings.py`, 7 — Compose/скрипты, 5 — фронтенд), плюс 2 служебные (`CI`, `NODE_ENV`) и 4 секрета GitHub Actions.
В шаблонах отсутствуют 13: `THROTTLE_*` (5), `AUCTION_DEFAULT_MEMBER_TYPE`, `ANTISPAM_MODE`, `SELLER_BADGE_THRESHOLD`, `LOCAL_LISTING_MAX_PHOTOS`, `LOCAL_LISTING_PHOTO_MAX_SIZE_MB`, `LOCAL_LISTING_EXPIRY_DAYS`, `NEXT_PUBLIC_DEMO_MODE`, `PORT` (`INTERNAL_API_URL` и `E2E_BASE_URL` в шаблон не нужны; `S3_REGION` нет в D, `COMPOSE_PROJECT_NAME` нет в D, `frontend/.env.example` нет — 12-C9).

Переменные, которые понадобятся после исправления C-находок (сейчас в коде их нет): `APIFY_ACTOR_ID`, `VIN_REPORT_PROVIDER`, `AUCTION_HISTORY_PROVIDER`, `NBU_MODE`/`NBU_API_URL`, `TELEGRAM_MODE`, `TELEGRAM_BROKER_CHAT_ID`, `CAPTCHA_*` (Turnstile), `SENTRY_DSN`, `JWT_ACCESS_MINUTES`/`JWT_REFRESH_DAYS`, `HSTS_*`, `DOMAIN` (nginx-шаблон), `REDIS_PASSWORD`, `S3_PUBLIC_URL`, `CELERY_EAGER`, `PASSWORD_RESET_TIMEOUT`, `LEGACY_CARS_API_ENABLED`, `CARVERTICAL_API_KEY`.

## (б) Модели в админке, которые заполняет владелец

| # | Модель | Админ-путь | Что заполнить | Placeholder сейчас? | Как проверить |
|---|---|---|---|---|---|
| 1 | `AuctionFeeTier` | `/admin/pricing/auctionfeetier/` | Сетки buyer fee Copart/IAAI по типу участника (broker/public), оплаты, титула; `valid_from` | да — baseline-сетки с `2026-01-01` (`pricing/management/commands/seed_auction_fees.py:15,53-171`, 02-C10) | Расчёт на `/calculator` для $5000 совпадает с прайсом аукциона; тесты используют свой seed (13-C3) |
| 2 | `AuctionFixedFee` | `/admin/pricing/auctionfixedfee/` | Gate / environmental / virtual bid по аукциону и титулу | да — baseline (`seed_auction_fees.py:154,168`) | Строки сборов в разбивке калькулятора |
| 3 | `UsLandRoute` | `/admin/pricing/uslandroute/` | Стоимость «локация аукциона → порт США» | да — плейсхолдер ($500) (`pricing/management/commands/seed_rates.py:46-78`, 02-C9) | Строка «Доставка по США»; при перекрытии периодов берётся старая запись (02-Q4) — не создавать пересекающиеся |
| 4 | `OceanFreightRate` | `/admin/pricing/oceanfreightrate/` | Фрахт «порт США → порт ЕС» | да (`seed_rates.py:46-78`) | Строка «Фрахт». Порты ЕС только Клайпеда/Гданьск (02-C4) |
| 5 | `EuToUaDeliveryRate` | `/admin/pricing/eutouadeliveryrate/` | Доставка «порт ЕС → Украина» | да ($350) | Строка доставки ЕС→UA; доставки по Украине до города нет |
| 6 | `CustomsExciseRate` | `/admin/pricing/customsexciserate/` | Акциз EUR/100 см³ по топливу и объёму, EV EUR/кВт·ч, пошлина, НДС | да — `# ПРОВЕРИТЬ по действующему законодательству`; HEV/PHEV «уточнить у брокера» (`seed_rates.py:110-111`, 02-C14) | Сверить с Митним кодексом/ПКУ; расчёт для бензин 2.0 и EV |
| 7 | `PensionFundBracket` | `/admin/pricing/pensionfundbracket/` | Пороги (в грн) и ставки пенсионного сбора | да — пороги из `LIVING_WAGE_UAH = 3028` × 165/290 в сиде (`seed_rates.py:31,134-140`, 02-C7), `# ПРОВЕРИТЬ` (`pricing/models.py:197`) | Сверить с действующим прожиточным минимумом; расчёт у границ брекета (02-Q2) |
| 8 | `ExchangeRate` | `/admin/pricing/exchangerate/` | Обычно ничего — НБУ грузит ежедневно в 09:00 (beat) | да — демо-курс 41.50 / 0.92 из сида без пометки (`seed_rates.py:82-89`, 02-C8) | Запись за сегодня с курсом НБУ; `python manage.py fetch_nbu_rates` (или задача beat) |
| 9 | `PromotionTariff` | `/admin/local_listings/promotiontariff/` | Цены и сроки RENEW / BUMP / TOP | да — 49/29/99/299 UAH из миграции (`local_listings/migrations/0004_seed_promotion_tariffs.py:3-13`, 05-C1); нет `valid_from/valid_to` (05-C2) | Модалка «Просування» показывает ваши цены; таблица на `/refund` захардкожена отдельно (11-C8) |
| 10 | `Region` | `/admin/local_listings/region/` | Проверить список областей | нет — сид `seed_regions` в `docker/entrypoint.sh:20` | Фильтр «Область» на `/ua` |
| 11 | `City` | `/admin/local_listings/city/` | Проверить/дополнить города | нет — тот же сид | Выбор города в форме объявления |
| 12 | `CustomUser` | `/admin/users/customuser/` | Создать суперпользователя (`createsuperuser`), назначить `is_staff` модераторам. Роли broker нет (01-S7) — брокер сейчас = staff | — | Вход в админку; модерация объявления |
| 13 | `PeriodicTask` (django-celery-beat) | `/admin/django_celery_beat/periodictask/` | Проверить 4 задачи: НБУ 09:00, сохранённые поиски 10:00, предупреждение 09:15, истечение 09:20 | нет, но правка времени перезаписывается из `CELERY_BEAT_SCHEDULE` при старте beat (01-C11) | `docker compose logs celery_beat` — задачи отправляются |

Операционные таблицы (не настройка, ведутся в работе): `Vehicle`/`Listing` (импорт лотов), `Shipment`/`TrackingEvent`, `DealerApplication` (одобрять через action, не полем `status` — 01-Q2), `LocalListing`/`PendingLocalListingProxy` (модерация), `Report`, `Payment`.

**Моделей настроек, которых нет, но бриф требует «заполнить без кода»** (вход для задач; см. (г)):
`SiteSettings`/`CompanyDetails` (реквизиты, контакты, email для обращений, контакт менеджера, срок хранения ПДн), `BrokerNotificationSettings` (chat_id брокера, получатель заявок), модель заявки после расчёта, шаблоны уведомлений (email/in-app/Telegram), настройки калькулятора (текст предупреждения, дефолты формы, возрастной коэффициент, прожиточный минимум), справочник портов, тарифы `listing_unlock`/`listing_vip`, флаг «тарифы проверены» (`is_estimate`/демо-баннер), `IntegrationStatus`, флаги публикации в Telegram-канал, `LegalDocument` (версия/дата/«утверждено юристом»).

## (в) Внешние аккаунты

| Сервис | Что завести | Что получить → куда | Примечание |
|---|---|---|---|
| Telegram — бот | Бот в @BotFather (**текущий токен отозвать, 12-S1**) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`; сгенерировать `TELEGRAM_WEBHOOK_SECRET`; выполнить `python manage.py set_webhook` на `https://домен/api/v1/telegram/webhook/` | Без HTTPS webhook не работает (12-S2) |
| Telegram — публичный канал | Канал, бот — администратор с правом публикации | `TELEGRAM_CHANNEL_ID` (`@name` или `-100…`) | До исправления 04-S1/07-S1 любой залогиненный может отправить пост через создание `Listing` |
| Telegram — B2B-канал | Закрытый канал для верифицированных дилеров, бот — админ | `TELEGRAM_B2B_CHANNEL_ID` | Обязательно, иначе wholesale уходит в публичный канал (07-S2) |
| Telegram — чат брокера | Группа/личный чат брокера для заявок | chat_id — **некуда вписать**: настройки нет (07-C1), заявок нет (02-Q1) | Появится после задачи «заявка брокеру» |
| LiqPay | Мерчант-аккаунт (ФОП/ТОВ, требует реквизитов #10) | `LIQPAY_PUBLIC_KEY`, `LIQPAY_PRIVATE_KEY`; в кабинете указать `server_url` = `https://домен/api/v1/payments/liqpay/callback/` (checkout продвижения его не передаёт, 06-C3) | Сначала sandbox; `LIQPAY_SANDBOX=false` только после исправления 06-S1…S4 |
| SMTP | Транзакционный провайдер (Brevo, Mailgun, SES, Gmail app-password) + SPF/DKIM/DMARC на домене | `EMAIL_*`, `DEFAULT_FROM_EMAIL` | Сейчас по умолчанию письма идут в консоль (01-C7) |
| НБУ | Ключ не нужен | — (URL в коде `pricing/nbu.py:29-32`) | Проверить, что beat-задача работает, демо-курс сида перезаписан |
| NHTSA vPIC | Ключ не нужен | — (URL в коде `integrations/providers.py:56`) | Используется для VIN-префилла |
| carVertical | Партнёрский API-аккаунт | ключ — **некуда вписать**: реальной реализации нет, фабрика всегда stub (03-C4) | После задачи адаптера: `CARVERTICAL_API_KEY`, `VIN_REPORT_PROVIDER` |
| Opendatabot | API-подписка | `OPENDATABOT_API_KEY` | Не включать до исправления 03-S1 (ключ утекает в ответ) |
| Apify / источник лотов | Аккаунт Apify + выбранный актор Copart/IAAI (или другой источник) | `APIFY_TOKEN`; ID актора — **некуда вписать** (`YOUR_ACTOR_ID` в `integrations/providers.py:351`, 03-C2) | Права на данные/фото — решение #11 |
| Домен / DNS | Домен, A/AAAA-записи на VPS; MX/SPF/DKIM для почты | `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `SITE_URL`, `NEXT_PUBLIC_*` (пересборка фронта) | `server_name localhost` захардкожен в nginx (12-C3) |
| TLS-сертификат | Let's Encrypt (certbot / acme-контейнер) | Файлы сертификата в volume nginx | Конфигурации 443 нет (12-S2); HSTS preload — отдельное решение (01-S18) |
| S3 / Cloudflare R2 | Бакет + ключ доступа (опционально) | `S3_*`, `AWS_*` | Не включать до исправления 01-C1/01-C2 |
| Sentry / GlitchTip | Проект (бесплатный тариф) | `SENTRY_DSN` — **некуда вписать**, sdk нет (12-S13) | После задачи мониторинга |
| Капча (Turnstile/hCaptcha) | Сайт в Cloudflare Turnstile (бесплатно) | ключи — **некуда вписать** (01-S5) | После задачи антибота |
| VPS + бэкапы | Сервер с Docker; внешнее хранилище для дампов | SSH-секреты GitHub (если автодеплой) | Скрипта бэкапа нет (12-S6) |

## (г) Хардкод, мешающий «заполнить без кода» (C-находки, дедуплицировано)

| № | ID | Что | Файл:строка | Куда должно уйти |
|---|---|---|---|---|
| 1 | 01-C1 | S3 через удалённые в Django 5.1 `DEFAULT_FILE_STORAGE`/`STATICFILES_STORAGE`; `MEDIA_ROOT` не задан при S3 | `core/settings.py:174-191` | Словарь `STORAGES`, `MEDIA_ROOT` всегда |
| 2 | 01-C2, 12-C6 | `MEDIA_URL` под amazonaws, игнорирует `S3_ENDPOINT_URL` (R2) | `core/settings.py:187-191` | `.env`: `S3_PUBLIC_URL` / `AWS_S3_CUSTOM_DOMAIN` |
| 3 | 01-C3, 03-C10, 04-C4, 05-C3 | Отправитель `noreply@autoforyou.ua` захардкожен; `fail_silently=True` | `users/services.py:74`; `local_listings/services.py:62` | `settings.DEFAULT_FROM_EMAIL` + статус SMTP |
| 4 | 01-C4, 06-C5, 07-C2 | Тексты писем, уведомлений (сделки, сообщения) и бота/постов захардкожены (RU/UA вперемешку) | `users/services.py:67-72`; `deals/services.py:53-140`; `messaging/services.py:149-153`; `telegram_bot/handlers.py:20-44,84,91,130-134`; `telegram_bot/tasks.py:57-63,75`; `telegram_bot/views.py:43` | Модель шаблонов уведомлений в админке (ключ → текст) |
| 5 | 01-C5, 04-C5 | TODO «промт 7/11»: Telegram-уведомление дилеру, перенос фото лотов в хранилище | `users/services.py:8,73`; `vehicles/models.py:43` | Адаптер уведомлений; задача хранения фото (после #11) |
| 6 | 01-C6, 07-C6, 12-C5 | Дефолт `SITE_URL = https://autoforyou.ua` (в 3 местах бэкенда) и `DEFAULT_FROM_EMAIL` на чужом домене | `core/settings.py:344,414`; `telegram_bot/handlers.py:87`; `telegram_bot/tasks.py:56`; `.env.example:62` | Только `.env`, без боевого дефолта; `check` при пустом в проде |
| 7 | 01-C7 | Email по умолчанию console и на проде, без статуса «не настроено» | `core/settings.py:335-338` | Проверка при старте / статус в админке |
| 8 | 01-C8 | Insecure `SECRET_KEY` в репо как dev-фолбэк | `core/settings.py:27` | Генерация при старте dev |
| 9 | 01-C9 | Жизнь JWT 15 мин / 7 дней | `core/settings.py:348-349` | `.env`: `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS` |
| 10 | 01-C10 | HSTS 1 год, preload, subdomains | `core/settings.py:424-426` | `.env`, preload по умолчанию выкл. |
| 11 | 01-C11 | Расписание beat в settings перезаписывает правки в админке | `core/settings.py:368-394` | Data-миграция `PeriodicTask` |
| 12 | 01-C12 | Описание API и `UserRoleEnum` без broker | `core/settings.py:272,276-281` | Обновить с ролью broker |
| 13 | 01-C13 | Celery eager привязан к `DEBUG` | `core/settings.py:358-365` | `.env`: `CELERY_EAGER` |
| 14 | 01-C14 | `LANGUAGE_CODE='ru-ru'` при украинском UI | `core/settings.py:137` | `uk` / `.env` |
| 15 | 02-C1, 09-C6, 08-C6 | Текст предупреждения калькулятора с датой «янв–чер 2026», текст демо-баннера | `pricing/views.py:344-348`; `frontend/components/ui/DemoBanner.tsx:16-18` | Модель настроек калькулятора |
| 16 | 02-C2, 02-C3, 09-C3, 08-C2, 11-C11, 12-C2 | `is_estimate=True` константой; демо-баннер — build-флаг (в Docker не пробрасывается); «Тестові тарифи» в футере и на главной статично | `pricing/views.py:335,341`; `pricing/calculator.py:140`; `frontend/components/ui/DemoBanner.tsx:4`; `frontend/components/calculator/CalcBreakdown.tsx:18`; `frontend/components/layout/Footer.tsx:18-20`; `frontend/app/page.tsx:118-120`; `Dockerfile.frontend:15-19` | Признак «тариф проверен» у тарифных моделей → `is_estimate`/`is_demo` в API → баннеры по данным |
| 17 | 02-C4, 04-C2 | Порты ЕС только Клайпеда/Гданьск в `TextChoices` (тарифы и контейнеры) | `pricing/models.py:112-114,129-131`; `pricing/serializers.py:27`; `shipments/models.py:27-29` | Справочник портов в админке |
| 18 | 02-C5, 09-C1 | Справочники калькулятора (аукционы, порты, локации, топливо; нет PHEV и поля батареи) во фронте | `frontend/app/calculator/page.tsx:71-74,86-87,94-96,103-104,111-112` | Отдавать из API по активным тарифам |
| 19 | 02-C6 | Формула возрастного коэффициента (min 1, max 15) | `pricing/calculator.py:148-155` | Параметры в `CustomsExciseRate`/настройках растаможки |
| 20 | 02-C7 | Прожиточный минимум 3028 и множители 165×/290× в сиде | `pricing/management/commands/seed_rates.py:31,134-140` | Модель «прожиточный минимум по датам» |
| 21 | 02-C8 | Демо-курс 41.50 / 0.92 без пометки | `pricing/management/commands/seed_rates.py:82-89` | Demo-адаптер НБУ, `NBU_MODE` |
| 22 | 02-C9, 02-C10 | Плейсхолдер-логистика и baseline-сетки аукционов в сидах | `seed_rates.py:46-78`; `seed_auction_fees.py:15,53-171` | Админка + LAUNCH_CHECKLIST (раздел б) |
| 23 | 02-C11, 09-C5 | Дефолты `payment_type`/`title_type`/`member_type` в сериализаторе (settings не используется), дефолты формы | `pricing/serializers.py:22-24`; `pricing/views.py:32,155-158`; `frontend/app/calculator/page.tsx:10-19` | Один источник: настройки калькулятора |
| 24 | 02-C12 | URL НБУ в коде | `pricing/nbu.py:29-32` | `.env` внутри адаптера |
| 25 | 02-C13, 09-C2, 08-C3 | «Пошлина 10%», «НДС 20%», «Акциз 50–150 €/л», порты — текстом во фронте | `frontend/components/calculator/CalcBreakdown.tsx:35-36`; `frontend/app/page.tsx:83-90` | Ставки из `rates_snapshot` / `/pricing/rates/` |
| 26 | 02-C14 | Акциз HEV/PHEV «уточнить у брокера» | `seed_rates.py:110-111` | Админка + вопрос владельцу |
| 27 | 03-C1 | Непустые плейсхолдеры `OPENDATABOT_API_KEY`, `APIFY_TOKEN`, `LIQPAY_*` в `.env.example` включают real-режим | `.env.example:47-48,52-53` | Пустые значения; плейсхолдер = «не настроено» |
| 28 | 03-C2 | `YOUR_ACTOR_ID` Apify в коде | `integrations/providers.py:351` | `.env`: `APIFY_ACTOR_ID` |
| 29 | 03-C3, 06-C4 | Базовые URL NHTSA, Opendatabot, LiqPay в коде | `integrations/providers.py:56,149-152`; `payments/liqpay_client.py:19-20` | Допустимо как константы; Opendatabot сверить |
| 30 | 03-C4, 06-C2, 07-C3, 05-C7 | Нет адаптеров real/demo и переключателя в `.env`: VIN/BidFax — всегда stub, LiqPay и Telegram — прямые вызовы; checkout без ключей не блокируется | `integrations/providers.py:244-249`; `payments/liqpay_client.py:33-40`; `local_listings/views.py:393-441`; `telegram_bot/tasks.py:72`; `telegram_bot/views.py:109`; `integrations/tasks.py:88` | Интерфейсы провайдеров + `*_PROVIDER`/`*_MODE` в `.env` |
| 31 | 03-C5, 07-C5 | Нет статуса интеграций в админке | `integrations/admin.py:1-19` | Модель/страница `IntegrationStatus` |
| 32 | 03-C6 | Кэш VIN/реестров навсегда | `integrations/views.py:50,103,165-167` | `.env`: `VIN_REPORT_CACHE_DAYS`, `REGISTRY_CACHE_DAYS` |
| 33 | 03-C7 | Демо-строки (`Toyota`, `Copart Dallas`, 8500) в ответах | `integrations/providers.py:34-49,136-141,171,196` | Убрать фейковые поля, `configured: false` |
| 34 | 03-C8, 04-C3 | Фолбэки импорта `year=2000`, `Unknown`, `petrol`, `price=0`, `in_transit`, `retail` | `integrations/providers.py:281-283,293`; `integrations/importer.py:38-45,60-70` | Отклонять/черновик; канал — настройка |
| 35 | 03-C9 | Таймауты 10/60/15 с | `integrations/providers.py:82,209,358`; `upload_lot_photos.py:59` | `.env` (желательно) |
| 36 | 04-C1 | Ставки legacy-калькулятора | `cars/views.py:34-42` | По решению владельца не трогать; флаг `LEGACY_CARS_API_ENABLED` |
| 37 | 04-C6, 10-C4 | Размер страницы 20 (бэкенд и фронт) | `core/settings.py:241`; `frontend/app/ua/LocalCatalogGrid.tsx:6` | Фронт — по `next`/`count` |
| 38 | 05-C1 | Placeholder-цены продвижения без пометки демо | `local_listings/migrations/0004_seed_promotion_tariffs.py:3-13`; `local_listings/views.py:383-390` | Флаг `is_demo` + LAUNCH_CHECKLIST |
| 39 | 05-C2 | `PromotionTariff` без `valid_from/valid_to` | `local_listings/models.py:38-51` | Поля периода |
| 40 | 05-C4 | Предупреждение «за 3 дня» | `local_listings/tasks.py:16` | `.env`: `LOCAL_LISTING_EXPIRY_WARN_DAYS` |
| 41 | 05-C5, 10-C6 | Лимит 10 объявлений в рассылке, «раз в сутки» (и текст на фронте) | `saved_searches/tasks.py:33`; `core/settings.py:380-383`; `SaveSearchButton.tsx:94` | `.env` / настройки |
| 42 | 05-C6, 06-C10, 12-C1 | Переменные читаются кодом, но нет в `.env*.example` | `core/settings.py:214-238,306-324` | Оба шаблона + LAUNCH_CHECKLIST (см. (а)) |
| 43 | 06-C1 | Нет цены `listing_unlock`/`listing_vip` — сумма от клиента | `payments/serializers.py:18-26` | Модель тарифов в админке |
| 44 | 06-C3 | Checkout продвижения не передаёт `server_url`/`result_url` | `local_listings/views.py:436-441` | Из `SITE_URL` / `LIQPAY_SERVER_URL` |
| 45 | 06-C6 | Текст предупреждения антиспама | `messaging/views.py:118-121` | Допустимо; по желанию — админка |
| 46 | 06-C7 | Лимит 50 уведомлений | `notifications/views.py:15` | Пагинация DRF |
| 47 | 06-C8, 07-C1 | Получатель импортных диалогов — «первый is_staff»; chat_id брокера для заявок отсутствует | `messaging/services.py:17-18` | Роль broker + `BrokerNotificationSettings` (`TELEGRAM_BROKER_CHAT_ID`) |
| 48 | 06-C9 | Валюта `Payment` по умолчанию USD, список валют в коде | `payments/models.py:48`; `payments/serializers.py:7` | Валюта из тарифа |
| 49 | 07-C4 | `set_webhook` ставит webhook без секрета | `telegram_bot/management/commands/set_webhook.py:27,41` | `CommandError` при пустом секрете; URL из `SITE_URL` |
| 50 | 07-C7 | Пауза 3 с и повторы постинга | `telegram_bot/tasks.py:10,16` | Celery `rate_limit` из settings |
| 51 | 07-C8 | Правила «что публиковать в канал» в сигнале | `telegram_bot/signals.py:9-11`; `core/settings.py:409-410` | Флаги публикации в админке |
| 52 | 08-C1, 08-C7, 11-C1, 11-C2 | Нет реквизитов и контактов в подвале; `[вписати…]` в правилах; email для обращений `[… заповнити]`; «Зверніться до менеджера» без контакта | `frontend/components/layout/Footer.tsx:9-20`; `frontend/app/rules/page.tsx:110`; `frontend/app/privacy/page.tsx:77`; `frontend/app/terms/page.tsx:80`; `frontend/app/refund/page.tsx:116`; `frontend/app/me/shipments/page.tsx:49` | Singleton `SiteSettings`/`CompanyDetails` в админке → SSR |
| 53 | 08-C4 | Имя бота `@AUTO_F_Y_bot` и «30 хвилин» | `frontend/app/me/telegram/page.tsx:107,109` | Из ответа link-token (`expires_at`) / `TELEGRAM_BOT_USERNAME` |
| 54 | 08-C5, 09-C4, 11-C9, 10-C7 | Фолбэки `http://localhost:8000` и `https://autoforyou.ua` в 8+ файлах фронта; дубль базового URL | `frontend/api/client.ts:1`; `frontend/lib/auth-context.tsx:6`; `frontend/lib/server-api.ts:10`; `frontend/app/page.tsx:7`; `frontend/next.config.ts:6`; `frontend/app/layout.tsx:8`; `frontend/app/listings/[id]/page.tsx:8-9`; `frontend/app/robots.ts:3`; `frontend/app/sitemap.ts:6`; `frontend/app/local/[id]/page.tsx:8-18` | Единый `lib/config.ts`, ошибка сборки без переменных |
| 55 | 08-C8 | Хосты Copart/IAAI/CDN в `remotePatterns` | `frontend/next.config.ts:27-33` | `.env` (список хостов) |
| 56 | 10-C1 | Баннер «Тестовий режим (SANDBOX)» всегда | `frontend/components/.../PromoteModal.tsx:70-74` | Флаг `sandbox` из API |
| 57 | 10-C2, 11-C6, 11-C7 | Лимиты C2C во фронте: 15 фото, 8 МБ, литерал `{LOCAL_LISTING_MAX_ACTIVE}`, «30 днів» | `LocalListingForm.tsx:14,31,36`; `PhotoUploadBlock.tsx:67,72,99`; `frontend/app/rules/page.tsx:95,33` | Публичный `/config/` из settings |
| 58 | 10-C3 | Максимальный год 2026 в форме | `LocalListingForm.tsx:248` | `new Date().getFullYear()+1` |
| 59 | 10-C5 | Справочники топлива/КПП/кузова продублированы в 4 местах | `LocalListingCard.tsx:5-10`; `LocalListingFilters.tsx:89-135`; `LocalListingForm.tsx:262-298`; `LocalListingDetail.tsx:15-27` | `lib/labels.ts` или choices из API |
| 60 | 11-C3 | Срок хранения `[X] років` | `frontend/app/privacy/page.tsx:85` | `SiteSettings` / `DATA_RETENTION_YEARS` |
| 61 | 11-C4 | `[дата — заповнити]` в 4 документах | privacy:101; terms:85; refund:140; cookies:159 | `LegalDocument.updated_at`/версия |
| 62 | 11-C5 | Плашки «Шаблон — потребує перевірки юристом» публично | privacy:11-13; terms:11; rules:11-14; refund:11-13; cookies:11-13 | Флаг `LEGAL_DOCS_APPROVED` |
| 63 | 11-C8 | Таблица платных услуг на `/refund` захардкожена | `frontend/app/refund/page.tsx:27-47` | Рендер из `PromotionTariff` |
| 64 | 11-C10 | `NEXT_PUBLIC_SITE_URL` вшивается при сборке — нужна пересборка при смене домена | `Dockerfile.frontend:18-19` | Пункт LAUNCH_CHECKLIST (или runtime-конфиг) |
| 65 | 12-C3 | `server_name localhost` и пути сертификатов в nginx | `nginx/nginx.conf:11,57-58` | Шаблон nginx + `DOMAIN` в `.env` |
| 66 | 12-C4 | Деплой привязан к EC2 и внешнему `/opt/autoforyou/redeploy.sh` | `.github/workflows/ci-cd.yml:179,192` | Скрипт в репо, джоба по флагу |
| 67 | 12-C7 | Имя контейнера `autoforyou-backend-1`; нет `COMPOSE_PROJECT_NAME` в Docker-шаблоне | `deploy.sh:72`; `.env.docker.example` | `docker compose ps -q backend` + переменная в шаблоне |
| 68 | 12-C8 | Dev-пароль/ключ в Docker-шаблоне | `.env.docker.example:10-11,18` | Допустимо — `deploy.sh:23-38` отсекает |
| 69 | 12-C9 | Нет `frontend/.env.example` | `frontend/` | Создать |
| 70 | 12-C10 | `--timeout 120`, `client_max_body_size 20M` не синхронизированы с лимитом фото | `docker/entrypoint.sh:31`; `nginx/nginx.conf:13` | `GUNICORN_TIMEOUT`, лимит через шаблон nginx |
| 71 | 13-C1 | Тесты наследуют `.env`, ключи провайдеров (кроме Telegram) не обнуляются | `core/settings.py:14,302,328,331,406-407` | Обнулять под `_testing` / `settings_test` |
| 72 | 13-C2 | При `REDIS_URL` и `DEBUG=false` тесты чистят живой Redis и шлют задачи в брокер | `core/settings.py:145-156,358-365` | LocMem + eager в тестах |
| 73 | 13-C3 | Тесты завязаны на placeholder-значения сидов | `pricing/tests.py:711-758`; `tests/test_e2e.py:222-239` | Задокументировать: тесты не зависят от данных админки |
| 74 | 13-C4 | E2E зависят от данных стека, фикстур нет | `docker/entrypoint.sh:20-22`; `frontend/e2e/home.spec.ts:4-7` | Фикстуры в `globalSetup` |
| 75 | 13-C5 | Playwright `baseURL` по умолчанию `http://localhost`, нет `webServer` | `frontend/playwright.config.ts:25` | Проверка готовности стека |

**Итого: 122 C-ID из 13 отчётов → 75 уникальных строк.** Строки 29, 45 и 68 — «допустимо», их можно не брать в задачи.

## (д) Решения владельца, которые не являются данными

| # | Вопрос | Что блокирует | Источник |
|---|---|---|---|
| 1 | **Issue #10 — реквизиты юрлица:** кто владелец ПДн и продавец платных услуг (ФОП/ТОВ, название, ЄДРПОУ/РНОКПП, адрес, email для обращений, телефон) | Политика (ст. 12 ЗУ), футер, договор-оферта, мерчант LiqPay | 11-S1, 11-C1, 11-C2, 08-C1 |
| 2 | **Issue #11 — права на фото Copart/IAAI:** хотлинк, копирование к себе, показ в og:image и Telegram, атрибуция или заглушки | `upload_lot_photos`, remotePatterns, SEO-карточки, посты канала | 09-S3, 03-S5, 04-C5 |
| 3 | Срок хранения персональных данных (лет) | Политика §6, задача очистки | 11-S6, 11-C3 |
| 4 | Является ли тарифная сетка брокера (`GET /pricing/rates/`) коммерческой тайной | Открыт ли эндпоинт анонимам | 02-S3 |
| 5 | Legacy `/api/calculate/` (решено «не трогать») — подтвердить: отключить флагом или оставить с `is_estimate` | Риск «точной» цены на хардкод-ставках | 04-S3, 04-C1 |
| 6 | Включать ли HSTS `preload` и `includeSubDomains` (почти необратимо) | Заголовки прода | 01-S18, 01-C10 |
| 7 | Состав расчёта: услуги/комиссия брокера, доставка по Украине до города, таможенная стоимость (с доставкой до границы или без), разбивка акциза HEV/PHEV | Структура моделей тарифов | 02-Q7, 02-C14, 09-Q5 |
| 8 | Нужна ли отдельная роль модератора или модерирует broker/admin | Модель ролей | 05 (Итог), 01-S7 |
| 9 | Провайдер капчи (Turnstile / hCaptcha) и SMTP-провайдер | Задачи этапа 1 и 3 | 01-S5, 01-C7 |
| 10 | Юридическая вычитка документов (снятие плашек «Шаблон») | Флаг `LEGAL_DOCS_APPROVED` | 11-C5 |
| 11 | Где хранить копии бэкапов вне сервера | Задача бэкапов | 12-S6 |
