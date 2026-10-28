#!/bin/sh
# Скачивает из хранилища последний зашифрованный дамп, расшифровывает и пишет дамп в stdout (задача 7.4).
# Всё остальное (логи, ошибки) - в stderr. Нужны BACKUP_S3_* и BACKUP_ENCRYPTION_PASSPHRASE.
# Использование: fetch-remote.sh [ИМЯ_ФАЙЛА.dump.gpg]   (без аргумента - самый свежий)
set -eu
umask 077

err() { printf '%s [fetch-remote] ОШИБКА: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
info() { printf '%s [fetch-remote] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

for v in BACKUP_S3_BUCKET BACKUP_S3_ACCESS_KEY_ID BACKUP_S3_SECRET_ACCESS_KEY BACKUP_ENCRYPTION_PASSPHRASE; do
    eval "val=\${$v:-}"
    if [ -z "$val" ]; then
        err "не задано $v: копия вне сервера не настроена"
        exit 2
    fi
done

AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_ACCESS_KEY"
AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-auto}"
AWS_REQUEST_CHECKSUM_CALCULATION=when_required
AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION AWS_REQUEST_CHECKSUM_CALCULATION AWS_RESPONSE_CHECKSUM_VALIDATION
remote_prefix="${BACKUP_S3_PREFIX:-autoforyou/}"
case "$remote_prefix" in */) ;; *) remote_prefix="$remote_prefix/" ;; esac
remote_base="s3://${BACKUP_S3_BUCKET}/${remote_prefix}"

aws_s3() {
    if [ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]; then
        aws --endpoint-url "$BACKUP_S3_ENDPOINT_URL" s3 "$@"
    else
        aws s3 "$@"
    fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

key="${1:-}"
if [ -z "$key" ]; then
    listing=$(aws_s3 ls "$remote_base") || { err "не удалось получить список файлов в хранилище"; exit 1; }
    key=$(printf '%s\n' "$listing" | awk '{print $NF}' | grep -E '^autoforyou_[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}\.dump\.gpg$' | sort | tail -n 1 || true)
    if [ -z "$key" ]; then
        err "в хранилище нет ни одного autoforyou_*.dump.gpg"
        exit 1
    fi
fi
case "$key" in
    autoforyou_*.dump.gpg) ;;
    *) err "имя файла должно быть autoforyou_*.dump.gpg"; exit 2 ;;
esac
case "$key" in */* | *..*) err "недопустимое имя файла"; exit 2 ;; esac

info "скачиваю $key"
aws_s3 cp --only-show-errors "${remote_base}${key}" "$work/enc" || { err "скачивание $key не удалось"; exit 1; }
printf '%s' "$BACKUP_ENCRYPTION_PASSPHRASE" > "$work/pass"
if ! gpg --batch --quiet --no-symkey-cache --pinentry-mode loopback --passphrase-file "$work/pass" --decrypt -o "$work/dump" "$work/enc"; then
    err "расшифровка не удалась: неверный BACKUP_ENCRYPTION_PASSPHRASE или файл повреждён"
    exit 1
fi
pg_restore --list "$work/dump" > /dev/null || { err "расшифрованный файл не является дампом Postgres"; exit 1; }
info "расшифровано и проверено: $key"
cat "$work/dump"
