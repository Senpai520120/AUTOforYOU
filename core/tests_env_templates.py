"""Полнота шаблонов .env и чек-листа (задача 7.7a, 12-C1, 12-C8, 12-C9).

Сканер читает исходники и собирает имена переменных окружения, которые читает код:
- Python (`os.environ.get`, `env.get`, `os.getenv`, `os.environ[...]`, `_positive_int_env`, `env_state`, `_flag(env, ...)`);
- `${VAR}` в docker-compose.yml и шаблонах nginx; `${VAR:-...}` в shell (deploy.sh, docker/, scripts/, entrypoint nginx);
- `process.env.X` во frontend/.
Каждое имя должно быть описано в шаблоне (в том числе закомментированной строкой `# KEY=`), иначе тест красный.
Исключения - только явные, с причиной; устаревшее исключение (имя в коде больше не встречается) тоже ошибка.
`cars/` и каталоги окружений не сканируются (решение владельца: cars только читать).
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core import launch

ROOT = Path(settings.BASE_DIR)
SKIP_DIRS = {
    '.venv', 'venv', 'node_modules', '.next', '.git', '.claude', 'cars', 'pgdata', 'backups', 'media',
    'private_media', 'test-results', 'staticfiles', '__pycache__', 'tests', 'docs',
}

PY_ENV_RE = re.compile(
    r"""(?:environ\.get|env\.get|environ\[|getenv|_positive_int_env|env_state|_flag\(\s*env)\s*[(,]?\s*\(?\s*"""
    r"""['"]([A-Z][A-Z0-9_]+)['"]"""
)
COMPOSE_VAR_RE = re.compile(r'\$\{([A-Z][A-Z0-9_]+)')
SHELL_DEFAULT_RE = re.compile(r'\$\{([A-Z][A-Z0-9_]+):?[-?=]')
NODE_ENV_RE = re.compile(r'process\.env\.([A-Z][A-Z0-9_]*[A-Z0-9])\b')
TEMPLATE_KEY_RE = re.compile(r'^#? ?([A-Z][A-Z0-9_]*)=\S*(?:[ \t]+#.*)?[ \t\r]*$', re.MULTILINE)
TEMPLATE_LINE_RE = re.compile(r'^(#? ?)([A-Z][A-Z0-9_]*)=(.*)$', re.MULTILINE)

# ─── Исключения: имя -> причина ──────────────────────────────────────────────

# Shell: это не переменные `.env`. Группы по причине; каждая группа - явный список.
_SHELL_LOCALS = 'локальная переменная shell-скрипта (не окружение)'
_SHELL_ARGS = 'параметр вызова скрипта из командной строки/CI, описан в DEPLOY_NOTES.md (не ключ .env)'
_CONTAINER_INTERNAL = 'путь/имя внутри контейнера, задаётся Dockerfile или docker-compose.yml, менять не нужно'
_NGINX_INTERNAL = 'внутренняя переменная entrypoint nginx (подстановка в шаблон), не настройка'
_SERVER_SETUP = 'параметр server-setup.sh на сервере до появления .env, описан в DEPLOY_NOTES.md'

SHELL_EXCLUDED = {}
for _names, _reason in (
    (('CURRENT', 'HEAD_SHA', 'LAST_DUMP', 'ID', 'UBUNTU_CODENAME', 'VERSION_CODENAME'), _SHELL_LOCALS),
    (('DEPLOY_ENV_FILE', 'DEPLOY_SMOKE_RETRIES', 'DEPLOY_SMOKE_SLEEP', 'DEPLOY_WAIT_TIMEOUT', 'EXPECTED_SHA',
      'DOCKER_DEFAULT_PLATFORM', 'COMPOSE_CMD', 'ENV_FILE', 'VERIFY_PG_IMAGE'), _SHELL_ARGS),
    (('DEPLOY_USER', 'FSTAB_FILE', 'SWAP_FILE', 'SWAP_SIZE_GB', 'SWAP_SWAPPINESS', 'SYSCTL_FILE', 'SSH_PORT',
      'SERVER_SETUP_SKIP_APT'), _SERVER_SETUP),
    (('BACKUP_DIR_IN_CONTAINER', 'BACKUP_MEDIA_DIR', 'BACKUP_PRIVATE_MEDIA_DIR', 'BACKUP_ROTATE_SCRIPT',
      'PGHOST', 'PGDATABASE', 'PORT', 'TZ'), _CONTAINER_INTERNAL),
    (('INTERNAL_HOST', 'NGINX_CONF_OUT', 'NGINX_GEN', 'NGINX_SRC', 'SERVER_NAMES', 'SSL_CERT_DIR', 'CSP_VALUE',
      'CSP_HEADER_NAME'), _NGINX_INTERNAL),
):
    for _name in _names:
        SHELL_EXCLUDED[_name] = _reason

# Frontend: не настройки сайта.
FRONTEND_EXCLUDED = {
    'NODE_ENV': 'выставляет сам Node/Next (development/production/test)',
    'CI': 'выставляет CI-система (GitHub Actions)',
    'NEXT_PHASE': 'выставляет сам Next во время сборки',
}

# Не нужны в dev-шаблоне (.env.docker.example): только прод-значения. Пока пусто - все переменные есть в обоих.
DOCKER_TEMPLATE_EXCLUDED = {}


def _iter_files(patterns):
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            if path.is_file() and not (set(path.relative_to(ROOT).parts) & SKIP_DIRS):
                yield path


def _read(path):
    return path.read_text(encoding='utf-8', errors='ignore')


def _py_files():
    for path in ROOT.rglob('*.py'):
        rel = path.relative_to(ROOT)
        if set(rel.parts) & SKIP_DIRS:
            continue
        if path.name.startswith(('tests', 'test_')) or path.name == 'conftest.py':
            continue
        yield path


def scan_backend_names():
    names = {}
    for path in _py_files():
        for match in PY_ENV_RE.finditer(_read(path)):
            names.setdefault(match.group(1), set()).add(path.relative_to(ROOT).as_posix())
    for path in _iter_files(['docker-compose.yml', 'nginx/templates/*', 'nginx/*.conf']):
        for match in COMPOSE_VAR_RE.finditer(_read(path)):
            names.setdefault(match.group(1), set()).add(path.relative_to(ROOT).as_posix())
    shell = ['deploy.sh', 'docker/*.sh', 'docker/backup/*.sh', 'scripts/*.sh', 'nginx/docker-entrypoint.d/*.sh']
    for path in _iter_files(shell):
        for match in SHELL_DEFAULT_RE.finditer(_read(path)):
            names.setdefault(match.group(1), set()).add(path.relative_to(ROOT).as_posix())
    return names


def scan_frontend_names():
    names = {}
    for pattern in ('frontend/**/*.ts', 'frontend/**/*.tsx', 'frontend/**/*.js', 'frontend/**/*.mjs'):
        for path in ROOT.glob(pattern):
            if set(path.relative_to(ROOT).parts) & SKIP_DIRS:
                continue
            for match in NODE_ENV_RE.finditer(_read(path)):
                names.setdefault(match.group(1), set()).add(path.relative_to(ROOT).as_posix())
    return names


def template_keys(path):
    """Имена переменных, определённых строкой `KEY=значение` или закомментированной `# KEY=значение`."""
    return set(TEMPLATE_KEY_RE.findall(_read(path)))


def template_values(path):
    """Живые (не закомментированные) строки: имя -> значение."""
    return {m.group(2): m.group(3).strip() for m in TEMPLATE_LINE_RE.finditer(_read(path)) if not m.group(1).startswith('#')}


ENV_EXAMPLE = ROOT / '.env.example'
ENV_DOCKER = ROOT / '.env.docker.example'
FRONTEND_ENV = ROOT / 'frontend' / '.env.example'
CHECKLIST = ROOT / 'docs' / 'LAUNCH_CHECKLIST.md'


class ScannerSanityTests(SimpleTestCase):
    """Сканер не должен молча находить «ничего»: проверяем на известных именах."""

    def test_backend_scanner_finds_known_names_from_each_source(self):
        names = scan_backend_names()
        self.assertEqual(names['ANTISPAM_MODE'], {'core/settings.py'})
        self.assertIn('S3_BUCKET_NAME', names)  # env.get в core/storage_settings.py
        self.assertIn('HSTS_MAX_AGE', names)  # _flag/env.get в core/security_settings.py
        self.assertIn('MEM_LIMIT_BACKEND', names)  # ${VAR} в docker-compose.yml
        self.assertIn('GUNICORN_WORKERS', names)  # ${VAR:-} в docker/entrypoint.sh
        self.assertIn('CSP_REPORT_ONLY', names)  # nginx entrypoint
        self.assertGreater(len(names), 150)

    def test_frontend_scanner_finds_known_names(self):
        names = scan_frontend_names()
        self.assertIn('NEXT_PUBLIC_API_URL', names)
        self.assertIn('INTERNAL_API_URL', names)
        self.assertIn('E2E_BASE_URL', names)
        self.assertNotIn('NEXT_PUBLIC_', names)  # префикс из комментария - не переменная

    def test_scanner_skips_legacy_cars_and_virtualenv(self):
        for names in (scan_backend_names(), scan_frontend_names()):
            for files in names.values():
                for file in files:
                    self.assertFalse(file.startswith(('cars', '.venv', 'venv', 'node_modules')), file)

    def test_template_key_parser_understands_commented_keys_and_ignores_prose(self):
        text = '# KEY_A=1\nKEY_B=\n#KEY_C=x\n# Это пояснение: KEY_D=2 в тексте\n# DEBUG=true с публичным хостом\nKEY_E=a  # c\n'
        found = set(TEMPLATE_KEY_RE.findall(text))
        self.assertEqual(found, {'KEY_A', 'KEY_B', 'KEY_C', 'KEY_E'})


class BackendTemplatesTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.names = scan_backend_names()
        cls.code_names = set(cls.names) - set(SHELL_EXCLUDED)

    def test_env_example_has_every_variable_read_by_code(self):
        missing = sorted(self.code_names - template_keys(ENV_EXAMPLE))
        self.assertEqual(missing, [], f'Нет в .env.example (добавьте строку `# KEY=` с пояснением): {missing}')

    def test_env_docker_example_has_every_variable_read_by_code(self):
        missing = sorted(self.code_names - template_keys(ENV_DOCKER) - set(DOCKER_TEMPLATE_EXCLUDED))
        self.assertEqual(missing, [], f'Нет в .env.docker.example: {missing}')

    def test_exclusions_are_not_stale(self):
        stale = sorted(set(SHELL_EXCLUDED) - set(self.names))
        self.assertEqual(stale, [], f'Исключение больше не встречается в коде, удалите его: {stale}')
        stale_docker = sorted(set(DOCKER_TEMPLATE_EXCLUDED) - set(self.names))
        self.assertEqual(stale_docker, [])

    def test_exclusions_have_reasons(self):
        for name, reason in {**SHELL_EXCLUDED, **FRONTEND_EXCLUDED, **DOCKER_TEMPLATE_EXCLUDED}.items():
            self.assertGreater(len(reason), 10, name)

    def test_excluded_names_are_not_documented_as_env_keys(self):
        # Исключённое - не ключ .env; если оно попало в шаблон, исключение лишнее.
        for name in SHELL_EXCLUDED:
            self.assertNotIn(name, template_keys(ENV_EXAMPLE), name)

    def test_removing_a_line_from_template_is_detected(self):
        # Самопроверка механизма: без строки ANTISPAM_MODE шаблон не проходит сравнение.
        text = '\n'.join(line for line in _read(ENV_EXAMPLE).splitlines() if not line.lstrip('# ').startswith('ANTISPAM_MODE='))
        self.assertNotIn('ANTISPAM_MODE', set(TEMPLATE_KEY_RE.findall(text)))
        self.assertIn('ANTISPAM_MODE', template_keys(ENV_EXAMPLE))

    def test_demo_mode_variable_is_gone(self):
        # 12-C2: NEXT_PUBLIC_DEMO_MODE закрыт задачей 2.6 (демо-пометка идёт «по данным»), переменной нет нигде.
        self.assertNotIn('NEXT_PUBLIC_DEMO_MODE', self.names)
        self.assertNotIn('NEXT_PUBLIC_DEMO_MODE', scan_frontend_names())
        for path in (ENV_EXAMPLE, ENV_DOCKER, FRONTEND_ENV):
            self.assertNotIn('DEMO_MODE', _read(path), path.name)

    def test_required_launch_vars_are_in_prod_template(self):
        required = set(launch.required_var_names())
        self.assertEqual(sorted(required - template_keys(ENV_EXAMPLE)), [])

    def test_required_launch_vars_are_in_checklist(self):
        text = _read(CHECKLIST)
        missing = sorted(n for n in launch.required_var_names() if n not in text)
        self.assertEqual(missing, [], f'Обязательные переменные без описания в LAUNCH_CHECKLIST: {missing}')

    def test_all_template_variables_are_in_checklist_or_documented_by_group(self):
        # Каждая переменная прод-шаблона должна упоминаться в чек-листе (таблицы раздела 2).
        text = _read(CHECKLIST)
        missing = sorted(n for n in template_keys(ENV_EXAMPLE) if n not in text)
        self.assertEqual(missing, [], f'Переменные из .env.example, которых нет в docs/LAUNCH_CHECKLIST.md: {missing}')


class FrontendTemplateTests(SimpleTestCase):
    def test_frontend_example_has_every_process_env(self):
        names = set(scan_frontend_names()) - set(FRONTEND_EXCLUDED)
        missing = sorted(names - template_keys(FRONTEND_ENV))
        self.assertEqual(missing, [], f'Нет во frontend/.env.example: {missing}')

    def test_frontend_exclusions_not_stale(self):
        stale = sorted(set(FRONTEND_EXCLUDED) - set(scan_frontend_names()))
        self.assertEqual(stale, [])

    def test_frontend_example_is_not_ignored_by_gitignore_rules(self):
        self.assertIn('!.env.example', _read(ROOT / 'frontend' / '.gitignore'))


class TemplateValuesTests(SimpleTestCase):
    SECRET_LIKE = (
        ('telegram bot token', re.compile(r'\d{8,10}:[A-Za-z0-9_-]{35}')),
        ('sk_live', re.compile(r'sk_(live|test)_[A-Za-z0-9]+')),
        ('private key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
        ('long token', re.compile(r'(?<![A-Za-z0-9_\-+=])[A-Za-z0-9_\-+=]{32,}(?![A-Za-z0-9_\-+=])')),
    )
    # Публичные тестовые ключи Cloudflare Turnstile (документация Cloudflare): всегда пропускают, не секреты.
    PUBLIC_TEST_VALUE = re.compile(r'^[123]x0+[A-Z]*$')

    def assertNoSecrets(self, path):
        for match in TEMPLATE_LINE_RE.finditer(_read(path)):
            value = match.group(3).split(' #')[0].strip().strip('"\'')
            if self.PUBLIC_TEST_VALUE.match(value):
                continue
            for label, pattern in self.SECRET_LIKE:
                self.assertIsNone(pattern.search(value), f'{path.name}: {match.group(2)} похоже на секрет ({label})')

    def test_templates_have_no_secret_like_values(self):
        for path in (ENV_EXAMPLE, ENV_DOCKER, FRONTEND_ENV):
            with self.subTest(path=path.name):
                self.assertNoSecrets(path)

    def test_secret_detector_catches_known_bad_values(self):
        # Мутационная самопроверка регулярок: плохие значения распознаются.
        bad = ['123456789:' + 'A' * 35, 'sk_' + 'live_abcdef123456', '-----BEGIN RSA PRIVATE KEY-----', 'a' * 40]
        for value in bad:
            hits = [label for label, p in self.SECRET_LIKE if p.search(value)]
            self.assertTrue(hits, value)
        for value in ('your-django-secret-key-here', 'https://yourdomain.com', 'redis://:your-strong-redis-password@redis:6379/0'):
            self.assertFalse([1 for _l, p in self.SECRET_LIKE if p.search(value)], value)

    def test_prod_template_values(self):
        values = template_values(ENV_EXAMPLE)
        for name, expected in launch.PROD_TEMPLATE_VALUES.items():
            with self.subTest(name=name):
                self.assertIn(name, values, f'{name} должен быть заданной (не закомментированной) строкой в .env.example')
                self.assertEqual(values[name], expected)

    def test_prod_template_turnstile_secret_present_and_empty(self):
        self.assertEqual(template_values(ENV_EXAMPLE)['TURNSTILE_SECRET_KEY'], '')

    def test_dev_template_values(self):
        values = template_values(ENV_DOCKER)
        for name, expected in launch.DEV_TEMPLATE_VALUES.items():
            with self.subTest(name=name):
                self.assertEqual(values.get(name), expected)

    def test_dev_template_marks_dev_values(self):
        # 12-C8: в dev-шаблоне сказано, что значения только для разработки.
        head = '\n'.join(_read(ENV_DOCKER).splitlines()[:14])
        self.assertIn('ЛОКАЛЬНИЙ (dev)', head)


class ChecklistDocumentTests(SimpleTestCase):
    # Путь в обратных кавычках вида `dir/file.ext`.
    PATH_RE = re.compile(r'`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.[A-Za-z0-9]{1,6})`')
    # Не файлы репозитория: пути внутри контейнера/на сервере и адреса.
    NOT_REPO_PATHS = ('etc/', 'var/', 'usr/', 'opt/', 'tmp/', 'app/', 'root/', 'home/')
    # Файлы, которых нет в репозитории по замыслу: создаются на сервере; скрипт-создатель обязан существовать.
    GENERATED = {'nginx/cloudflare-ips.conf': 'scripts/update-cloudflare-ips.sh'}
    # Локальные файлы вне git (личные настройки и неотслеживаемый аудит владельца): в CI их нет.
    LOCAL_ONLY = {'.claude/settings.local.json', 'docs/audit/SECURITY_AUDIT_2026-10-25.md'}

    def paths(self):
        found = set()
        for raw in self.PATH_RE.findall(_read(CHECKLIST)):
            if raw.startswith(self.NOT_REPO_PATHS) or raw.startswith(('http', 'www.')):
                continue
            found.add(raw)
        return sorted(found)

    def test_every_path_in_checklist_exists(self):
        paths = self.paths()
        self.assertGreater(len(paths), 10)  # регулярка действительно что-то находит
        missing = [p for p in paths if p not in self.LOCAL_ONLY and not (ROOT / p).exists() and not (
            p in self.GENERATED and (ROOT / self.GENERATED[p]).exists())]
        self.assertEqual(missing, [], f'В docs/LAUNCH_CHECKLIST.md пути к несуществующим файлам: {missing}')

    def test_path_regex_catches_a_deleted_file_reference(self):
        found = self.PATH_RE.findall('см. `scripts/deleted-long-ago.sh` и `.env.example`')
        self.assertEqual(found, ['scripts/deleted-long-ago.sh'])
        self.assertFalse((ROOT / 'scripts/deleted-long-ago.sh').exists())

    def test_checklist_has_no_real_secrets(self):
        text = _read(CHECKLIST)
        for label, pattern in TemplateValuesTests.SECRET_LIKE[:3]:
            self.assertIsNone(pattern.search(text), label)

    def test_checklist_has_lawyer_and_accountant_sections(self):
        text = _read(CHECKLIST)
        self.assertRegex(text, r'(?m)^#{2,4} .*Вопросы юристу')
        self.assertRegex(text, r'(?m)^#{2,4} .*Вопросы бухгалтеру')

    def test_checklist_mentions_uptime_monitor_for_healthz(self):
        text = _read(CHECKLIST)
        self.assertIn('healthz', text)
        self.assertIn('uptime', text.lower())

    def test_checklist_mentions_launch_check_and_check_memory(self):
        text = _read(CHECKLIST)
        self.assertIn('launch_check', text)
        self.assertIn('check-memory.sh', text)
