from django.apps import AppConfig
from django.core.checks import Error, Warning, register

CLOUDFLARE_TEST_SECRETS = frozenset({
    '1x0000000000000000000000000000000AA',
    '2x0000000000000000000000000000000AA',
    '3x0000000000000000000000000000000AA',
})


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        register(check_lockout_cache)
        register(check_captcha_provider)


def check_lockout_cache(app_configs, **kwargs):
    """Без общего кэша (Redis) блокировка входа считается в каждом воркере отдельно."""
    from django.conf import settings
    from django.core.cache import caches
    from django.core.cache.backends.locmem import LocMemCache

    if not settings.DEBUG and isinstance(caches['default'], LocMemCache):
        return [Warning(
            'Кэш — LocMemCache: блокировка входа по аккаунту работает в пределах одного воркера.',
            hint='Задайте REDIS_URL.',
            id='users.W001',
        )]
    return []


def check_captcha_provider(app_configs, **kwargs):
    """CAPTCHA_PROVIDER=off допустим только при DEBUG=True и в тестах (задача 1.6)."""
    from django.conf import settings

    if settings.DEBUG or settings.IS_TESTING:
        return []
    if settings.CAPTCHA_PROVIDER == 'off':
        return [Error(
            'CAPTCHA_PROVIDER=off при DEBUG=False: регистрация и вход без защиты от ботов.',
            hint='Задайте CAPTCHA_PROVIDER=turnstile (или honeypot).',
            id='users.E001',
        )]
    secret = settings.TURNSTILE_SECRET_KEY
    if secret in CLOUDFLARE_TEST_SECRETS:
        return [Error(
            'TURNSTILE_SECRET_KEY - публичный тестовый ключ Cloudflare: капча пропускает всех.',
            hint='Возьмите секрет из Cloudflare Dashboard -> Turnstile.',
            id='users.E002',
        )]
    if not secret:
        return [Warning(
            'TURNSTILE_SECRET_KEY не задан: работает только honeypot, без Turnstile.',
            hint='Задайте TURNSTILE_SITE_KEY и TURNSTILE_SECRET_KEY.',
            id='users.W002',
        )]
    return []
