#!/bin/sh
# Резервная копия Postgres (+ медиа без S3), шифрование, отправка вне сервера, ротация (задача 7.4).
# Подключение к БД - стандартные PGHOST/PGUSER/PGPASSWORD/PGDATABASE. Код возврата 0 = всё настроенное выполнено.
# В лог не попадают пароль, passphrase и ключи (aws/gpg получают их через переменные и stdin).
set -eu
umask 077

BACKUP_DIR="${BACKUP_DIR_IN_CONTAINER:-/backups}"
KEEP_DAILY="${BACKUP_KEEP_DAILY:-7}"
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-3}"
MEDIA_DIR="${BACKUP_MEDIA_DIR:-/media}"
PRIVATE_MEDIA_DIR="${BACKUP_PRIVATE_MEDIA_DIR:-/private_media}"
ROTATE="${BACKUP_ROTATE_SCRIPT:-/usr/local/bin/rotate.sh}"
PREFIX=autoforyou
MEDIA_PREFIX=autoforyou-media

log() { printf '%s [backup] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
err() { printf '%s [backup] ОШИБКА: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

for pair in "KEEP_DAILY=$KEEP_DAILY" "KEEP_WEEKLY=$KEEP_WEEKLY" "KEEP_MONTHLY=$KEEP_MONTHLY"; do
    case "${pair#*=}" in
        '' | *[!0-9]*) err "BACKUP_${pair%%=*} должно быть числом, получено '${pair#*=}'"; exit 2 ;;
    esac
done
if [ "$KEEP_DAILY" -lt 1 ]; then
    err "BACKUP_KEEP_DAILY должно быть не меньше 1 (иначе новая копия удалилась бы сразу)"
    exit 2
fi
case "$BACKUP_DIR" in
    /?*) ;;
    *) err "BACKUP_DIR_IN_CONTAINER должен быть абсолютным путём"; exit 2 ;;
esac

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
stamp=$(date '+%Y-%m-%d_%H%M')
work="$BACKUP_DIR/.tmp.$$"
mkdir -p "$work"
# shellcheck disable=SC2329  # вызывается через trap
cleanup() { rm -rf "$work"; }
trap cleanup EXIT
trap 'err "прервано сигналом"; exit 1' INT TERM

dump_name="${PREFIX}_${stamp}.dump"
media_name="${MEDIA_PREFIX}_${stamp}.tar.gz"
failed=0

# ─── 1. Дамп базы ────────────────────────────────────────────────────────────
log "pg_dump -> $dump_name (база ${PGDATABASE:-?} на ${PGHOST:-?})"
if ! pg_dump -Fc -Z 6 -f "$work/$dump_name"; then
    err "pg_dump завершился с ошибкой, бэкап не создан (старые копии не тронуты)"
    exit 1
fi
if ! pg_restore --list "$work/$dump_name" > /dev/null; then
    err "проверка pg_restore --list не прошла: дамп повреждён, бэкап не создан (старые копии не тронуты)"
    exit 1
fi
mv "$work/$dump_name" "$BACKUP_DIR/$dump_name"
(cd "$BACKUP_DIR" && sha256sum "$dump_name" > "$work/$dump_name.sha256" && mv "$work/$dump_name.sha256" "$dump_name.sha256")
log "дамп готов: $dump_name ($(wc -c < "$BACKUP_DIR/$dump_name") байт), контрольная сумма записана"

# ─── 2. Медиафайлы (только если лежат в томах, а не в S3) ─────────────────────
have_media=0
tar_dirs=""
if [ -z "${S3_BUCKET_NAME:-}" ] && [ -d "$MEDIA_DIR" ]; then
    tar_dirs="$tar_dirs $(basename "$MEDIA_DIR")"
else
    log "медиа не архивируются: фото объявлений в S3 (S3_BUCKET_NAME задан) или каталог $MEDIA_DIR недоступен"
fi
if [ -z "${PRIVATE_S3_BUCKET_NAME:-}" ] && [ -d "$PRIVATE_MEDIA_DIR" ]; then
    tar_dirs="$tar_dirs $(basename "$PRIVATE_MEDIA_DIR")"
else
    log "приватные медиа не архивируются: PRIVATE_S3_BUCKET_NAME задан или каталог $PRIVATE_MEDIA_DIR недоступен"
fi
if [ -n "$tar_dirs" ]; then
    # Архив строится от родителя каталогов: внутри media/... и private_media/... (восстановление: tar -xzf -C /app).
    parent=$(dirname "$MEDIA_DIR")
    # shellcheck disable=SC2086  # tar_dirs - список имён каталогов без пробелов
    if tar -czf "$work/$media_name" -C "$parent" $tar_dirs && tar -tzf "$work/$media_name" > /dev/null; then
        mv "$work/$media_name" "$BACKUP_DIR/$media_name"
        (cd "$BACKUP_DIR" && sha256sum "$media_name" > "$work/$media_name.sha256" && mv "$work/$media_name.sha256" "$media_name.sha256")
        have_media=1
        log "архив медиа готов: $media_name (каталоги:$tar_dirs)"
    else
        err "не удалось создать архив медиа; дамп базы сохранён"
        failed=1
    fi
fi

# ─── 3. Локальная ротация (только после успешного нового дампа) ───────────────
rotate_local() {
    # Метки всех наших файлов -> план удаления -> удаляем файлы с этими метками.
    # shellcheck disable=SC2012  # имена отфильтрованы sed по строгому шаблону
    stamps=$(ls -1 "$BACKUP_DIR" | sed -n -e "s/^${PREFIX}_\\([0-9-]*_[0-9]*\\)\\.dump\$/\\1/p" -e "s/^${MEDIA_PREFIX}_\\([0-9-]*_[0-9]*\\)\\.tar\\.gz\$/\\1/p" | sort -u)
    to_delete=$(printf '%s\n' "$stamps" | "$ROTATE" plan "$KEEP_DAILY" "$KEEP_WEEKLY" "$KEEP_MONTHLY") || return 1
    # Нового архива медиа в этом запуске нет: последний существующий не удаляем.
    keep_media=""
    if [ "$have_media" -eq 0 ]; then
        # shellcheck disable=SC2012  # имена отфильтрованы sed по строгому шаблону
        keep_media=$(ls -1 "$BACKUP_DIR" | sed -n "s/^${MEDIA_PREFIX}_\\([0-9-]*_[0-9]*\\)\\.tar\\.gz\$/\\1/p" | sort | tail -n 1)
    fi
    for s in $to_delete; do
        rm -f "$BACKUP_DIR/${PREFIX}_${s}.dump" "$BACKUP_DIR/${PREFIX}_${s}.dump.sha256"
        if [ "$s" = "$keep_media" ]; then
            log "ротация: архив медиа $s сохранён (нового архива в этом запуске нет)"
        else
            rm -f "$BACKUP_DIR/${MEDIA_PREFIX}_${s}.tar.gz" "$BACKUP_DIR/${MEDIA_PREFIX}_${s}.tar.gz.sha256"
        fi
        log "ротация: удалена копия $s"
    done
}
if ! rotate_local; then
    err "локальная ротация не выполнена"
    failed=1
fi

# ─── 4. Копия вне сервера (шифруется ДО отправки) ─────────────────────────────
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
    if [ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]; then
        err "BACKUP_S3_BUCKET задан, но шифрование не настроено (нет BACKUP_ENCRYPTION_PASSPHRASE): отправка вне сервера не выполнена, данные наружу не уходили"
        failed=1
    elif [ -z "${BACKUP_S3_ACCESS_KEY_ID:-}" ] || [ -z "${BACKUP_S3_SECRET_ACCESS_KEY:-}" ]; then
        err "BACKUP_S3_BUCKET задан, но нет BACKUP_S3_ACCESS_KEY_ID / BACKUP_S3_SECRET_ACCESS_KEY: отправка вне сервера не выполнена"
        failed=1
    else
        AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY_ID"
        AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_ACCESS_KEY"
        AWS_DEFAULT_REGION="${BACKUP_S3_REGION:-auto}"
        # R2 и часть S3-совместимых хранилищ не принимают дополнительные контрольные суммы aws-cli v2 по умолчанию.
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

        upload() {  # $1 - файл в BACKUP_DIR
            enc="$work/$1.gpg"
            if ! printf '%s' "$BACKUP_ENCRYPTION_PASSPHRASE" | gpg --batch --yes --quiet --no-symkey-cache --pinentry-mode loopback \
                    --passphrase-fd 0 --symmetric --cipher-algo AES256 -o "$enc" "$BACKUP_DIR/$1"; then
                err "шифрование gpg не удалось для $1, файл не отправлен"
                return 1
            fi
            if ! aws_s3 cp --only-show-errors "$enc" "${remote_base}$1.gpg"; then
                err "отправка $1.gpg в хранилище не удалась (проверьте BACKUP_S3_* и доступ к bucket)"
                rm -f "$enc"
                return 1
            fi
            rm -f "$enc"
            log "отправлено вне сервера (зашифровано AES256): $1.gpg"
        }

        remote_ok=1
        upload "$dump_name" || remote_ok=0
        if [ "$have_media" -eq 1 ]; then upload "$media_name" || remote_ok=0; fi

        if [ "$remote_ok" -eq 1 ]; then
            # Ротация в хранилище: только после успешной отправки нового дампа.
            if listing=$(aws_s3 ls "$remote_base" 2>&1); then
                r_stamps=$(printf '%s\n' "$listing" | awk '{print $NF}' \
                    | sed -n -e "s/^${PREFIX}_\\([0-9-]*_[0-9]*\\)\\.dump\\.gpg\$/\\1/p" -e "s/^${MEDIA_PREFIX}_\\([0-9-]*_[0-9]*\\)\\.tar\\.gz\\.gpg\$/\\1/p" | sort -u)
                r_delete=$(printf '%s\n' "$r_stamps" | "$ROTATE" plan "$KEEP_DAILY" "$KEEP_WEEKLY" "$KEEP_MONTHLY") || r_delete=""
                for s in $r_delete; do
                    aws_s3 rm --only-show-errors "${remote_base}${PREFIX}_${s}.dump.gpg" || { err "не удалось удалить старую копию $s в хранилище"; failed=1; }
                    aws_s3 rm --only-show-errors "${remote_base}${MEDIA_PREFIX}_${s}.tar.gz.gpg" > /dev/null 2>&1 || true
                    log "ротация в хранилище: удалена копия $s"
                done
            else
                err "не удалось получить список файлов в хранилище, ротация там пропущена"
                failed=1
            fi
        else
            failed=1
        fi
    fi
else
    log "копия вне сервера не настроена (BACKUP_S3_BUCKET пуст): копии лежат только на этом сервере"
fi

# ─── 5. Метка успеха для healthcheck ──────────────────────────────────────────
if [ "$failed" -eq 0 ]; then
    date '+%Y-%m-%d %H:%M:%S' > "$work/.last_success"
    mv "$work/.last_success" "$BACKUP_DIR/.last_success"
    log "готово"
    exit 0
fi
err "бэкап выполнен не полностью (см. ошибки выше); метка успеха не обновлена"
exit 1
