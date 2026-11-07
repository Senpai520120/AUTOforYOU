"""Лимит писем на один адрес (D4, задача 1.17).

Лимит по IP не защищает чужой ящик от атаки с пула адресов. Счётчик живёт в django.cache,
ключ - HMAC нормализованного адреса (как в lockout): в кэше и логах адреса нет. Слот занимается
независимо от того, есть ли аккаунт, поэтому по поведению нельзя узнать о его существовании.
"""
from django.conf import settings
from django.core.cache import cache

from . import lockout

SCOPE = 'password_reset_email'

_PERIODS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}


def _parse_rate(rate):
    num, period = rate.split('/')
    return int(num), _PERIODS[period[0]]


def consume_email_slot(email, kind='reset') -> bool:
    """True - письмо на этот адрес можно отправить; False - лимит исчерпан (письмо не слать).

    kind разводит счётчики по назначению ('reset' - сброс пароля, 'exists' - «вже є акаунт»):
    регистрации на чужой адрес не должны съедать лимит писем сброса. Лимит у обоих один.
    """
    limit, window = _parse_rate(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'][SCOPE])
    key = f'{SCOPE}:{kind}:{lockout._digest(email)}'
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:  # ключ истёк между add и incr
        cache.set(key, 1, timeout=window)
        count = 1
    return count <= limit
