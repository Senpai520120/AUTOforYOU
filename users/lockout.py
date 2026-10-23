"""Временная блокировка входа по аккаунту (01-S2).

Всё в django.cache, без БД. Ключ — sha256 нормализованного email, счётчик общий для всех IP.
Работает одинаково для существующих и несуществующих адресов (нет перебора адресов).
В лог попадают только хэш (префикс) и IP, никогда не email.
"""
import hashlib
import hmac
import logging
import time
import unicodedata

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def _digest(email):
    # NFKC как у UsernameField админки: полноширинные варианты адреса дают один счётчик.
    # HMAC с SECRET_KEY: хэш из лога/кэша не сопоставить со словарём адресов.
    normalized = unicodedata.normalize('NFKC', email or '').strip().casefold()
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'), normalized.encode('utf-8'), hashlib.sha256,
    ).hexdigest()


def _fail_key(email):
    return f'login-fail:{_digest(email)}'


def _lock_key(email):
    return f'login-lock:{_digest(email)}'


def failure_count(email):
    """Сколько неудачных входов в текущем окне (для порога капчи, задача 1.6)."""
    return cache.get(_fail_key(email), 0)


def is_locked(email):
    """Секунд до разблокировки или None, если аккаунт не заблокирован."""
    until = cache.get(_lock_key(email))
    if until is None:
        return None
    remaining = int(until - time.time())
    return remaining if remaining > 0 else None


def reserve_attempt(email, ip):
    """Занять попытку входа ДО проверки пароля (иначе параллельные запросы обходят порог).

    Возвращает (count, retry_after). retry_after не None — попытка сверх лимита: аккаунт
    заблокирован, пароль проверять нельзя. Успешный вход вызывает reset().
    """
    window = settings.LOGIN_FAILURE_WINDOW_MINUTES * 60
    key = _fail_key(email)
    # add + incr: атомарно на Redis, без гонки «прочитал — записал».
    cache.add(key, 0, timeout=window)
    try:
        count = cache.incr(key)
    except ValueError:  # ключ истёк между add и incr
        cache.set(key, 1, timeout=window)
        count = 1
    if count <= settings.LOGIN_MAX_FAILURES:
        return count, None
    lockout = settings.LOGIN_LOCKOUT_MINUTES * 60
    cache.set(_lock_key(email), time.time() + lockout, timeout=lockout)
    cache.delete(key)
    logger.warning('login lockout: account=%s ip=%s', _digest(email)[:12], ip)
    return count, lockout


def reset(email):
    cache.delete_many([_fail_key(email), _lock_key(email)])
