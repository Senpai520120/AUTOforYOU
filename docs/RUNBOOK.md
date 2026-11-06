# RUNBOOK: упало — что делать

Для одного человека на сервере, без опыта администрирования. Все команды выполняются из папки проекта на VPS.
Команды сверены со скриптами и `docker-compose.yml`, но на настоящем сервере ещё не прогонялись: при первых учениях (конец файла) исправить здесь то, что отличается.

## Перед любым действием

```bash
docker compose --profile letsencrypt ps        # кто запущен (без профиля certbot не виден)
docker compose logs --tail 100 <сервис>        # db, redis, backend, frontend, nginx, bot, celery_worker, celery_beat, backup, certbot
df -h                                          # место на диске
./scripts/check-memory.sh                      # память контейнеров
```

**Никогда не выполнять `docker compose down -v`: `-v` удаляет том с базой данных.**

Откат кода: `./deploy.sh --rollback` поднимает образы прошлого деплоя. Данные БД он не откатывает.

## 1. Сайт не открывается

- **Проверка:** `curl -I https://ваш-домен/healthz`. Ошибка Cloudflare 52x означает, что Cloudflare работает, а сервер не отвечает.
- **Действие:** `docker compose up -d nginx`. Если нет связи по SSH — перезагрузка из консоли Hetzner.
- **Откат:** если сломалось после деплоя — `./deploy.sh --rollback`.

## 2. Backend отвечает 502

- **Проверка:** `docker compose logs --tail 100 backend nginx`. Подозрение на нехватку памяти — `./scripts/check-memory.sh`.
- **Действие:** `docker compose restart backend`.
- **Откат:** `./deploy.sh --rollback`. Если новая миграция уже применена — `./scripts/restore.sh backups/<дамп до деплоя>.dump`.

## 3. База данных

- **Проверка:** `/healthz` отвечает 503; `docker compose exec db pg_isready`.
- **Действие:** `docker compose restart db`.
- **Откат:** `./scripts/restore.sh backups/<файл>.dump` (сначала сам делает страховочный дамп). Копия вне сервера: `.dump.gpg` из R2, порядок — `DEPLOY_NOTES.md`.

## 4. Redis или Celery: заявки не приходят брокеру, сторож прислал оповещение

`/healthz` проверяет только БД и Redis, поэтому при мёртвом Celery сайт выглядит здоровым. Об этом сообщает сервис-сторож (`CELERY_HEARTBEAT_URL`).

- **Проверка:**
  - `docker compose exec celery_worker celery -A core inspect ping`
  - `docker compose exec redis redis-cli -a "$REDIS_PASSWORD" LLEN celery` (очередь; пароль — из `.env`)
  - админка → «Невдалі завдання»
- **Действие:** `docker compose restart celery_worker celery_beat`.
- **Что с заявками:** они лежат в БД и досылаются автоматически (`resend-undelivered-leads`), вручную — «повторно» в админке.

## 5. Бот молчит

- **Проверка:** `docker compose ps bot`. При режиме webhook контейнер в состоянии Exit 0 — это норма.
- **Действие:** `docker compose restart bot`; при webhook — `docker compose exec backend python manage.py set_webhook`. Токен отозван — новый токен в `.env`, затем `docker compose up -d bot backend celery_worker`.
- **Что с заявками:** брокеру их шлёт worker, при сбое Telegram — резервное письмо (2.12).

## 6. Кончился диск

- **Проверка:** `df -h`, `docker system df`, `du -sh backups`.
- **Действие:** `docker image prune` (теги текущего и прошлого деплоя не удалять: они нужны для отката), `journalctl --vacuum-size=200M`.
- **Затем:** `docker compose restart db backend`.

## 7. Сертификат HTTPS

- **Проверка:** `echo | openssl s_client -connect ваш-домен:443 2>/dev/null | openssl x509 -noout -dates`; `docker compose --profile letsencrypt logs --tail 100 certbot`.
- **Действие:** порт 80 должен быть открыт, затем:
  - `docker compose --profile letsencrypt run --rm --entrypoint certbot certbot renew --webroot -w /var/www/certbot`
  - `docker compose exec nginx nginx -s reload`
- **Если не помогло:** `./scripts/init-letsencrypt.sh` (сначала с `LETSENCRYPT_STAGING=true`).

## 8. Сторож сообщил, что не было бэкапа

- **Проверка:** `docker compose logs --tail 100 backup`, `ls -l backups/.last_success`.
- **Действие:** `./scripts/backup.sh --now`; проверка копии — `./scripts/backup-verify.sh`.

## Если вас нет

Все доступы — в менеджере паролей: VPS, Cloudflare, регистратор домена, BotFather, R2, GitHub, пароль шифрования бэкапов. Экстренный доступ — у доверенного человека. **Без пароля шифрования копии в R2 не восстановить.**

## Учения (после деплоя, затем раз в квартал)

1. `docker compose stop celery_worker` → пришло оповещение сторожа → `docker compose start celery_worker`.
2. `docker compose stop backend` → пришло оповещение uptime-монитора → `docker compose start backend`.
3. `./scripts/backup-verify.sh --from-remote` проходит на настоящем R2.
4. Команды этого файла совпали с реальностью; расхождения исправлены здесь.
