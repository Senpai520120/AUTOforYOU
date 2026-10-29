#!/bin/sh
# Выполняется ВНУТРИ контейнера backup по команде scripts/restore.sh (задача 7.4). Данные идут через stdin.
#   restore-inner.sh dump        stdin = .dump           -> pg_restore в базу PGDATABASE (clean, if-exists, no-owner)
#   restore-inner.sh dump-gpg    stdin = .dump.gpg       -> расшифровка BACKUP_ENCRYPTION_PASSPHRASE и то же самое
# Сам по себе ничего не спрашивает: подтверждение и остановка сервисов - в scripts/restore.sh.
set -eu
umask 077

err() { printf '[restore] ОШИБКА: %s\n' "$*" >&2; }
mode="${1:-}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

case "$mode" in
    dump) cat > "$work/dump" ;;
    dump-gpg)
        if [ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]; then
            err "для .gpg нужен BACKUP_ENCRYPTION_PASSPHRASE"
            exit 2
        fi
        cat > "$work/enc"
        printf '%s' "$BACKUP_ENCRYPTION_PASSPHRASE" > "$work/pass"
        gpg --batch --quiet --no-symkey-cache --pinentry-mode loopback --passphrase-file "$work/pass" --decrypt -o "$work/dump" "$work/enc" \
            || { err "расшифровка не удалась: неверный пароль или файл повреждён"; exit 1; }
        ;;
    *) err "режим: dump | dump-gpg"; exit 2 ;;
esac

# Дамп проверяется до того, как что-то будет затёрто --clean.
pg_restore --list "$work/dump" > /dev/null || { err "файл не является корректным дампом Postgres, база не тронута"; exit 1; }
echo "[restore] pg_restore --clean --if-exists --single-transaction --no-owner в базу ${PGDATABASE:-?}"
pg_restore --clean --if-exists --single-transaction --no-owner --no-acl --exit-on-error -d "${PGDATABASE}" "$work/dump"
echo "[restore] база восстановлена"
