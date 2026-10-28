#!/usr/bin/env bash
# Тесты ротации и безопасного поведения backup.sh (задача 7.4). Без Docker и сети: pg_dump/aws - заглушки в PATH.
# Запуск: ./scripts/tests/test_backup_rotation.sh   Код возврата 0 = все проверки прошли.
# shellcheck disable=SC2015,SC2016  # A && B || C в проверках намеренно; одинарные кавычки - тексты заглушек
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ROTATE="$ROOT/docker/backup/rotate.sh"
BACKUP="$ROOT/docker/backup/backup.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fails=0

ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }
check() { if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (ожидалось: $2 | получено: $3)"; fi; }

# ── 1. Ротация: 40 дней подряд, 7/4/3 ────────────────────────────────────────
# Ожидание считается независимо (GNU date), не тем же кодом, что в rotate.sh.
base=2026-03-01   # 1-е число месяца
stamps=""
for i in $(seq 0 39); do
    stamps="$stamps$(date -u -d "$base + $i days" +%Y-%m-%d)_0330"$'\n'
done
today=$(date -u -d "$base + 39 days" +%Y-%m-%d)
expected_keep=""
n=0
for i in $(seq 39 -1 0); do
    d=$(date -u -d "$base + $i days" +%Y-%m-%d)
    [ $n -lt 7 ] && { expected_keep="$expected_keep$d"$'\n'; n=$((n + 1)); }
done
n=0
for i in $(seq 39 -1 0); do
    d=$(date -u -d "$base + $i days" +%Y-%m-%d)
    if [ "$(date -u -d "$d" +%u)" = 7 ] && [ $n -lt 4 ]; then expected_keep="$expected_keep$d"$'\n'; n=$((n + 1)); fi
done
n=0
for i in $(seq 39 -1 0); do
    d=$(date -u -d "$base + $i days" +%Y-%m-%d)
    if [ "${d:8:2}" = 01 ] && [ $n -lt 3 ]; then expected_keep="$expected_keep$d"$'\n'; n=$((n + 1)); fi
done
expected_keep=$(printf '%s' "$expected_keep" | sort -u)
deleted=$(printf '%s' "$stamps" | "$ROTATE" plan 7 4 3 | sort)
kept=$(comm -23 <(printf '%s' "$stamps" | sort) <(printf '%s\n' "$deleted") | cut -c1-10 | sort -u)
check "ротация 40 дней при 7/4/3 оставляет ровно ожидаемые даты" "$expected_keep" "$kept"
check "дата сегодняшней копии (самая новая) сохранена ($today)" "$today" "$(printf '%s\n' "$kept" | tail -n 1)"

# Несколько копий за день: остаётся самая поздняя; мусорные строки игнорируются.
out=$(printf '%s\n' 2026-05-02_0100 2026-05-02_0330 2026-05-02_1200 мусор 'x.dump' | "$ROTATE" plan 7 4 3 | sort)
check "из трёх копий за день остаётся самая поздняя, мусор не трогается" $'2026-05-02_0100\n2026-05-02_0330' "$out"

# Некорректные аргументы.
if printf '' | "$ROTATE" plan 7 x 3 2> /dev/null; then bad "нечисловой срок должен давать ошибку"; else ok "нечисловой срок даёт ошибку"; fi

# ── 2. backup.sh с заглушками ────────────────────────────────────────────────
mkdir -p "$TMP/bin"
cat > "$TMP/bin/pg_restore" <<'MOCK'
#!/bin/sh
exit 0
MOCK
cat > "$TMP/bin/aws" <<'MOCK'
#!/bin/sh
echo "aws $*" >> "$MOCK_AWS_LOG"
exit 0
MOCK
chmod +x "$TMP/bin/pg_restore" "$TMP/bin/aws"
printf '#!/bin/sh\necho DUMPDATA > "${2:-}"\n' > /dev/null

make_pg_dump_ok() {
    cat > "$TMP/bin/pg_dump" <<'MOCK'
#!/bin/sh
# pg_dump -Fc -Z 6 -f FILE
while [ "$#" -gt 0 ]; do [ "$1" = "-f" ] && { echo DUMPDATA > "$2"; exit 0; }; shift; done
exit 1
MOCK
    chmod +x "$TMP/bin/pg_dump"
}
make_pg_dump_fail() {
    printf '#!/bin/sh\necho "pg_dump: connection refused" >&2\nexit 1\n' > "$TMP/bin/pg_dump"
    chmod +x "$TMP/bin/pg_dump"
}

run_backup() {  # печатает лог, код возврата - в RC
    set +e
    PATH="$TMP/bin:$PATH" BACKUP_DIR_IN_CONTAINER="$TMP/backups" BACKUP_MEDIA_DIR="$TMP/data/media" \
        BACKUP_PRIVATE_MEDIA_DIR="$TMP/data/private_media" BACKUP_ROTATE_SCRIPT="$ROTATE" \
        MOCK_AWS_LOG="$TMP/aws.log" "$@" sh "$BACKUP" > "$TMP/out.log" 2>&1
    RC=$?
    set -e
}

mkdir -p "$TMP/data/media" "$TMP/data/private_media" "$TMP/backups"
echo photo > "$TMP/data/media/a.jpg"
chmod 700 "$TMP/backups"

# 2a. дамп не удался -> код != 0, старые файлы целы, временных файлов нет.
for d in 2026-01-01 2026-01-02 2026-01-03; do : > "$TMP/backups/autoforyou_${d}_0330.dump"; done
make_pg_dump_fail
run_backup env BACKUP_KEEP_DAILY=1 BACKUP_KEEP_WEEKLY=0 BACKUP_KEEP_MONTHLY=0
check "неудачный pg_dump -> код 1" 1 "$RC"
check "неудачный pg_dump -> ни одна старая копия не удалена" 3 "$(find "$TMP/backups" -name 'autoforyou_*.dump' | wc -l | tr -d ' ')"
check "неудачный pg_dump -> нет временных каталогов" 0 "$(find "$TMP/backups" -name '.tmp.*' | wc -l | tr -d ' ')"
grep -q "старые копии не тронуты" "$TMP/out.log" && ok "лог объясняет, что старое не тронуто" || bad "в логе нет пояснения"

# 2b. успешный дамп: файл + sha256 + права, ротация удаляет старое, метка успеха.
make_pg_dump_ok
run_backup env BACKUP_KEEP_DAILY=1 BACKUP_KEEP_WEEKLY=0 BACKUP_KEEP_MONTHLY=0
check "успешный бэкап -> код 0" 0 "$RC"
new=$(find "$TMP/backups" -name 'autoforyou_*.dump' -newer "$TMP/bin/pg_dump" | head -n 1)
[ -n "$new" ] && ok "новый дамп создан: $(basename "$new")" || bad "новый дамп не создан"
check "остался один дамп (старые удалены после успешного нового)" 1 "$(find "$TMP/backups" -name 'autoforyou_*.dump' | wc -l | tr -d ' ')"
[ -f "$new.sha256" ] && ok "контрольная сумма создана" || bad "нет .sha256"
(cd "$TMP/backups" && sha256sum -c "$(basename "$new").sha256" > /dev/null) && ok "sha256 сходится" || bad "sha256 не сходится"
# На NTFS (Git Bash) chmod не действует - права проверяем только там, где файловая система их держит.
probe="$TMP/probe"; : > "$probe"; chmod 600 "$probe"
if [ "$(stat -c %a "$probe")" = 600 ]; then
    check "права файла дампа 600" 600 "$(stat -c %a "$new")"
    check "права директории 700" 700 "$(stat -c %a "$TMP/backups")"
else
    echo "skip - права 600/700 (файловая система не поддерживает chmod; проверяется в CI и в контейнере)"
fi
[ -f "$TMP/backups/.last_success" ] && ok "метка .last_success записана" || bad "нет .last_success"
ls "$TMP"/backups/autoforyou-media_*.tar.gz > /dev/null 2>&1 && ok "архив медиа создан (S3 не задан)" || bad "нет архива медиа"

# 2c. S3_BUCKET_NAME задан -> медиа не архивируются, в логе причина.
rm -f "$TMP"/backups/autoforyou-media_*
run_backup env S3_BUCKET_NAME=b PRIVATE_S3_BUCKET_NAME=p
check "при S3 код 0" 0 "$RC"
check "при S3 архив медиа не создаётся" 0 "$(find "$TMP/backups" -name 'autoforyou-media_*' | wc -l | tr -d ' ')"
grep -q "медиа не архивируются" "$TMP/out.log" && ok "в логе сказано, почему нет архива медиа" || bad "нет пояснения про S3"

# 2d. bucket без passphrase -> код != 0, aws не вызывался, метка успеха не обновляется.
rm -f "$TMP/aws.log" "$TMP/backups/.last_success"
run_backup env BACKUP_S3_BUCKET=bk BACKUP_S3_ACCESS_KEY_ID=k BACKUP_S3_SECRET_ACCESS_KEY=s BACKUP_ENCRYPTION_PASSPHRASE=
check "bucket без passphrase -> код 1" 1 "$RC"
grep -q "шифрование не настроено" "$TMP/out.log" && ok "в логе: шифрование не настроено" || bad "нет сообщения про шифрование"
[ ! -e "$TMP/aws.log" ] && ok "aws не вызывался, данные наружу не уходили" || bad "aws был вызван без шифрования"
[ ! -f "$TMP/backups/.last_success" ] && ok "метка .last_success не обновлена после ошибки" || bad "метка .last_success обновлена после ошибки"

# 2e. успешная отправка: наружу уходят только *.gpg, секретов в логе нет, метка обновлена.
cat > "$TMP/bin/gpg" <<'MOCK'
#!/bin/sh
# Заглушка gpg: читает passphrase из stdin (как настоящий --passphrase-fd 0) и пишет "шифртекст" в -o.
out=""
while [ "$#" -gt 0 ]; do [ "$1" = "-o" ] && { out="$2"; shift; }; shift; done
cat > /dev/null
echo ENCRYPTED > "$out"
MOCK
chmod +x "$TMP/bin/gpg"
rm -f "$TMP/aws.log" "$TMP/backups/.last_success"
run_backup env BACKUP_S3_BUCKET=bk BACKUP_S3_ENDPOINT_URL=http://s3.invalid BACKUP_S3_ACCESS_KEY_ID=KEYID-ZZ-111     BACKUP_S3_SECRET_ACCESS_KEY=SECRET-ZZ-222 BACKUP_ENCRYPTION_PASSPHRASE=PASS-ZZ-333
check "успешная отправка -> код 0" 0 "$RC"
[ -f "$TMP/backups/.last_success" ] && ok "после успешной отправки метка записана" || bad "нет метки после успешной отправки"
uploads=$(grep -c ' cp ' "$TMP/aws.log" || true)
[ "$uploads" -ge 2 ] && ok "отправлены дамп и архив медиа ($uploads cp)" || bad "ожидалось >= 2 вызова cp, получено $uploads"
if grep ' cp ' "$TMP/aws.log" | grep -Evq '\.gpg [^ ]*\.gpg$'; then bad "cp без .gpg в источнике или назначении"; else ok "все cp: источник и назначение *.gpg"; fi
if grep -Eq '\.(dump|tar\.gz)( |$)' "$TMP/aws.log"; then bad "в вызовах aws есть незашифрованный .dump/.tar.gz"; else ok "ни одного .dump/.tar.gz без .gpg в вызовах aws"; fi
if grep -q 'PASS-ZZ-333\|SECRET-ZZ-222\|KEYID-ZZ-111' "$TMP/out.log" "$TMP/aws.log"; then bad "passphrase или ключи попали в лог"; else ok "в логах нет passphrase и ключей"; fi

# 2f. нового архива медиа нет (медиа в S3) -> последний старый архив не удаляется, остальные по ротации удаляются.
find "$TMP/backups" -name 'autoforyou*' -delete
for d in 2026-01-01 2026-01-02 2026-01-03; do
    : > "$TMP/backups/autoforyou_${d}_0330.dump"; echo m > "$TMP/backups/autoforyou-media_${d}_0330.tar.gz"
done
run_backup env S3_BUCKET_NAME=b PRIVATE_S3_BUCKET_NAME=p BACKUP_KEEP_DAILY=1 BACKUP_KEEP_WEEKLY=0 BACKUP_KEEP_MONTHLY=0
check "ротация без нового архива медиа -> код 0" 0 "$RC"
check "остался только последний старый архив медиа" "autoforyou-media_2026-01-03_0330.tar.gz" "$(cd "$TMP/backups" && ls autoforyou-media_*.tar.gz)"

if [ "$fails" -ne 0 ]; then echo "Провалено проверок: $fails"; exit 1; fi
echo "Все проверки прошли"
