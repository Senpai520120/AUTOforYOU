# Аудит: Пакет 12 «Инфраструктура»

Дата: 2026-09-25. Ветка `finish-site`. Код не менялся, контейнеры не запускались.
Реальные `.env` / `frontend/.env.local` не читались, проверено только их отслеживание в git.

## Состав

| Файл | Строк | Назначение |
|---|---|---|
| `Dockerfile` | 6 | Node-образ из корня (`node server.js`). В корне нет ни `package.json`, ни `server.js`, так что файл мёртвый |
| `Dockerfile.backend` | 33 | Django: двухстадийная сборка на python:3.12-slim. Используется для сервисов backend, bot, celery_worker и celery_beat |
| `Dockerfile.frontend` | 34 | Next.js: три стадии (deps, build, runtime) на node:20-alpine, запуск через `npm start` |
| `docker-compose.yml` | 145 | 8 сервисов: db (postgres:18), redis, backend, frontend, bot, celery_worker, celery_beat, nginx. Других compose-файлов нет |
| `docker/entrypoint.sh` | 33 | migrate → seed_* → collectstatic → gunicorn |
| `docker/bot_entrypoint.sh` | 8 | `run_bot`, либо exit 0, если токена нет |
| `nginx/nginx.conf` | 62 | Прокси `/api` и `/admin` на backend, `/` на frontend, отдача `/static` и `/media`. Только порт 80 |
| `deploy.sh` | 75 | Pre-flight проверки переменных, затем `docker compose up -d` |
| `.github/workflows/ci-cd.yml` | 192 | Джобы: backend, frontend, e2e (стек в Docker + Playwright) и deploy (SSH на AWS EC2) |
| `.env.example` | 73 | Шаблон для прода |
| `.env.docker.example` | 93 | Шаблон для локального Docker-стека |
| `requirements.txt` | 25 | 19 закреплённых top-level зависимостей |
| `frontend/package.json` | 33 | Next 16.2.9, React 19.2.4; devDependencies указаны с `^` (есть lock-файл) |
| `ruff.toml` | 19 | Правила E, F, I; E501 выключен |
| `.gitignore` | 53 | Корневой |
| `frontend/.gitignore` | 47 | Фронтенд |
| `.dockerignore` | 20 | Контекст backend |
| `frontend/.dockerignore` | 8 | Контекст frontend |
| `DEPLOY_NOTES.md` | 266 | Только сверка |

Моделей и эндпоинтов в пакете нет. Смежные файлы, прочитанные точечно: `core/settings.py` (секции безопасности, Celery, S3), `core/__init__.py`, `frontend/next.config.ts`.

**Проверка через `git ls-files`.** Файлы `.env`, `frontend/.env.local`, `db.sqlite3`, `dump.sql`, `backups/`, `pgdata/`, `media/` в git не попадают, их игнорируют `.gitignore:14,15,30-41` и `frontend/.gitignore:34`. Поиск по истории (`git log --all --diff-filter=A`) тоже ничего не нашёл. Локально эти файлы есть (`pgdata/` 51 МБ, `dump.sql` 352 КБ, `backups/*.sqlite3`, `backups/win_dump.sql`), но они игнорируются.
**Однако в git отслеживается `.claude/settings.local.json`, хотя `.claude/` стоит в `.gitignore:44`, и в нём лежит реальный токен Telegram-бота (12-S1). Репозиторий публичный: `gh repo view` показывает `PUBLIC`.**

## Функции

| Функция | Состояние | Файл:строки | Комментарий |
|---|---|---|---|
| Сборка backend-образа | готово | `Dockerfile.backend:1-33` | Multi-stage, но образ работает от root, а в `COPY . .` попадает лишнее (12-S4) |
| Сборка frontend-образа | частично | `Dockerfile.frontend:1-34` | Работает. Внутри root, в runtime попадают все `node_modules` вместе с dev-зависимостями, `NEXT_PUBLIC_DEMO_MODE` не пробрасывается |
| Корневой `Dockerfile` | сломано | `Dockerfile:1-7` | Ссылается на несуществующие в корне `package.json` и `server.js` |
| Compose: Postgres | готово | `docker-compose.yml:4-23` | Порт открыт только на `127.0.0.1:5433`, пароль обязателен (`:?`), есть healthcheck |
| Compose: Redis | частично | `docker-compose.yml:26-28` | Наружу не открыт. Нет healthcheck, volume и пароля (сеть внутренняя) |
| Compose: Celery worker + beat | готово | `docker-compose.yml:85-124` | Есть. beat работает с DatabaseScheduler. У обоих нет healthcheck и зависимости от миграций |
| Compose: bot | готово | `docker-compose.yml:70-82`, `docker/bot_entrypoint.sh:1-8` | Без токена корректно завершается с exit 0 |
| Gunicorn | частично | `docker/entrypoint.sh:28-33` | sync-воркеры, timeout 120, нет `--max-requests` и `--graceful-timeout` |
| Запуск стека на Windows-машине | сломано | `docker/entrypoint.sh` (CRLF), нет `.gitattributes` | backend в цикле рестартов (12-Q14) |
| Миграции и сиды при старте | готово | `docker/entrypoint.sh:5-22` | Ошибки сидов теперь видны в логе |
| Статика и медиа | частично | `nginx/nginx.conf:16-27`, `docker-compose.yml:43-44,133-134` | Раздаются. Медиа публичные, без `nosniff` |
| HTTPS / TLS | отсутствует | `nginx/nginx.conf:54-61` | Только закомментированная заготовка |
| HSTS / CSP / защитные заголовки | частично | `core/settings.py:419-431` | Выставляются только ответами Django (`/api`, `/admin`). Для страниц Next.js их нет, CSP нет нигде |
| Лимит размера загрузки | готово | `nginx/nginx.conf:13` | 20M |
| Healthchecks | частично | `docker-compose.yml:17-22,46-51` | Есть только у db и backend, причём у backend это TCP-проверка |
| Бэкапы Postgres | отсутствует | — | Нет ни скрипта, ни расписания, ни ротации, ни проверки восстановления |
| Мониторинг ошибок (Sentry и т.п.) | отсутствует | `requirements.txt` | sentry-sdk нет, `LOGGING` в settings не настроен |
| Логирование без ПДн | частично | `docker/entrypoint.sh:32`, nginx по умолчанию | Access-логи пишут полный URL с query-строкой и IP. Ротации логов нет |
| deploy.sh (под любой VPS) | сломано | `deploy.sh:8-19,72` | Не читает `.env`, поэтому без `export` всегда падает. Имя контейнера захардкожено |
| CI: backend (ruff, check, makemigrations --check, migrate, test, openapi) | готово | `ci-cd.yml:11-77` | Postgres 16, тогда как в compose 18 |
| CI: frontend (lint, tsc, build) | готово | `ci-cd.yml:80-103` | — |
| CI: e2e (полный стек в Docker + Playwright) | готово | `ci-cd.yml:106-175` | — |
| CI: обязательность | готово | GitHub branch protection | `required_status_checks`: Backend checks, Frontend checks, E2E tests |
| CI: deploy | сломано | `ci-cd.yml:178-192` | На main падает при каждом push: `dial tcp ***: i/o timeout` (5 последних запусков красные) |
| Шаблоны `.env*.example` | частично | `.env.example`, `.env.docker.example` | Не хватает ряда переменных (12-C1). Нет `frontend/.env.example` |
| Закреплённые версии | частично | `requirements.txt:1-25`, `package.json:17-32` | Top-level закреплены, транзитивные нет. Docker-образы на плавающих тегах |
| Два venv в корне | сломано | `venv/`, `.venv/` | В `venv/` нет celery, django_redis и gunicorn. `core/__init__.py:1` импортирует celery, поэтому любой `manage.py` из `venv/` падает |
| DEPLOY_NOTES.md | устарел | `DEPLOY_NOTES.md:7-20,52,146-171,227-233` | Описывает SQLite, бэкап через dumpdata и «119 тестов», бота из терминала. Про Docker, deploy.sh и HTTPS там ничего нет |

## Сверка с BRIEF.md

| Пункт брифа | Статус | Комментарий |
|---|---|---|
| §3 «секреты только в `.env`» | **противоречит** | Токен бота лежит в отслеживаемом `.claude/settings.local.json:58` (12-S1). Остальные секреты только в env: `core/settings.py:22-31,301-302,328-343`, `deploy.sh:17-43` |
| §3 HTTPS | **не хватает** | В nginx только порт 80 (`nginx/nginx.conf:10`), TLS закомментирован (12-S2) |
| §3 HSTS, CSP и безопасные заголовки | **частично** | HSTS, X-Frame и nosniff отдаёт только Django. CSP нет, заголовков на страницах Next.js нет (12-S3) |
| §3 порт БД не наружу | совпадает | `docker-compose.yml:8` открывает `127.0.0.1:5433`. У Redis портов нет (`:26-28`) |
| §3 бэкапы Postgres | **не хватает** | Ничего нет (12-S6) |
| §3 логирование без личных данных | **частично** | Нет `LOGGING` и фильтров, access-логи пишутся с query-строкой и без ротации (12-S8) |
| §3 защита от перебора по IP | **противоречит (инфра-часть)** | IP клиента для DRF-throttling подменяется через `X-Forwarded-For` (12-S9) |
| §2 «всё настраивается без правки кода» | **частично** | Домен в `nginx.conf:11`, дефолты `autoforyou.ua` в settings, часть env-переменных не описана в шаблонах (12-C1..C4) |
| §2 «владелец заполняет .env и запускает `docker compose up`» | **частично** | Без TLS, бэкапов и с неработающим `deploy.sh` этого недостаточно для прода |
| §4 этап 7: деплой-сценарий под любой VPS | **противоречит** | Деплой привязан к AWS EC2 и к `/opt/autoforyou/redeploy.sh`, которого нет в репо (`ci-cd.yml:179,192`). `deploy.sh` сломан (12-Q1) |
| §4 этап 7: домен + HTTPS, бэкапы, мониторинг ошибок | **не хватает** | 12-S2, 12-S6, 12-S13 |
| §4 этап 0: стабильная тестовая среда | **противоречит** | Два venv, в `venv/` тесты падают (12-Q8) |
| §5 тесты зелёные, build | совпадает | Обязательные проверки CI зелёные, красный только deploy |
| `docs/LAUNCH_CHECKLIST.md` | **не хватает** | Файла нет (`ls docs/` показывает 00_AUDIT, BACKEND_TESTS, BRIEF, DEMO, PRODUCTION_ROADMAP, TEST_CASES, audit) |

## Безопасность и личные данные

| ID | Уровень | Проблема | Файл:строка | Как исправить |
|---|---|---|---|---|
| 12-S1 | **критично** | В публичном репозитории лежит реальный токен Telegram-бота `<ID бота>:<токен скрыт>***` в строке разрешения Bash. Файл отслеживается вопреки `.gitignore:44`, в истории с коммитов `8904842` и `a47169c` | `.claude/settings.local.json:58` | Отозвать токен в @BotFather и выпустить новый, выполнить `git rm --cached .claude/settings.local.json`. По желанию вычистить историю (filter-repo) |
| 12-S2 | **критично** | HTTPS нет: nginx слушает только `:80`, TLS закомментирован. При `DEBUG=false` в Django по умолчанию `SECURE_SSL_REDIRECT=true`, и `/api` с `/admin` редиректят на несуществующий https. За внешним TLS-балансировщиком будет бесконечный редирект, потому что nginx перезаписывает `X-Forwarded-Proto $scheme` на `http` | `nginx/nginx.conf:10,35,54-61`; `core/settings.py:423,429` | Сервер на 443 с сертификатами Let's Encrypt (certbot или контейнер acme), редирект 80→443, сертификаты в volume |
| 12-S3 | важно | На HTML-страницах Next.js нет HSTS, CSP, X-Frame-Options, nosniff, Referrer-Policy и Permissions-Policy: nginx ничего не добавляет, в `next.config.ts` нет `headers()`. CSP нет нигде | `nginx/nginx.conf:9-62`; `frontend/next.config.ts:12-36`; `core/settings.py:424-431` | `add_header ... always` в server-блоке nginx, CSP через nginx или middleware Next |
| 12-S4 | важно | Строка `COPY . .` запекает в backend-образ `.claude/` (с токеном), `pgdata/` (51 МБ данных Postgres), `dump.sql` (дамп БД), `test-results/`, `.pytest_cache/`, если сборка идёт в рабочей копии разработчика: `.dockerignore` их не исключает | `Dockerfile.backend:25`; `.dockerignore:1-20` | Добавить в `.dockerignore` `.claude/ pgdata/ dump.sql *.sql test-results/ .pytest_cache/ .ruff_cache/ htmlcov/ .env.*` |
| 12-S5 | важно | Все контейнеры работают от root: нет `USER` ни в одном Dockerfile | `Dockerfile.backend:13-33`; `Dockerfile.frontend:24-34` | Создать непривилегированного пользователя (`useradd app` / `USER node`), выдать права на `/app/media` и `/app/staticfiles` |
| 12-S6 | важно | Бэкапов Postgres нет: ни `pg_dump`-скрипта, ни сервиса или cron в compose, ни ротации, ни проверки восстановления. DEPLOY_NOTES описывает только копирование `db.sqlite3` и `dumpdata` | `docker-compose.yml:4-23`; `DEPLOY_NOTES.md:7-20,146-149` | Сервис или cron с `pg_dump -Fc`, ротация (7 дневных и 4 недельных), копия вне сервера, скрипт `restore` и ежемесячный тестовый restore |
| 12-S7 | желательно | `/media/` раздаётся всем без проверки доступа и без `X-Content-Type-Options: nosniff`, включая `tracking_photos/` (фото отслеживания доставки клиента) | `nginx/nginx.conf:24-27`; `shipments/models.py:87` | `add_header X-Content-Type-Options nosniff`. Приватные файлы отдавать через X-Accel-Redirect после проверки прав |
| 12-S8 | важно | Логи с ПДн и без ротации. Access-лог gunicorn и лог nginx по умолчанию пишут полный URL с query-строкой и IP, а в query могут оказаться email, телефон или токены. В Django нет `LOGGING`, в compose нет `logging:` (json-file растёт без ограничений) | `docker/entrypoint.sh:32`; `nginx/nginx.conf` (нет `log_format`); `docker-compose.yml` (нет `logging`) | Свой `log_format` без `$args`, `logging: {driver: json-file, options: {max-size: 10m, max-file: "5"}}`, `LOGGING` с фильтром ПДн |
| 12-S9 | важно | Throttling обходится подменой IP. nginx дописывает `X-Forwarded-For` (`$proxy_add_x_forwarded_for`), а в DRF не задан `NUM_PROXIES`, поэтому идентификатором служит вся клиентская строка XFF. Её можно менять в каждом запросе | `nginx/nginx.conf:34,45`; `core/settings.py:219-240` (нет `NUM_PROXIES`) | `'NUM_PROXIES': 1` в `REST_FRAMEWORK`, в nginx `proxy_set_header X-Forwarded-For $remote_addr` (или real_ip за балансировщиком) |
| 12-S10 | желательно | В nginx нет `limit_req` на `/api/v1/auth/` и `/admin/login`, `server_tokens` не выключен | `nginx/nginx.conf:30-39` | `limit_req_zone` и `limit_req` для auth, `server_tokens off` |
| 12-S11 | желательно | В CI нет `permissions:` (у GITHUB_TOKEN права по умолчанию), actions закреплены тегами, а не SHA, `pip install ruff` без версии, нет `pip-audit`/`npm audit`, нет Dependabot | `.github/workflows/ci-cd.yml:1-9,39,49,185` | `permissions: contents: read`, закрепить ruff, добавить джобу аудита зависимостей и `dependabot.yml` |
| 12-S12 | желательно | Redis без пароля. Наружу он не открыт, но любой контейнер в сети имеет полный доступ | `docker-compose.yml:26-28` | `--requirepass ${REDIS_PASSWORD}` и пароль в `REDIS_URL` |
| 12-S13 | важно | Мониторинга ошибок нет: нет sentry-sdk или аналога, алертов тоже нет. Бриф, этап 7 | `requirements.txt:1-25`; `core/settings.py` (нет `LOGGING`/`SENTRY_DSN`) | `sentry-sdk` (или GlitchTip, бесплатно) через `SENTRY_DSN` из `.env`, `send_default_pii=False` |

## Готовность к конфигурации

| ID | Что захардкожено / заглушка / TODO / placeholder / demo-данные | Файл:строка | Куда вынести |
|---|---|---|---|
| 12-C1 | Переменные, которые код читает, но которых нет ни в одном `.env*.example`: `ANTISPAM_MODE`, `AUCTION_DEFAULT_MEMBER_TYPE`, `LOCAL_LISTING_EXPIRY_DAYS`, `LOCAL_LISTING_MAX_PHOTOS`, `LOCAL_LISTING_PHOTO_MAX_SIZE_MB`, `SELLER_BADGE_THRESHOLD`, `THROTTLE_ANON_RATE`, `THROTTLE_USER_RATE`, `THROTTLE_CONTACT_RATE`, `THROTTLE_EXPENSIVE_RATE`, `THROTTLE_MESSAGES_RATE`. Кроме того, `S3_REGION` нет в `.env.docker.example` | `core/settings.py:312` и др.; `.env.example`; `.env.docker.example` | Описать в обоих шаблонах и в `docs/LAUNCH_CHECKLIST.md` |
| 12-C2 | `NEXT_PUBLIC_DEMO_MODE` используется во фронтенде (`components/ui/DemoBanner.tsx`), но его нет в шаблонах и он не передаётся как build-arg, поэтому в Docker демо-баннер включить нельзя | `Dockerfile.frontend:15-19`; `docker-compose.yml:59-62` | `ARG`/`ENV` в Dockerfile.frontend, `args:` в compose, строка в `.env*.example` |
| 12-C3 | Домен `server_name localhost` и пути к сертификатам захардкожены в nginx | `nginx/nginx.conf:11,57-58` | Шаблон `/etc/nginx/templates/*.conf.template` (envsubst) с `DOMAIN` из `.env` |
| 12-C4 | Деплой привязан к AWS EC2 и внешнему скрипту `/opt/autoforyou/redeploy.sh`, которого нет в репо | `.github/workflows/ci-cd.yml:179,192` | Скрипт redeploy положить в репо, джобу включать через `vars.DEPLOY_ENABLED` / `workflow_dispatch` |
| 12-C5 | Дефолтный домен `https://autoforyou.ua` для `SITE_URL` и `noreply@autoforyou.ua` для `DEFAULT_FROM_EMAIL` | `core/settings.py:344,414`; `.env.example:62` | Оставить только в `.env`, дефолт пустой или `localhost` |
| 12-C6 | `MEDIA_URL` для S3 собирается по шаблону `*.s3.<region>.amazonaws.com` даже при заданном `S3_ENDPOINT_URL` (R2). Ссылки на R2 будут неверными (в работе не проверено) | `core/settings.py:187-191` | Env `MEDIA_URL`/`AWS_S3_CUSTOM_DOMAIN` или вычисление из endpoint |
| 12-C7 | Имя контейнера `autoforyou-backend-1` захардкожено, а в `.env.docker.example` нет `COMPOSE_PROJECT_NAME` | `deploy.sh:72`; `.env.docker.example` | `docker compose ps -q backend` плюс `COMPOSE_PROJECT_NAME` в шаблоне |
| 12-C8 | Dev-значения `POSTGRES_PASSWORD=autoforyou_dev_pass` и SECRET_KEY с `REPLACE` в Docker-шаблоне. Это допустимо, `deploy.sh:23-38` их отсекает | `.env.docker.example:10-11,18` | Оставить как есть |
| 12-C9 | Нет `frontend/.env.example`. Переменные фронтенда (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `INTERNAL_API_URL`, `NEXT_PUBLIC_DEMO_MODE`, `E2E_BASE_URL`) для запуска без Docker нигде не описаны | `frontend/` | Создать `frontend/.env.example` |
| 12-C10 | Параметры gunicorn `--timeout 120` и `client_max_body_size 20M` не синхронизированы с `LOCAL_LISTING_PHOTO_MAX_SIZE_MB` | `docker/entrypoint.sh:31`; `nginx/nginx.conf:13` | `GUNICORN_TIMEOUT` в env, лимит nginx через шаблон |

## Качество кода

| ID | Уровень | Проблема | Файл:строка |
|---|---|---|---|
| 12-Q1 | важно | `deploy.sh` проверяет переменные shell-окружения, но `.env` не загружает (нет `set -a; . ./.env`), поэтому скрипт падает с «SECRET_KEY is not set». Кроме того: нет `git pull`, нет бэкапа перед деплоем, нет отката | `deploy.sh:8-19,63-75` |
| 12-Q2 | важно | Джоба deploy красная на каждом push в main: 5 из 5 последних запусков `failure`, в run 36000769006 `dial tcp ***: i/o timeout`. Main постоянно выглядит красным, реальные падения не видно | `.github/workflows/ci-cd.yml:178-192` |
| 12-Q3 | желательно | Корневой `Dockerfile` мёртвый и сломанный (в корне нет `package.json` и `server.js`). `docker build .` собирает не то, что ожидается | `Dockerfile:1-7` |
| 12-Q4 | важно | Healthchecks неполные: у redis, frontend, nginx, celery_worker, celery_beat и bot их нет. У backend проверяется только TCP-порт, без HTTP и без БД. nginx ждёт frontend только по `service_started`. Эндпоинта `/healthz` нет | `docker-compose.yml:26-28,46-51,55-67,85-140` |
| 12-Q5 | желательно | celery_worker и celery_beat не ждут миграций (зависят от db, а не от backend), так что beat с DatabaseScheduler может стартовать раньше таблиц. `collectstatic --clear` и `migrate` выполняются в entrypoint при каждом старте, что создаёт гонку при масштабировании | `docker-compose.yml:94-98,119-123`; `docker/entrypoint.sh:5,25` |
| 12-Q6 | желательно | Gunicorn: нет `--max-requests`/`--max-requests-jitter`, `--graceful-timeout` и `--worker-tmp-dir /dev/shm`. Access-лог пишется без собственного формата | `docker/entrypoint.sh:28-33` |
| 12-Q7 | желательно | В runtime-образ frontend копируются все `node_modules` вместе с dev-зависимостями. PID 1 — это `npm start` (плохо пробрасывает SIGTERM). `output: 'standalone'` не используется | `Dockerfile.frontend:28-34`; `frontend/next.config.ts:12` |
| 12-Q8 | важно | В корне два виртуальных окружения. `venv/` создан из `.venv` (`venv/pyvenv.cfg`), в нём есть django и aiogram, но нет celery, django_redis, gunicorn и kombu. `core/__init__.py:1` импортирует celery, поэтому `manage.py test` через `venv/` падает. Какой интерпретатор выбран в PyCharm, не проверено (`.idea/misc.xml`: «Python 3.12 (AUTOforYOU)») | `venv/`, `.venv/`, `core/__init__.py:1` |
| 12-Q9 | желательно | Расхождение версий: Postgres 16 в CI против 18 в compose. Плавающие теги `nginx:alpine` и `redis:7-alpine`. Транзитивные Python-зависимости (botocore, kombu, redis и др.) не закреплены, lock-файла или хешей нет | `ci-cd.yml:16`; `docker-compose.yml:5,27,128`; `requirements.txt` |
| 12-Q10 | желательно | Redis без volume и `maxmemory`, кэш и брокер Celery делят одну БД `/0` | `docker-compose.yml:26-28`; `.env.example:29` |
| 12-Q11 | важно | `DEPLOY_NOTES.md` устарел и расходится с реальным деплоем. Описаны SQLite, «откат на SQLite», бэкап через `dumpdata`, «119 тестов» и запуск бота в терминале. Про `docker compose`, `deploy.sh`, HTTPS и Celery ничего нет | `DEPLOY_NOTES.md:7-20,38-53,144-171,224-233` |
| 12-Q12 | желательно | nginx: `Connection 'upgrade'` задаётся для всех запросов к frontend (ломает keepalive, комментарий про HMR). `gzip_static on` без предсжатых файлов, обычного `gzip` для text/js/css нет | `nginx/nginx.conf:20,48-51` |
| 12-Q14 | важно | На Windows backend-контейнер уходит в цикл рестартов с ошибкой `exec /app/docker/entrypoint.sh: no such file or directory` (проверено основным агентом через `docker compose up -d --build`). Причина: `core.autocrlf=true`, `.gitattributes` в репозитории нет, `git ls-files --eol docker/entrypoint.sh` показывает `i/lf w/crlf`. В рабочей копии `docker/entrypoint.sh` и `deploy.sh` с CRLF, `bot_entrypoint.sh` с LF. Из-за этого свежую сборку стека локально с Windows не поднять, и e2e против неё не запускались | `docker/entrypoint.sh`; `deploy.sh`; `Dockerfile.backend:31` (нет `.gitattributes`) |
| 12-Q13 | желательно | `.gitignore` не мешает отслеживать ранее добавленные файлы: `.claude/settings.local.json` остаётся в индексе (см. 12-S1) | `.gitignore:43-44` |

## Тесты

- Автотестов для инфраструктуры нет. Косвенно её проверяет CI: джоба e2e поднимает весь стек `docker compose up -d --build` с `DEBUG=false` и прогоняет Playwright (`ci-cd.yml:106-175`), джоба backend проверяет миграции и актуальность openapi (`ci-cd.yml:53-77`). Эти три проверки обязательны в branch protection.
- Не покрыто:
  - поведение настроек безопасности в проде (HSTS, SSL-redirect, `SECURE_PROXY_SSL_HEADER`): `_TESTING` отключает их в тестах (`core/settings.py:418-419`);
  - `deploy.sh`;
  - бэкап и восстановление;
  - определение IP за прокси;
  - заголовки nginx.
- Нужны Django-тесты:
  - `override_settings(DEBUG=False, ...)`: наличие HSTS, `nosniff` и `X-Frame-Options` в ответе API;
  - при `X-Forwarded-Proto: https` нет редиректа;
  - throttling не обходится подменой `X-Forwarded-For` (после `NUM_PROXIES`);
  - `/healthz` отвечает 200 и проверяет БД.
- Нужны CI и shell-проверки:
  - `shellcheck deploy.sh docker/*.sh`;
  - `docker compose config --quiet`;
  - `hadolint` для Dockerfile;
  - job «backup → restore в чистый Postgres → `manage.py check`»;
  - `gitleaks`/`trufflehog` на секреты (поймал бы 12-S1);
  - проверка, что в `*.sh` нет CRLF (12-Q14); исправление: `.gitattributes` с `*.sh text eol=lf` или `sed -i 's/\r$//'` в Dockerfile.
- Нужны Playwright-сценарии (e2e-стек):
  - главная и страница объявления отдают заголовки `Strict-Transport-Security` (на TLS-стенде), `Content-Security-Policy`, `X-Content-Type-Options`;
  - `http://` редиректит на `https://`;
  - загрузка фото больше 20 МБ даёт понятную ошибку, а не 413 без текста;
  - `/media/` недоступен для приватных файлов.

## Итог (≤15 строк)

Готовность пакета около 55%. Compose-стек поднимается целиком, включая Celery worker и beat и бота. БД и Redis наружу не открыты, CI из трёх обязательных джоб зелёный, e2e гоняется на полном стеке с `DEBUG=false`. Top-level зависимости закреплены, `.env`, дампы и `pgdata` в git не попадали.
Критично:
- **12-S1**: в публичном репо лежит реальный токен Telegram-бота (`.claude/settings.local.json:58`). Нужно срочно отозвать его в BotFather;
- **12-S2**: HTTPS нет, nginx только на `:80`, а Django при `DEBUG=false` редиректит на https, так что прод-сценарий не работает.

Важно:
- 12-S3: нет CSP и заголовков на страницах Next;
- 12-S4: `.dockerignore` пропускает в образ `.claude`, `pgdata`, `dump.sql`;
- 12-S5: контейнеры работают от root;
- 12-S6: бэкапов Postgres нет вовсе;
- 12-S8: логи с query-строкой и без ротации;
- 12-S9: throttling обходится подменой XFF;
- 12-S13: нет Sentry;
- 12-Q1: `deploy.sh` не читает `.env`;
- 12-Q2: deploy-джоба красная на каждом push в main;
- 12-Q4: неполные healthchecks;
- 12-Q8: в `venv/` нет celery, тесты там падают;
- 12-Q14: CRLF в `entrypoint.sh` и нет `.gitattributes`, поэтому backend на Windows уходит в цикл рестартов;
- 12-Q11: DEPLOY_NOTES устарел (SQLite, dumpdata);
- 12-C1, 12-C2: часть env-переменных не описана в шаблонах, `NEXT_PUBLIC_DEMO_MODE` не пробрасывается в Docker.

Этап 7 брифа (любой VPS, HTTPS, бэкапы, мониторинг, LAUNCH_CHECKLIST.md) по инфраструктуре не выполнен.
