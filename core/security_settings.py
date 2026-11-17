"""Заголовки безопасности и HTTPS-настройки Django (задача 7.1, 12-S2, 01-S18).

Чистая функция без обращений к os.environ и django.conf: settings.py передаёт ей окружение,
тесты - словарь. Режим TLS_MODE тот же, что в nginx (nginx/docker-entrypoint.d).
"""
from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured

TLS_MODES = ('off', 'selfsigned', 'letsencrypt', 'external')
DEFAULT_HSTS_MAX_AGE = 31_536_000

_TRUE = ('true', '1', 'yes')


def _flag(env: Mapping, name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or str(raw).strip() == '':
        return default
    return str(raw).strip().lower() in _TRUE


def _hsts_max_age(env: Mapping) -> int:
    raw = str(env.get('HSTS_MAX_AGE', '')).strip()
    if not raw:
        return DEFAULT_HSTS_MAX_AGE
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f'HSTS_MAX_AGE должен быть целым числом, получено {raw!r}') from exc
    if value < 0:
        raise ValueError('HSTS_MAX_AGE не может быть отрицательным')
    return value


def build_security_settings(env: Mapping, *, debug: bool = False, testing: bool = False,
                            auth_cookie_secure: bool = True) -> dict:
    """Настройки заголовков безопасности по окружению.

    В dev и в тест-раннере возвращает пустой словарь: там всё идёт по HTTP.
    TLS_MODE пустой = прежнее поведение (редирект включён, если не выключен явно);
    при DEBUG=false без TLS_MODE ничего не отключается молча.
    Явный SECURE_SSL_REDIRECT в окружении важнее режима (обратная совместимость с CI).
    HSTS preload и includeSubDomains - только по флагам, по умолчанию выключены (01-S18).
    """
    if debug or testing:
        return {}

    mode = str(env.get('TLS_MODE', '')).strip().lower()
    if mode and mode not in TLS_MODES:
        raise ValueError(f'TLS_MODE={mode!r} не поддерживается, допустимо: {", ".join(TLS_MODES)}')

    # Режимы selfsigned/letsencrypt: HTTP->HTTPS редирект делает nginx, external: балансировщик.
    # Django в них НЕ редиректит: SSR Next ходит в http://backend:8000 без X-Forwarded-Proto и
    # получил бы 301 на https://backend:8000 (страницы остались бы без данных). Пустой режим =
    # прежнее поведение (старый .env без TLS_MODE): редирект включён, если не выключен явно.
    redirect_default = mode == ''
    ssl_redirect = _flag(env, 'SECURE_SSL_REDIRECT', redirect_default)
    tls_front = mode in ('selfsigned', 'letsencrypt', 'external')
    # HSTS в Django дублирует nginx (тот скрывает заголовок апстрима и ставит свой): нужен для
    # check --deploy и прямого доступа к backend по https.
    hsts_seconds = _hsts_max_age(env) if (tls_front or (mode == '' and ssl_redirect)) else 0

    if (tls_front or ssl_redirect) and not auth_cookie_secure:
        # Флаг стенда без TLS (.env.e2e) не должен попасть на прод с HTTPS.
        raise ImproperlyConfigured('AUTH_COOKIE_SECURE=false допустим только при TLS_MODE=off.')

    return {
        'SECURE_SSL_REDIRECT': ssl_redirect,
        'SECURE_HSTS_SECONDS': hsts_seconds,
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': _flag(env, 'HSTS_INCLUDE_SUBDOMAINS', False),
        'SECURE_HSTS_PRELOAD': _flag(env, 'HSTS_PRELOAD', False),
        'SESSION_COOKIE_SECURE': True,
        'CSRF_COOKIE_SECURE': auth_cookie_secure,
        'SECURE_PROXY_SSL_HEADER': ('HTTP_X_FORWARDED_PROTO', 'https'),
        'X_FRAME_OPTIONS': 'DENY',
        'SECURE_CONTENT_TYPE_NOSNIFF': True,
        'SECURE_REFERRER_POLICY': 'strict-origin-when-cross-origin',
        # Редирект делает nginx/балансировщик: check --deploy не должен требовать его в Django.
        'SILENCED_SYSTEM_CHECKS': ['security.W008'] if (tls_front and not ssl_redirect) else [],
    }


def csrf_origins_from_site(domain: str, site_url: str, tls_mode: str) -> list[str]:
    """CSRF_TRUSTED_ORIGINS из DOMAIN/SITE_URL, если список не задан явно.

    Схема: https для всех режимов, кроме off (там http). Пустой DOMAIN - берём хост из SITE_URL.
    """
    from urllib.parse import urlsplit

    domain = (domain or '').strip()
    scheme = 'http' if (tls_mode or '').strip().lower() == 'off' else 'https'
    if not domain:
        parts = urlsplit(site_url or '')
        if not parts.hostname or parts.hostname == 'localhost':
            return []
        return [f'{parts.scheme}://{parts.netloc}']
    return [f'{scheme}://{domain}']
