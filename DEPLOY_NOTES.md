# Инструкция по запуску AUTOforYOU в продакшене

Написано простым языком. Продакшен — это Docker-стек на одном VPS (Postgres, Redis, Django, Next.js, Celery, nginx, бэкапы),
который поднимает один скрипт `./deploy.sh`. Список того, что нужно заполнить владельцу, — `docs/LAUNCH_CHECKLIST.md`.

---

## 1. Требования к серверу (VPS)

- Linux: Ubuntu 22.04 / 24.04 или Debian 12. Минимум 2 vCPU, 4 ГБ RAM, 40 ГБ диска.
- Основной вариант по бизнес-плану — Hetzner **CX23** (x86, `amd64`). Запасной — **CAX11** (ARM, `arm64`), если CX23 недоступен.
  Деплой работает на обеих архитектурах: `deploy.sh` сам определяет платформу по `uname -m` (x86_64 → `linux/amd64`,
  aarch64 → `linux/arm64`). Другие архитектуры скрипт отвергает с ошибкой.
- Docker Engine и Compose v2 (команда `docker compose`), `git`.
- SSH-доступ по ключу. Открытые порты: 22 (SSH), 80 и 443.

## 2. DNS

У регистратора (или в Cloudflare) создайте A-запись домена на IP сервера (AAAA — если есть IPv6; `www` — по желанию, тогда `DOMAIN_WWW=true`).
Проверка: `nslookup ваш-домен` возвращает IP сервера. Без DNS Let's Encrypt сертификат не выдаст.

## 3. Подготовка чистого сервера

Автоматически (от root, один раз; повторный запуск безопасен):
```
sudo ./scripts/server-setup.sh
```
Скрипт печатает каждое действие. Если не хотите запускать скрипт, выполните то же руками:

1. **Docker из официального репозитория** — по инструкции https://docs.docker.com/engine/install/ubuntu/ (или `/debian/`):
   пакеты `docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin`. Проверка: `docker compose version`.
2. **Пользователь для деплоя** (не root):
   `adduser deploy` и `usermod -aG docker deploy`. Положите свой публичный ключ в `~deploy/.ssh/authorized_keys`.
   Группа `docker` даёт права, близкие к root: добавляйте в неё только доверенных людей.
3. **Файрвол**: `ufw allow <порт SSH>/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable`. Порт SSH узнайте командой `sshd -T | grep ^port` (если он не 22, не включайте ufw, пока не разрешили его: иначе потеряете доступ). Скрипт делает это сам.
   Docker открывает опубликованные порты в обход ufw; Compose публикует наружу только nginx (80/443), БД слушает `127.0.0.1`.
4. **Автообновления безопасности**: `apt install unattended-upgrades`, файл `/etc/apt/apt.conf.d/20auto-upgrades`:
   `APT::Periodic::Update-Package-Lists "1";` и `APT::Periodic::Unattended-Upgrade "1";`.
5. **Swap** (на 4 ГБ RAM и 8 контейнеров — страховка от OOM). Если `swapon --show` пуст:
   `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`,
   затем строка `/swapfile none swap sw 0 0` в `/etc/fstab`. Размер в скрипте задаёт `SWAP_SIZE_GB` (по умолчанию 2). ПРОВЕРИТЬ по `docker stats` под нагрузкой.
6. **`vm.swappiness`**: в `/etc/sysctl.d/99-autoforyou.conf` строка `vm.swappiness=10`, применить `sysctl --system`. ПРОВЕРИТЬ замером.

## 4. Первый запуск

Под пользователем `deploy`:
```
git clone <адрес репозитория> autoforyou && cd autoforyou
cp .env.example .env   # прод-шаблон; .env.docker.example — только для локального стека
```
Заполните `.env` по `docs/LAUNCH_CHECKLIST.md` (раздел 2). Минимум для старта:
`SECRET_KEY` (случайный, от 50 символов), `POSTGRES_PASSWORD` и тот же пароль в `DATABASE_URL`, `REDIS_PASSWORD` и в `REDIS_URL`,
`DEBUG=false`, `DOMAIN`, `ALLOWED_HOSTS` (с вашим доменом), `SITE_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SITE_URL`, `TLS_MODE`.
Ключ генерируется так:
```
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```
Первый деплой — только с выключенными замороженными модулями и платежами: `C2C_PUBLIC_POSTING_ENABLED=false`, `PAYMENTS_ENABLED=false`;
`C2C_ENABLED` — по решению владельца (`false`, пока нет «засева» объявлений). Режим бота: `TELEGRAM_UPDATES_MODE` (webhook или polling).

Запуск:
```
./deploy.sh --build
```
Скрипт проверяет `.env`, собирает образы, поднимает стек, дожидается healthy-сервисов и проверяет `/healthz` и `/`.
Первый бэкап пропускается сам (базы ещё нет). Затем создайте администратора:
```
docker compose exec backend python manage.py createsuperuser
```

### HTTPS (TLS_MODE=letsencrypt)
После первого `./deploy.sh --build`, когда DNS уже указывает на сервер:
```
./scripts/init-letsencrypt.sh
```
(нужны `TLS_MODE=letsencrypt` и `LETSENCRYPT_EMAIL` в `.env`; для пробы — `LETSENCRYPT_STAGING=true`). Скрипт получает сертификат и включает автопродление.
До этого nginx работает с временным сертификатом — браузер покажет предупреждение, это нормально. Другие режимы (`off`, `selfsigned`, `external`, Cloudflare) — `docs/LAUNCH_CHECKLIST.md`, раздел 2.3.

## 5. Обычный деплой

```
./deploy.sh --pull --build
```
Порядок: проверки → `git pull --ff-only` → бэкап БД (`scripts/backup.sh --now`, путь к дампу печатается) → сборка образов с тегом
`IMAGE_TAG=<git short sha>` → `docker compose up -d --wait` → smoke (`/healthz` и `/` через локальный nginx) → итог.

| Флаг | Что делает |
|------|-----------|
| `--pull` | `git pull --ff-only` перед деплоем |
| `--build` | пересобрать образы (после `--pull` нужен почти всегда) |
| `--skip-backup` | не делать бэкап (только осознанно) |
| `--rollback` | вернуться на предыдущие образы |
| `--smoke-e2e` | после деплоя прогнать Playwright `@smoke` (нужны node и `npm ci` в `frontend/`) |

`.env` берётся из каталога скрипта; другой файл — `DEPLOY_ENV_FILE=путь ./deploy.sh`. Файлы и имя проекта Compose читаются из стандартных
`COMPOSE_FILE` и `COMPOSE_PROJECT_NAME`. Если в `.env` включён `CLOUDFLARE_PROXY=true`, скрипт сначала обновляет диапазоны IP Cloudflare.
Замороженные модули (`LOTS_ENABLED`, `B2B_ENABLED`, `DEALERS_ENABLED`, `SHIPMENTS_ENABLED`, `VIN_REPORTS_ENABLED`) при `DEBUG=false`
вызывают предупреждение, но не остановку. Права на тома `media`, `private_media`, `static` под непривилегированного пользователя выставляет
сервис `volume_init` при каждом запуске — вручную `chown` не нужен.

## 6. Откат

Если запуск или smoke не прошли, `deploy.sh` сам поднимет образы предыдущего деплоя (тег лежит в `.deploy/previous_tag`).
Вручную: `./deploy.sh --rollback` (повторный запуск вернёт обратно).

> ⚠ Откат образов **не откатывает данные и миграции БД.** Если новая миграция уже применена, а старый код с ней не работает, нужно
> восстановить базу из дампа, который скрипт сделал перед деплоем: `./scripts/restore.sh <дамп>` (раздел 7).

**Правило обратно совместимых миграций.** Каждая миграция должна работать и со старым, и с новым кодом. Поэтому поле или таблицу сначала
перестают использовать в коде (релиз 1: добавление нового, код пишет в оба места), а удаляют отдельным релизом, когда новый код уже
в продакшене. Тогда `--rollback` безопасен без восстановления БД. Переименование колонки — это «добавить новую + перенести + удалить старую» в трёх релизах.

## 7. Бэкапы и восстановление (задача 7.4)

Бэкап Postgres делает сервис `backup` каждую ночь; перед изменениями `deploy.sh` делает ещё один. Вручную:
```
./scripts/backup.sh --now
```
Файл `backups/autoforyou_ДАТА_ЧЧММ.dump` (+ `.sha256`, архив медиа). Настройка, копия вне сервера, шифрование и проверка восстановления
(`./scripts/backup-verify.sh`) описаны в `docs/LAUNCH_CHECKLIST.md`, разделы 2.10 и 7.7.

> ⚠ Папка `backups/` никогда не попадёт в git и в образы — это правильно, там личные данные.

Восстановление (останавливает сервисы, делает страховочный дамп, просит подтверждение):
```
./scripts/restore.sh backups/autoforyou_ДАТА_ЧЧММ.dump [--media backups/autoforyou-media_ДАТА_ЧЧММ.tar.gz]
```
Каталог `BACKUP_DIR` может создать любой пользователь: контейнеру `backup` для записи в чужой каталог дана capability `DAC_OVERRIDE`, больше
ничего (корень read-only, `cap_drop: ALL`). Файлы внутри создаются от root с правами 600; чтобы прочитать их с хоста, используйте `sudo`.
Перед восстановлением появляется `pre-restore_*.dump` (состояние базы до отката): единственный путь «откатить откат». Удаляйте его вручную,
когда убедились, что восстановленный сайт работает (обычно через несколько дней). Он содержит ПДн — не копируйте и не оставляйте дольше нужного.
Для файла из облака (`.dump.gpg`) нужен `BACKUP_ENCRYPTION_PASSPHRASE` в `.env`; храните его вне сервера.

## 8. Логи и состояние

```
docker compose ps                       # статусы и health
docker compose logs --tail 100 backend  # последние строки (frontend, nginx, celery_worker, bot, ...)
docker compose logs -f nginx            # следить в реальном времени
docker stats                            # память и CPU контейнеров
```
Размер логов ограничен (`LOG_MAX_SIZE`, `LOG_MAX_FILES`). Мониторинг `/healthz` снаружи — `docs/LAUNCH_CHECKLIST.md`, раздел 1.

## 9. Обновление

Обычное обновление кода — раздел 5. Обновление версий зависимостей приходит PR-ами от Dependabot (раз в неделю); сливать после зелёного CI.
Обновление ОС: пакеты безопасности ставятся автоматически (раздел 3); раз в месяц `apt update && apt upgrade` и перезагрузка в тихое время.
После `apt upgrade` с обновлением Docker: `docker compose ps` — все сервисы должны подняться сами (`restart: unless-stopped`).

## 10. Автодеплой из GitHub (по желанию)

Если хотите, чтобы сайт обновлялся после каждого слияния в `main`. Без этого деплой вручную: `./deploy.sh --pull --build`.

1. На сервере под `deploy` положите **отдельный** SSH-ключ только для GitHub (публичная часть — в `authorized_keys`).
2. GitHub → Settings → **Environments** → New environment → `production`. В нём:
   - **Deployment branches** = только `main` (Selected branches). Required reviewers — по желанию (деплой ждёт вашего «Approve»).
   - **Environment secrets** (а не секреты репозитория: так их увидит только джоба деплоя на `main`): `SSH_HOST`, `SSH_USER`,
     `SSH_KEY` (приватный ключ), `SSH_PORT` (если не 22), `SSH_HOST_FINGERPRINT`.
   - Отпечаток берите **на самом сервере** (консоль хостера, не по сети): `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`.
     В секрет кладите только строку `SHA256:…`. `ssh-keyscan` для этого не используйте: он берёт ключ из сети, которой мы как раз не доверяем.
3. Repository (или environment) **Variables**: `DEPLOY_ENABLED=true`, `DEPLOY_PATH` (каталог проекта на сервере), `SITE_URL` (необязательно: после деплоя CI прогонит Playwright `@smoke`).
4. Джоба «Deploy» запускается после зелёных secrets-scan, infra-lint, backend, frontend и e2e на push в `main` или вручную с ветки `main`
   (Actions → CI/CD → Run workflow). Без `DEPLOY_ENABLED` она пропускается (`skipped`), `main` остаётся зелёным.
   Если Secret или Variable не задана, джоба падает с перечнем недостающих.
5. CI передаёт `EXPECTED_SHA` (коммит, прошедший проверки): после `git pull` `deploy.sh` откажется деплоить, если HEAD на сервере другой
   (например, в `main` успели слить более новый коммит). Тогда просто запустите workflow заново.

### Ограничение ключа деплоя (рекомендуется)
Украденный ключ деплоя не должен давать оболочку на сервере. В `~deploy/.ssh/authorized_keys` ограничьте ключ одной командой:
```
restrict,command="cd /путь/к/проекту && ./deploy.sh --pull --build" ssh-ed25519 AAAA… github-deploy
```
Честно о компромиссе: при `command=` сервер **игнорирует** команду, которую шлёт CI, поэтому `EXPECTED_SHA` до `deploy.sh` не доходит
и проверка «тот ли коммит» не выполняется — деплоится то, что сейчас в `main` (ветка защищена, поэтому это приемлемо).
Выбирайте: либо `command=` (ключ ничего другого не умеет, нет проверки SHA), либо ключ без `command=` (CI передаёт `EXPECTED_SHA`, но ключ
даёт оболочку пользователя `deploy`). Если ключ без ограничения, хотя бы держите его только в environment `production` с ветвью `main`.

## 11. Частые ошибки

| Симптом | Причина и решение |
|---------|-------------------|
| `.env не найден` | Не создан `.env`: `cp .env.example .env` (прод-шаблон) и заполните |
| `SECRET_KEY looks like a placeholder` | В `.env` остался текст из шаблона: сгенерируйте ключ (раздел 4) |
| `ALLOWED_HOSTS … не содержит DOMAIN` | Впишите домен в `ALLOWED_HOSTS`, иначе Django отвечает 400 на всё, включая `/healthz` |
| `SITE_URL … не начинается с https://` | При `TLS_MODE` не `off` адрес сайта должен быть https |
| `DEBUG is enabled` | В продакшене `DEBUG=false` |
| `нет доступа к Docker` | Пользователь не в группе `docker`: `usermod -aG docker deploy`, перелогиниться |
| `docker compose config не прошёл` | Пустой обязательный пароль или `NEXT_PUBLIC_*` в `.env`; текст ошибки Compose называет переменную |
| smoke не прошёл, пошёл откат | Смотрите `docker compose logs --tail 100 backend nginx`; частые причины — миграция упала, неверный домен в `ALLOWED_HOSTS` |
| `--rollback`: нет `.deploy/previous_tag` | До этого был один деплой: откатываться некуда |
| Let's Encrypt не выдаёт сертификат | DNS ещё не указывает на сервер или закрыт порт 80; пробуйте `LETSENCRYPT_STAGING=true` |
| Сайт открывается по http, но не по https | Не выполнен `./scripts/init-letsencrypt.sh` или `TLS_MODE` не `letsencrypt` |
| Не хватает места на диске | `docker system df`; старые образы: `docker image prune` (образы текущего и предыдущего деплоя нужны для отката — не удаляйте их вручную) |
