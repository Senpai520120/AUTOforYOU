#!/usr/bin/env bash
# Проверка, что бэкап восстанавливается (задача 7.4). Рабочая БД НЕ затрагивается: дамп разворачивается во
# временный контейнер Postgres без томов (tmpfs) в отдельной docker-сети; после проверки всё удаляется.
#   ./scripts/backup-verify.sh                  последний autoforyou_*.dump из BACKUP_DIR
#   ./scripts/backup-verify.sh --file <путь>    конкретный дамп (*.dump)
#   ./scripts/backup-verify.sh --from-remote    последний зашифрованный дамп из BACKUP_S3_BUCKET (нужен BACKUP_ENCRYPTION_PASSPHRASE)
# Проверки: pg_restore, manage.py migrate --check, счётчики ключевых таблиц. При успехе пишет BACKUP_DIR/.last_verify.
# Выполнять раз в месяц, результат записывать в журнал. Нестандартный compose (CI): COMPOSE_CMD="...".
set -euo pipefail

usage() {
    echo "Использование: $0 [--file <файл.dump> | --from-remote]" >&2
    exit 2
}

mode=latest
file=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --from-remote) mode=remote; shift ;;
        --file) [ "$#" -ge 2 ] || usage; mode="file"; file="$2"; shift 2 ;;
        *) usage ;;
    esac
done

cd "$(dirname "${BASH_SOURCE[0]}")/.."
read -r -a DC <<< "${COMPOSE_CMD:-docker compose}"
ENV_FILE="${ENV_FILE:-.env}"

env_value() {  # значение из переменной окружения или из env-файла (без eval)
    local name="$1" default="$2" v
    v="${!name:-}"
    if [ -z "$v" ] && [ -f "$ENV_FILE" ]; then
        v=$(grep -E "^${name}=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d '\r' || true)
    fi
    echo "${v:-$default}"
}

backup_dir=$(env_value BACKUP_DIR ./backups)
# Каталог создаёт контейнер backup (root, права 700): с хоста читать его нужно от root (sudo) или владельца.
if [ ! -d "$backup_dir" ] || [ ! -r "$backup_dir" ] || [ ! -x "$backup_dir" ]; then
    echo "ОШИБКА: каталог бэкапов не найден или недоступен: $backup_dir (создан контейнером от root с правами 700: запустите через sudo)" >&2
    exit 2
fi

case "$mode" in
    latest)
        file=$(find "$backup_dir" -maxdepth 1 -name 'autoforyou_*.dump' | sort | tail -n 1)
        [ -n "$file" ] || { echo "ОШИБКА: в $backup_dir нет ни одного autoforyou_*.dump. Сначала ./scripts/backup.sh --now" >&2; exit 2; }
        ;;
    file)
        if [ ! -f "$file" ] || [ ! -r "$file" ]; then echo "ОШИБКА: файл не найден: $file" >&2; exit 2; fi
        case "$file" in *.dump) ;; *) echo "ОШИБКА: ожидается *.dump (для .gpg используйте --from-remote)" >&2; exit 2 ;; esac
        ;;
esac
if [ "$mode" = remote ]; then source_desc="хранилище BACKUP_S3_BUCKET (последний .dump.gpg)"; else source_desc="$file"; fi

pg_image="${VERIFY_PG_IMAGE:-$(sed -n 's/^[[:space:]]*image:[[:space:]]*\(postgres:[^[:space:]]*\).*/\1/p' docker-compose.yml | head -n 1)}"
[ -n "$pg_image" ] || { echo "ОШИБКА: не удалось определить образ postgres из docker-compose.yml (задайте VERIFY_PG_IMAGE)" >&2; exit 2; }

project=$("${DC[@]}" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')
suffix="$(date +%s)-$$"
net="afy-verify-$suffix"
cname="afy-verify-db-$suffix"
verify_pw=$(head -c 24 /dev/urandom | base64 | tr -d '/+=
')

# Образ backend (собран compose'ом): нужен для migrate --check. Запускается голым docker run, без env_file и боевых секретов.
backend_image=$("${DC[@]}" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["services"]["backend"].get("image",""))')
[ -n "$backend_image" ] || backend_image="${project}-backend"
docker image inspect "$backend_image" > /dev/null 2>&1     || { echo "ОШИБКА: образ $backend_image не найден. Соберите: docker compose build backend" >&2; exit 2; }

cleanup() {
    docker rm -f -v "$cname" > /dev/null 2>&1 || true
    docker network rm "$net" > /dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# Отдельная внутренняя сеть (без выхода наружу и без рабочих сервисов): временная БД не видит db/redis стека.
docker network create --internal "$net" > /dev/null

echo "Проверка восстановления из: $source_desc (временная БД $pg_image, рабочая БД не затрагивается)"
docker run -d --name "$cname" --network "$net" --network-alias afy-verify-db --tmpfs /var/lib/postgresql     -e POSTGRES_PASSWORD="$verify_pw" -e POSTGRES_DB=verify "$pg_image" > /dev/null
ready=0
for _ in $(seq 1 60); do
    if docker exec "$cname" psql -U postgres -d verify -Atc 'select 1' > /dev/null 2>&1; then ready=1; break; fi
    sleep 1
done
[ "$ready" -eq 1 ] || { echo "ОШИБКА: временный Postgres не стартовал" >&2; exit 1; }

echo "== pg_restore во временную БД"
if [ "$mode" = remote ]; then
    "${DC[@]}" run --rm -T backup /usr/local/bin/fetch-remote.sh | docker exec -i "$cname" pg_restore -U postgres -d verify --no-owner --no-acl --exit-on-error
else
    docker exec -i "$cname" pg_restore -U postgres -d verify --no-owner --no-acl --exit-on-error < "$file"
fi

echo "== manage.py migrate --check на восстановленной базе"
docker run --rm --network "$net" --entrypoint python     -e "DATABASE_URL=postgres://postgres:${verify_pw}@afy-verify-db:5432/verify"     -e "SECRET_KEY=verify-only-$(head -c 40 /dev/urandom | base64 | tr -d '/+=
')"     -e DEBUG=false -e ALLOWED_HOSTS=localhost -e REDIS_URL=     "$backend_image" manage.py migrate --check

echo "== Счётчики ключевых таблиц (только имена и числа)"
counts=$(docker exec "$cname" psql -U postgres -d verify -At -F ' : ' -c "
    select table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text
    from information_schema.tables
    where table_schema = 'public' and table_type = 'BASE TABLE'
      and (table_name = 'users_customuser' or table_name like 'local\_listings\_%' or table_name like 'pricing\_%')
    order by 1")
echo "$counts"
echo "$counts" | grep -q '^users_customuser : ' || { echo "ОШИБКА: в восстановленной базе нет таблицы users_customuser" >&2; exit 1; }

umask 077
if printf '%s ok source=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$([ "$mode" = remote ] && echo remote || basename "$file")" > "$backup_dir/.last_verify"; then
    echo "Проверка пройдена. Метка записана: $backup_dir/.last_verify"
else
    echo "Проверка пройдена, но метку $backup_dir/.last_verify записать не удалось (нужны права на каталог)" >&2
fi
