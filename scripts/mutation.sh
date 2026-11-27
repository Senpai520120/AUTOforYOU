#!/usr/bin/env bash
# Мутационное тестирование одного модуля (cosmic-ray). Конфиги - mutation/<name>.toml.
#   bash scripts/mutation.sh security      # core/security_settings.py, ~10 мин
#   bash scripts/mutation.sh liqpay        # payments/liqpay_client.py, ~15 мин
#   MUTATION_WORKERS=6 bash scripts/mutation.sh calculator   # pricing/calculator.py
# Переменные:
#   MUTATION_WORKERS=N      - N параллельных воркеров, каждый в своей копии репо (git worktree
#                             от HEAD: незакоммиченные правки туда не попадут). По умолчанию 1.
#   MUTATION_MAX_SURVIVAL=P - упасть, если выживших больше P %.
#   MUTATION_PORT_BASE=9800 - порты воркеров: база+1..база+N.
#
# cosmic-ray правит исходник на месте и откатывает после каждого мутанта, поэтому модуль
# должен быть без незакоммиченных правок, при обрыве он восстанавливается из git.
# Эквивалентные мутанты (не меняют поведение) помечаются в коде `# pragma: no mutate (почему)`.
# Отчёт: .mutation/<name>.html. Окружение - как у тестов (CLAUDE.md).
set -euo pipefail

name="${1:?Укажите модуль: имя конфига из mutation/ (calculator, security, liqpay, payments, access, deals, antispam, sso, callback, posting)}"
cfg="mutation/${name}.toml"
[ -f "$cfg" ] || { echo "Нет конфига $cfg" >&2; exit 2; }

# module-path - строка или список: все пути в кавычках из этой строки.
read -r -a modules <<< "$(grep '^module-path' "$cfg" | grep -o '"[^"]*"' | tr -d '"' | tr '\n' ' ')"
out="${MUTATION_DIR:-.mutation}"
db="${out}/${name}.sqlite"
workers="${MUTATION_WORKERS:-1}"
mkdir -p "$out"

if ! git diff --quiet -- "${modules[@]}" || ! git diff --cached --quiet -- "${modules[@]}"; then
    echo "В ${modules[*]} есть незакоммиченные правки: cosmic-ray мутирует файл на месте. Закоммитьте их." >&2
    exit 2
fi

export DEBUG="${DEBUG:-true}" SECRET_KEY="${SECRET_KEY:-mutation-testing-not-secret}"
export DATABASE_URL="" REDIS_URL="" TELEGRAM_BOT_TOKEN=""
# Windows: Django печатает по-русски в cp1251, а cosmic-ray читает вывод теста как UTF-8 и
# падает (мутант уходит в INCOMPETENT вместо KILLED).
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

worker_pids=()
# Копии воркеров - вне проекта: тесты, сканирующие репозиторий (test_bot_constructed_only_in_provider,
# шаблоны .env), иначе находят в них «лишние» файлы и роняют baseline.
wdir="$(mktemp -d "${TMPDIR:-/tmp}/afy-mutation-XXXXXX")"
cleanup() {
    for pid in "${worker_pids[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
    for i in $(seq 1 "$workers"); do
        [ -d "${wdir}/w${i}" ] && git worktree remove --force "${wdir}/w${i}" 2>/dev/null || true
    done
    git checkout -- "${modules[@]}"
    git worktree prune
    rm -rf "$wdir"
}
trap cleanup EXIT

# test-command с абсолютным путём к текущему python: на Windows Popen("python") находит
# системный интерпретатор, а не .venv.
py="$(python -c 'import sys; print(sys.executable.replace(chr(92), "/"))')"
run_cfg="${out}/${name}.toml"
sed "s|\"python manage.py|\"${py} manage.py|" "$cfg" > "$run_cfg"
# baseline (тесты на немутированном коде) - всегда локально, в этой папке.
base_cfg="${out}/${name}.base.toml"
cp "$run_cfg" "$base_cfg"

if [ "$workers" -gt 1 ]; then
    urls=""
    for i in $(seq 1 "$workers"); do
        port=$((${MUTATION_PORT_BASE:-9800} + i))
        git worktree add --force --detach "${wdir}/w${i}" HEAD > /dev/null
        (cd "${wdir}/w${i}" && exec cosmic-ray http-worker --port "$port") > "${out}/worker${i}.log" 2>&1 &
        worker_pids+=("$!")
        urls="${urls:+${urls}, }\"http://127.0.0.1:${port}\""
    done
    for i in $(seq 1 "$workers"); do
        for _ in $(seq 1 60); do
            curl -s -o /dev/null "http://127.0.0.1:$((${MUTATION_PORT_BASE:-9800} + i))/" && break
            sleep 1
        done
    done
    sed -i "s|^name = \"local\"|name = \"http\"\n\n[cosmic-ray.distributor.http]\nworker-urls = [${urls}]|" "$run_cfg"
fi

cosmic-ray init "$run_cfg" "$db" --force
cr-filter-operators "$db" "$run_cfg"
cr-filter-pragma "$db"
cosmic-ray baseline "$base_cfg"
cosmic-ray exec "$run_cfg" "$db"

cr-html "$db" > "${out}/${name}.html"
echo "HTML-отчёт: ${out}/${name}.html"

# cr-rate считает отфильтрованные (SKIPPED) мутанты выжившими, поэтому процент - свой.
python - "$db" "${MUTATION_MAX_SURVIVAL:-}" <<'EOF'
import sqlite3, sys

db, limit = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
counts = dict(con.execute(
    "SELECT COALESCE(test_outcome, worker_outcome), COUNT(*) FROM work_results GROUP BY 1"))
killed, survived = counts.get('KILLED', 0), counts.get('SURVIVED', 0)
incompetent, skipped = counts.get('INCOMPETENT', 0), counts.get('SKIPPED', 0)
tested = killed + survived + incompetent
rate = 100 * survived / tested if tested else 0.0
print(f'убито {killed}, выжило {survived}, incompetent {incompetent}, пропущено {skipped}; '
      f'выживших {rate:.1f}% из {tested}')
for path, row, op in con.execute(
        "SELECT s.module_path, s.start_pos_row, s.operator_name FROM mutation_specs s "
        "JOIN work_results w ON w.job_id = s.job_id WHERE w.test_outcome = 'SURVIVED' ORDER BY 2"):
    print(f'  выжил: {path}:{row} {op}')
if incompetent:
    sys.exit(f'{incompetent} мутантов INCOMPETENT: тест не запустился, разберите вывод в отчёте.')
if limit and rate > float(limit):
    sys.exit(f'Выживших {rate:.1f}% > порога {limit}%.')
EOF
