# Деплой на AWS EC2 — что сделать владельцу (2026-11-16)

> **Исправление 2026-11-16.** Сервера для AUTOforYOU ещё нет. `3.72.4.226` был тестовым стендом другого проекта
> (Users & Roles): его создал Terraform 13.11 и удалил `terraform destroy`. `.pem` к нему не было, вход шёл через EC2 Instance Connect.
> Взлома не было. Хостинг ещё не выбран: по бизнес-плану основной вариант — Hetzner CX23 (`DEPLOY_NOTES.md`, `LAUNCH_CHECKLIST.md`),
> EC2 — альтернатива. Разделы 1 и 3 ниже применимы только если выбран EC2; адрес и ключ — от нового сервера.

**Решение владельца 2026-11-16: EC2 на кредитах Free plan, сервер временный** — поднимается под задачи, которым нужен сервер,
после них владелец его останавливает (stop). Пока остановлен, кредиты списываются только за диск и Elastic IP (~$8/мес).
Сервер: `i-017e7dfd9fced32f5`, `m7i-flex.large` (2 vCPU, 8 ГБ), `eu-central-1`, Ubuntu 24.04, gp3 40 ГБ (шифрован), IMDSv2 hop 2.
Elastic IP `63.180.126.91`. SG `sg-095c0abb3b8fd462c` (22 — только IP владельца, 80/443 — все). Ключ: `C:\Users\kirit\.ssh\autoforyou-ec2.pem`.
Сменился домашний IP → обновить правило 22 в SG, иначе SSH не пустит.

> **Состояние на 2026-11-16 (блоки 0–7 `docs/archive/EC2_CREDITS_ROADMAP.md` выполнены).** Стек работает по `https://63-180-126-91.sslip.io` (Let's Encrypt)
> (тег `3de025a`, `~deploy/autoforyou`, ветка `finish-site`). S3: бакеты `autoforyou-{media,private,backup}-piats1`,
> IAM `autoforyou-app-s3` и `autoforyou-backup-s3`. Подробности и цифры — `PROGRESS.md`, раздел «EC2 за кредиты».
> Осталось за владельцем: `createsuperuser` (пароль), свой `BACKUP_ENCRYPTION_PASSPHRASE` (сейчас сгенерирован на сервере),
> Healthchecks.io и uptime-монитор, данные для `launch_check` (реквизиты, брокер), домен — для HTTPS (7.1) и автодеплоя.
> SSH из Git Bash не читает `.pem` (CRLF) — использовать `C:\Windows\System32\OpenSSH\ssh.exe`.
Полная инструкция — `DEPLOY_NOTES.md` и `docs/LAUNCH_CHECKLIST.md`. Здесь только шаги, которые может сделать только владелец
(аккаунт AWS, домен, GitHub, пароли). Секреты никуда не пересылать: ни в чат, ни в git.

## Блокеры перед слиянием PR #38 (10.4)
- 10.2 (красный CI на `ssr.spec.ts`) — закрыт: CI на `5fb3c49` зелёный, включая E2E.
- 10.3 (фото с адресом `http://backend:8000`) — исправлен 2026-11-16, ещё не закоммичен и не прогнан в CI.

## 1. AWS-консоль
- [ ] **AWS Budget** с оповещениями на почту — до создания инстанса (нужны права `budgets:*` у `claude-deploy`).
- [ ] **Инстанс** создаёт Claude через AWS CLI: key pair (ключ в `C:\Users\kirit\.ssh\`), диск gp3 40 ГБ сразу
      (минимум из `docs/tasks/7.5-deploy.md`), IMDSv2 (hop limit 2, если контейнеры ходят в S3 через роль инстанса).
- [ ] **Elastic IP** → Associate с инстансом. Без него публичный IP меняется после stop/start, и DNS с сертификатом ломаются.
- [ ] **Security Group** входящие: `22/tcp` — только «My IP»; `80/tcp` и `443/tcp` — `0.0.0.0/0` и `::/0`. Всё остальное закрыто
      (Postgres и Redis наружу не публикуются).
- [ ] **Бакеты S3** в `eu-central-1` (тот же регион — без платы за трафик между EC2 и S3):
  - медиа: публичное чтение фото → `S3_BUCKET_NAME`, `S3_REGION=eu-central-1`;
  - приватные файлы (документы) — отдельный бакет без публичного доступа → `PRIVATE_S3_BUCKET_NAME`;
  - бэкапы — отдельный бакет, ключ только на запись в него → `BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY`;
  - IAM-пользователь (или роль инстанса) с доступом только к этим бакетам → `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
  - Хост бакета медиа (например `<bucket>.s3.eu-central-1.amazonaws.com`) — в `NEXT_PUBLIC_IMAGE_HOSTS` и `CSP_IMG_SRC_EXTRA` (`https://…`).
- [ ] **`BACKUP_ENCRYPTION_PASSPHRASE`** — придумать длинный пароль и сохранить в менеджере паролей **вне сервера**.
      Без него бэкап из облака не расшифровать.

## 2. Домен
- [ ] Купить домен (если ещё нет) и создать **A-запись** `домен → Elastic IP` (и `www`, если нужен, тогда `DOMAIN_WWW=true`).
      Без домена Let's Encrypt сертификат не выдаст. Проверка: `nslookup домен` показывает Elastic IP.
- [ ] Email для уведомлений Let's Encrypt → `LETSENCRYPT_EMAIL`.

## 3. Доступ для меня (Claude) к серверу
- [ ] SSH-ключ создаётся вместе с новым инстансом и сохраняется в `C:\Users\kirit\.ssh\`. Чтобы Claude выполнял команды
      на сервере, владелец разрешает в настройках правило вида `Bash(ssh -i <ключ> ubuntu@<Elastic IP> *)`.
- [ ] Репозиторий приватный → серверу нужен **Deploy key** (GitHub → репозиторий → Settings → Deploy keys, только чтение).
      Ключ создаётся на сервере (`ssh-keygen -t ed25519`), в GitHub — только его `.pub`.

## 4. GitHub (автодеплой, после слияния PR #38 в `main`)
Settings → Environments → `production` (Deployment branches: только `main`). В environment:
- [ ] Secrets: `SSH_HOST` (Elastic IP или домен), `SSH_USER` (`deploy`), `SSH_KEY` (приватный ключ **отдельной** пары только для CI),
      `SSH_PORT` (`22`), `SSH_HOST_FINGERPRINT` — строка `SHA256:…` из `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` на сервере
      (я выведу её после `server-setup.sh`).
- [ ] Variables: `DEPLOY_ENABLED=true`, `DEPLOY_PATH` (например `/home/deploy/autoforyou`), `SITE_URL=https://домен`.
- [ ] Слияние PR #38 в `main` — только по твоему явному «да».

## 5. Мониторинг (до открытия регистрации, можно после первого деплоя)
- [ ] UptimeRobot на `https://домен/healthz` с оповещением в Telegram.
- [ ] Healthchecks.io: две проверки → `CELERY_HEARTBEAT_URL` (5 мин) и `BACKUP_HEARTBEAT_URL` (1 день).

## Что сделаю я, когда будет доступ
1. `sudo ./scripts/server-setup.sh` (Docker, пользователь `deploy`, ufw 22/80/443, автообновления, swap), расширение диска.
2. `git clone`, `.env` из `.env.example` по `docs/LAUNCH_CHECKLIST.md` (секреты сгенерирую на сервере, в чат не выведу),
   первый деплой с `C2C_ENABLED=false`, `C2C_PUBLIC_POSTING_ENABLED=false`, `PAYMENTS_ENABLED=false`.
3. `./deploy.sh --build` → `./scripts/init-letsencrypt.sh` → `createsuperuser` (пароль вводишь ты) → `backup.sh --now` → `launch_check`.
4. Смоук: `/healthz`, `/`, `/calculator`, `/privacy`, `/terms` → 200; `/api/v1/local/listings/` → 404, `/ua` → «Скоро»; HTTPS с HSTS и CSP.
5. Откат: второй деплой, затем `./deploy.sh --rollback` и обратно, проверка тега в `.deploy/previous_tag`.
6. Остатки «на сервере»: 6.8 (замер LCP Lighthouse mobile), 9.55 (учения по `docs/RUNBOOK.md`), 9.54 (снять `noindex` с `/calculator`
   только после сверки ставок с брокером).
