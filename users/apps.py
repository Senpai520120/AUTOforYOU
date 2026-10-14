from django.apps import AppConfig
from django.core.checks import Warning, register


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        register(check_lockout_cache)


def check_lockout_cache(app_configs, **kwargs):
    """Без общего кэша (Redis) блокировка входа считается в каждом воркере отдельно."""
    from django.conf import settings
    from django.core.cache.backends.locmem import LocMemCache
    from django.core.cache import caches

    if not settings.DEBUG and isinstance(caches['default'], LocMemCache):
        return [Warning(
            'Кэш — LocMemCache: блокировка входа по аккаунту работает в пределах одного воркера.',
            hint='Задайте REDIS_URL.',
            id='users.W001',
        )]
    return []
