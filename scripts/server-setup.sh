#!/usr/bin/env bash
# server-setup.sh - необязательный помощник для чистого VPS (Ubuntu 22.04/24.04, Debian 12), задача 7.5.
# Запуск один раз от root:   sudo ./scripts/server-setup.sh
# Идемпотентен: повторный запуск ничего не ломает и не создаёт второй swap. Каждое действие печатается.
# То же самое руками описано в DEPLOY_NOTES.md (раздел «Ручная подготовка сервера»).
#
# Переменные (необязательные):
#   DEPLOY_USER    пользователь для деплоя (по умолчанию deploy)
#   SSH_PORT       дополнительный порт SSH для ufw (порты берутся из `sshd -T`, запасной - 22)
#   SWAP_SIZE_GB   размер swap-файла, если swap ещё нет (по умолчанию 2)   # ПРОВЕРИТЬ замером под нагрузкой (4 ГБ RAM)
#   SWAP_SWAPPINESS значение vm.swappiness (по умолчанию 10)                # ПРОВЕРИТЬ замером под нагрузкой
# Скрипт не содержит архитектурно-зависимых путей: архитектура берётся у dpkg (amd64/arm64).
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
SSH_PORT="${SSH_PORT:-}"
SWAP_SIZE_GB="${SWAP_SIZE_GB:-2}"
SWAP_SWAPPINESS="${SWAP_SWAPPINESS:-10}"
# Пути можно подменить (тесты в песочнице); на сервере значения по умолчанию.
SWAP_FILE="${SWAP_FILE:-/swapfile}"
FSTAB_FILE="${FSTAB_FILE:-/etc/fstab}"
SYSCTL_FILE="${SYSCTL_FILE:-/etc/sysctl.d/99-autoforyou.conf}"

step() { echo "[server-setup] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "запускайте от root (sudo ./scripts/server-setup.sh)."
[[ "$SWAP_SIZE_GB" =~ ^[1-9][0-9]*$ ]] || die "SWAP_SIZE_GB должен быть целым числом > 0 (сейчас '$SWAP_SIZE_GB')."
[[ "$DEPLOY_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || die "DEPLOY_USER содержит недопустимые символы."

export DEBIAN_FRONTEND=noninteractive

# ─── 1. Пакеты и Docker из официального репозитория ──────────────────────────
if [ "${SERVER_SETUP_SKIP_APT:-0}" = 1 ]; then
    step "пакеты и Docker: пропущено (SERVER_SETUP_SKIP_APT=1)"
else
    step "apt: базовые пакеты (ca-certificates, curl, gnupg, git, ufw, unattended-upgrades)"
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg git ufw unattended-upgrades

    if command -v docker > /dev/null 2>&1 && docker compose version > /dev/null 2>&1; then
        step "Docker и Compose v2 уже установлены - пропускаю"
    else
        # shellcheck disable=SC1091
        . /etc/os-release
        case "${ID:-}" in ubuntu | debian) ;; *) die "поддерживаются Ubuntu и Debian (сейчас '${ID:-?}')." ;; esac
        codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
        [ -n "$codename" ] || die "не удалось определить кодовое имя релиза из /etc/os-release."
        step "Docker: ключ и репозиторий download.docker.com ($ID $codename, архитектура $(dpkg --print-architecture))"
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
        chmod a+r /etc/apt/keyrings/docker.asc
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $codename stable" \
            > /etc/apt/sources.list.d/docker.list
        step "Docker: установка docker-ce, compose-plugin, buildx-plugin"
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
        systemctl enable --now docker
    fi
fi

# ─── 2. Пользователь для деплоя ──────────────────────────────────────────────
if id "$DEPLOY_USER" > /dev/null 2>&1; then
    step "пользователь $DEPLOY_USER уже есть"
else
    step "создаю пользователя $DEPLOY_USER (без пароля, вход только по ключу)"
    useradd --create-home --shell /bin/bash "$DEPLOY_USER"
fi
step "добавляю $DEPLOY_USER в группу docker (доступ к Docker = права, близкие к root: давайте только доверенным)"
usermod -aG docker "$DEPLOY_USER"

# ─── 3. Файрвол ──────────────────────────────────────────────────────────────
# Docker сам открывает опубликованные порты в обход ufw. Compose публикует наружу только nginx (80/443);
# БД слушает 127.0.0.1. Не публикуйте другие порты без необходимости.
# Порты SSH берём у работающей конфигурации sshd (их может быть несколько), чтобы не запереть себя на нестандартном порту.
SSH_PORTS=()
while IFS= read -r port; do
    [ -n "$port" ] && SSH_PORTS+=("$port")
done < <(sshd -T 2> /dev/null | awk '/^port /{print $2}' | sort -un || true)
[ -n "$SSH_PORT" ] && SSH_PORTS+=("$SSH_PORT")
[ "${#SSH_PORTS[@]}" -gt 0 ] || SSH_PORTS=(22)
for port in "${SSH_PORTS[@]}"; do
    { [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -ge 1 ] && [ "$port" -le 65535 ]; } || die "порт SSH '$port' вне диапазона 1-65535."
done
step "ufw: разрешаю SSH-порты ${SSH_PORTS[*]}, 80/tcp, 443/tcp; остальное входящее закрыто"
ufw default deny incoming > /dev/null
ufw default allow outgoing > /dev/null
for port in "${SSH_PORTS[@]}"; do
    ufw allow "$port/tcp" > /dev/null
done
ufw allow 80/tcp > /dev/null
ufw allow 443/tcp > /dev/null
ufw --force enable > /dev/null

# ─── 4. Автоматические обновления безопасности ───────────────────────────────
step "unattended-upgrades: включаю ежедневные обновления безопасности"
if [ "${SERVER_SETUP_SKIP_APT:-0}" != 1 ]; then
    cat > /etc/apt/apt.conf.d/20auto-upgrades <<'APT'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT
fi

# ─── 5. Swap и vm.swappiness ─────────────────────────────────────────────────
if [ -n "$(swapon --show 2> /dev/null)" ]; then
    step "swap уже настроен ($(swapon --show --noheadings 2> /dev/null | head -n 1)) - не трогаю"
else
    step "swap не найден: создаю $SWAP_FILE на ${SWAP_SIZE_GB} ГБ"
    fallocate -l "${SWAP_SIZE_GB}G" "$SWAP_FILE" || dd if=/dev/zero of="$SWAP_FILE" bs=1M count=$((SWAP_SIZE_GB * 1024)) status=none
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" > /dev/null
    swapon "$SWAP_FILE"
    if ! grep -qs "^${SWAP_FILE}[[:space:]]" "$FSTAB_FILE"; then
        echo "$SWAP_FILE none swap sw 0 0" >> "$FSTAB_FILE"
        step "добавлено в $FSTAB_FILE (swap переживёт перезагрузку)"
    fi
fi
step "vm.swappiness=$SWAP_SWAPPINESS -> $SYSCTL_FILE"
mkdir -p "$(dirname "$SYSCTL_FILE")"
printf '# Записано scripts/server-setup.sh (задача 7.5). Низкое значение: swap только как страховка от OOM.\nvm.swappiness=%s\n' "$SWAP_SWAPPINESS" > "$SYSCTL_FILE"
sysctl -w "vm.swappiness=$SWAP_SWAPPINESS" > /dev/null

# ─── Итог ────────────────────────────────────────────────────────────────────
step "готово. Дальше:"
step "  1) добавьте публичный SSH-ключ в ~$DEPLOY_USER/.ssh/authorized_keys (chmod 700 .ssh, 600 authorized_keys)"
step "  2) войдите как $DEPLOY_USER: git clone <репозиторий>, cp .env.docker.example .env, заполните .env"
step "  3) ./deploy.sh --build ; затем ./scripts/init-letsencrypt.sh (если TLS_MODE=letsencrypt)"
step "  Отключите вход по паролю и root в /etc/ssh/sshd_config только после проверки входа по ключу (скрипт SSH не меняет)."
