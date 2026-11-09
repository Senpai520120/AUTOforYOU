"""Лимиты показа телефона (задача 4.5a, 05-S6, F3.2, Н-33).

- ``ContactDailyThrottle`` - суточный лимит на аккаунт вдобавок к почасовому ``contact``.
- ``GuestContactThrottle`` - суточный лимит показов гостю. Ключ кэша - HMAC-SHA256(PHONE_LOG_IP_SALT, ip),
  поэтому IP нет ни в Redis, ни в БД, ни в логах. IP берётся как в остальных лимитах DRF
  (``get_ident`` с ``NUM_PROXIES``): подмена X-Forwarded-For при верном NUM_PROXIES лимит не обходит.
  Слот резервируется атомарно (``cache.add`` + ``incr``) до показа и возвращается (``release``), если
  показ не состоялся (капча, 404): параллельные запросы не проходят «одним слотом» (ревью 4.5a),
  а отказ капчи лимит гостя не расходует. Окно фиксированное: сутки от первого показа.
- ``GuestAnonThrottle`` - общий лимит анонимных запросов к этому эндпоинту (перебор капчи) по тому же
  хэшу, а не по IP в открытом виде.
"""
import hashlib
import hmac

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle

DAILY_LIMIT_MESSAGE = 'Ліміт переглядів телефонів на сьогодні вичерпано'


def ip_hash(ip: str) -> str:
    """64 hex-символа; пустая соль - пустая строка (гостевой показ тогда закрыт, 503)."""
    salt = settings.PHONE_LOG_IP_SALT
    if not salt or not ip:
        return ''
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()


class _ListingCreateThrottle(UserRateThrottle):
    """8.5 (B7.2): только POST создания объявления; GET каталога и staff (засев) не ограничиваются."""
    message = 'Забагато нових оголошень. Спробуйте пізніше'

    def allow_request(self, request, view):
        user = getattr(request, 'user', None)
        if request.method != 'POST' or (user and user.is_authenticated and (user.is_staff or user.is_admin_role)):
            return True
        return super().allow_request(request, view)


class ListingCreateThrottle(_ListingCreateThrottle):
    scope = 'listing_create'


class ListingCreateDailyThrottle(_ListingCreateThrottle):
    scope = 'listing_create_daily'


class ContactDailyThrottle(UserRateThrottle):
    scope = 'contact_daily'
    message = DAILY_LIMIT_MESSAGE


class GuestAnonThrottle(AnonRateThrottle):
    """anon-лимит гостевого POST /contact/ с ключом по HMAC IP (без соли эндпоинт отвечает 503 раньше)."""

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        digest = ip_hash(self.get_ident(request))
        if not digest:
            return None
        return self.cache_format % {'scope': 'contact_guest_anon', 'ident': digest}


class GuestContactThrottle(SimpleRateThrottle):
    scope = 'contact_guest'
    message = DAILY_LIMIT_MESSAGE

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            return None
        digest = ip_hash(self.get_ident(request))
        if not digest:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': digest}

    def allow_request(self, request, view):
        """Атомарно занять слот; True - можно показывать. Не показали - вызвать ``release()``."""
        self.key = None
        if self.rate is None:
            return True
        key = self.get_cache_key(request, view)
        if key is None:
            return True
        self.cache.add(key, 0, timeout=self.duration)
        try:
            count = self.cache.incr(key)
        except ValueError:  # ключ истёк между add и incr
            self.cache.set(key, 1, timeout=self.duration)
            count = 1
        if count > self.num_requests:
            self._safe_decr(key)
            return False
        self.key = key
        return True

    def release(self):
        """Вернуть слот, если показ не состоялся (отказ капчи, 404)."""
        if self.key is not None:
            self._safe_decr(self.key)
            self.key = None

    def _safe_decr(self, key):
        try:
            self.cache.decr(key)
        except ValueError:
            pass

    def wait(self):
        return self.duration
