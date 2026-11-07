"""SECRET_KEY и защита от DEBUG на публичном хосте (задача 7.2, 01-S10, 01-C8).

Чистые функции без Django-настроек: settings.py вызывает их при импорте, тесты - напрямую
и через subprocess. Фиксированного ключа в репозитории нет.
"""
import logging
import secrets
import string
from collections.abc import Mapping
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

MIN_PROD_KEY_LENGTH = 50
# Маркеры ключей-заглушек из шаблонов .env (та же логика, что в deploy.sh).
PLACEHOLDER_MARKERS = ('REPLACE', 'local-docker-dev', 'django-insecure', 'not-for-production', 'e2e-only', 'your-')
SAFE_DEBUG_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0', 'backend', 'testserver'}
GENERATE_HINT = (
    'Сгенерировать: python -c "from django.core.management.utils import get_random_secret_key; '
    'print(get_random_secret_key())"'
)


def _truthy(value) -> bool:
    return str(value or '').lower() in ('true', '1', 'yes')


def _random_key() -> str:
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*(-_=+)'
    return ''.join(secrets.choice(alphabet) for _ in range(50))


def _dev_key(env: Mapping, base_dir) -> str:
    """Ключ разработчика: создаётся один раз в .dev_secret_key, чтобы сессии переживали перезапуск."""
    path = Path(env.get('DEV_SECRET_KEY_FILE', '') or Path(base_dir) / '.dev_secret_key')
    try:
        key = path.read_text(encoding='utf-8').strip()
        if key:
            return key
    except OSError:
        pass
    key = _random_key()
    try:
        path.write_text(key, encoding='utf-8')
        path.chmod(0o600)
    except OSError:
        # Директория только для чтения (контейнер): ключ живёт до перезапуска процесса.
        logger.warning('Не удалось сохранить %s: SECRET_KEY сгенерирован только в памяти', path.name)
    return key


def resolve_secret_key(env: Mapping, *, debug: bool, testing: bool, base_dir) -> str:
    key = env.get('SECRET_KEY', '')
    if testing and not key:
        return _random_key()  # случайный на прогон
    if not key:
        if debug:
            return _dev_key(env, base_dir)
        raise ImproperlyConfigured(f'SECRET_KEY не задан. На проде SECRET_KEY обязателен. {GENERATE_HINT}')
    if not debug and not testing:
        if len(key) < MIN_PROD_KEY_LENGTH or any(m.lower() in key.lower() for m in PLACEHOLDER_MARKERS):
            raise ImproperlyConfigured(
                f'SECRET_KEY похож на заглушку из шаблона или короче {MIN_PROD_KEY_LENGTH} символов. '
                f'{GENERATE_HINT}'
            )
    return key


def _url_hosts(value: str):
    from urllib.parse import urlsplit
    for item in (value or '').split(','):
        item = item.strip()
        if item:
            yield (urlsplit(item).hostname or '') if '://' in item else item


def check_debug_hosts(env: Mapping, *, debug: bool, allowed_hosts) -> None:
    """DEBUG=true с внешним хостом - ошибка старта (отключились бы все SECURE_*, видны трассировки).

    Кроме ALLOWED_HOSTS смотрим адреса сайта (SITE_URL, CSRF_TRUSTED_ORIGINS, CORS_ALLOWED_ORIGINS):
    с пустым ALLOWED_HOSTS дефолтные localhost-хосты иначе пропускали бы сервер с Host: localhost.
    """
    if not debug or _truthy(env.get('ALLOW_DEBUG_ON_PUBLIC_HOST')):
        return
    hosts = set(allowed_hosts)
    for name in ('SITE_URL', 'CSRF_TRUSTED_ORIGINS', 'CORS_ALLOWED_ORIGINS'):
        hosts.update(_url_hosts(env.get(name, '')))
    public = sorted(h for h in hosts if h and h.lstrip('.') not in SAFE_DEBUG_HOSTS)
    if public:
        raise ImproperlyConfigured(
            f'DEBUG=true при публичном хосте ({", ".join(public)}): на сервере это '
            'отключает защиту (HTTPS-заголовки, безопасные cookie) и показывает трассировки. '
            'Поставьте DEBUG=false в .env.'
        )
