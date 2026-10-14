"""Единое место параметров auth-cookie (задача 1.3).

access уходит на весь сайт (Path=/), refresh — только на эндпоинты auth
(refresh и logout), чтобы не светиться в каждом запросе. Следствие для 1.4:
proxy.ts Next не видит refresh-cookie.

Метка сессии `has_session=1` (задача 1.4) — не httpOnly и без токена: фронт по ней
понимает, есть ли смысл звать profile/refresh. Без неё гость на каждой загрузке
страницы делал бы два лишних запроса под анонимный лимит.
"""
from django.conf import settings


def _common():
    return {
        'secure': settings.AUTH_COOKIE_SECURE,
        'httponly': True,
        'samesite': settings.AUTH_COOKIE_SAMESITE,
        'domain': settings.AUTH_COOKIE_DOMAIN,
    }


def _lifetime_seconds(key):
    return int(settings.SIMPLE_JWT[key].total_seconds())


def set_auth_cookies(response, access, refresh=None):
    response.set_cookie(
        settings.AUTH_COOKIE_ACCESS_NAME, str(access),
        max_age=_lifetime_seconds('ACCESS_TOKEN_LIFETIME'), path='/', **_common(),
    )
    if refresh is not None:
        response.set_cookie(
            settings.AUTH_COOKIE_REFRESH_NAME, str(refresh),
            max_age=_lifetime_seconds('REFRESH_TOKEN_LIFETIME'),
            path=settings.AUTH_COOKIE_REFRESH_PATH, **_common(),
        )
        response.set_cookie(
            settings.AUTH_COOKIE_HINT_NAME, '1',
            max_age=_lifetime_seconds('REFRESH_TOKEN_LIFETIME'), path='/',
            **{**_common(), 'httponly': False},
        )
    return response


def clear_auth_cookies(response):
    # delete_cookie ставит Max-Age=0; path и domain должны совпасть с set_cookie.
    common = _common()
    response.delete_cookie(
        settings.AUTH_COOKIE_ACCESS_NAME, path='/',
        domain=common['domain'], samesite=common['samesite'],
    )
    response.delete_cookie(
        settings.AUTH_COOKIE_REFRESH_NAME, path=settings.AUTH_COOKIE_REFRESH_PATH,
        domain=common['domain'], samesite=common['samesite'],
    )
    response.delete_cookie(
        settings.AUTH_COOKIE_HINT_NAME, path='/',
        domain=common['domain'], samesite=common['samesite'],
    )
    return response
