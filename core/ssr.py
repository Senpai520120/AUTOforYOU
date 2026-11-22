"""Доверенный SSR-запрос Next (задача 12.4) и его троттл.

SSR фронта ходит в backend:8000 в обход nginx и без X-Forwarded-For, поэтому DRF видит REMOTE_ADDR = IP
контейнера фронта, и все посетители делили бы один счётчик `anon`. Фронт добавляет заголовки:
  X-SSR-Key        - общий секрет (SSR_INTERNAL_KEY, >= 32 символов), только server-side;
  X-SSR-Client-IP  - реальный IP посетителя (его ставит nginx в x-real-ip).

Запрос «доверенный SSR» только если ключ совпал И нет X-Forwarded-For: nginx ставит XFF всегда, поэтому запрос
снаружи доверенным стать не может даже с утёкшим ключом. Для недоверенного X-SSR-* ничего не меняют.
"""
import hmac
import ipaddress

from django.conf import settings
from django.core.checks import Warning as CheckWarning
from rest_framework.throttling import AnonRateThrottle

MIN_KEY_LENGTH = 32


def ssr_key_configured() -> bool:
    key = getattr(settings, 'SSR_INTERNAL_KEY', '') or ''
    return len(key) >= MIN_KEY_LENGTH


def _is_trusted_ssr(meta) -> bool:
    if not ssr_key_configured() or meta.get('HTTP_X_FORWARDED_FOR'):
        return False
    given = meta.get('HTTP_X_SSR_KEY', '')
    if not given:
        return False
    return hmac.compare_digest(given.encode(), settings.SSR_INTERNAL_KEY.encode())


def normalize_visitor_ip(raw: str) -> str:
    """IP посетителя для бакета троттла. ValueError - невалидный.

    IPv4-mapped IPv6 (::ffff:1.2.3.4) -> IPv4; IPv6 -> сеть /64 (иначе клиент с /64 даёт себе 2^64 бакетов);
    адрес с %scope - невалидный. REMOTE_ADDR подменяется строкой сети ('2001:db8:1:2::'): get_ident, аудит
    (HMAC от строки) и блокировка входа лишь хэшируют/используют её как ключ, формат им не важен.
    """
    ip = ipaddress.ip_address(raw)
    if ip.version == 6:
        if getattr(ip, 'scope_id', None):
            raise ValueError('scope id')
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f'{ip}/64', strict=False).network_address)
    return str(ip)


def check_ssr_key(app_configs, **kwargs):
    """За прокси (NUM_PROXIES>=1) без ключа SSR Next делит один anon-лимит между всеми посетителями."""
    if settings.IS_TESTING or settings.NUM_PROXIES_COUNT < 1 or ssr_key_configured():
        return []
    return [CheckWarning(
        'NUM_PROXIES>=1, но SSR_INTERNAL_KEY не задан или короче 32 символов: SSR-запросы Next делят один anon-лимит.',
        hint='python -c "import secrets;print(secrets.token_urlsafe(48))" -> SSR_INTERNAL_KEY в .env (задача 12.4).',
        id='core.W001',
    )]


class SsrTrustMiddleware:
    """Доверенному SSR подставляет IP посетителя в REMOTE_ADDR и ставит request.ssr_trusted = True.

    Стоит до любого кода, читающего REMOTE_ADDR (DRF get_ident, логи, аудит).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.ssr_trusted = False
        request.ssr_visitor_ip = False
        if _is_trusted_ssr(request.META):
            request.ssr_trusted = True
            raw_ip = request.META.get('HTTP_X_SSR_CLIENT_IP', '').strip()
            try:
                request.META['REMOTE_ADDR'] = normalize_visitor_ip(raw_ip)
                request.ssr_visitor_ip = True
            except ValueError:
                pass  # невалидный IP игнорируется: бакет остаётся по REMOTE_ADDR фронта
        return self.get_response(request)


class SsrAwareAnonThrottle(AnonRateThrottle):
    """Анонимы: обычный scope `anon`.

    Доверенный SSR с валидным IP посетителя - scope `ssr` (бакет по посетителю, THROTTLE_SSR_RATE).
    Доверенный SSR без IP (кэшируемые запросы Next несут только ключ) - scope `ssr_shared`: общий бакет по IP
    фронта с высоким лимитом (THROTTLE_SSR_SHARED_RATE), чтобы краулер не выбил его и не отнял у людей.
    """

    def allow_request(self, request, view):
        if getattr(request, 'ssr_trusted', False):
            self.scope = 'ssr' if getattr(request, 'ssr_visitor_ip', False) else 'ssr_shared'
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)
