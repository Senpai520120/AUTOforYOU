"""Middleware проекта: ModuleFlagMiddleware (заморозка модулей, задача 2.8) и C2CFlagMiddleware (раздел C2C, 6.7)."""
import re

from django.http import JsonResponse

from core.c2c import c2c_enabled, c2c_public_posting_enabled
from core.modules import module_enabled

# (regex пути, модуль). Порядок не важен: срабатывает первое совпадение.
# Это единственный список замороженных префиксов; тест core/tests_module_flags.py сверяет его с urlconf.
FROZEN_ROUTES = (
    (re.compile(r'^/api/v1/listings/'), 'lots'),
    (re.compile(r'^/api/v1/lots/'), 'lots'),
    # Только список и карточка по pk. VIN-эндпоинты (decode, report, registry) модулю лотов не принадлежат.
    (re.compile(r'^/api/v1/vehicles/(\d+/)?$'), 'lots'),
    (re.compile(r'^/api/v1/b2b/'), 'b2b'),
    (re.compile(r'^/api/v1/dealers/'), 'dealers'),
    (re.compile(r'^/api/v1/shipments/'), 'shipments'),
    (re.compile(r'^/api/v1/auth/me/shipments/'), 'shipments'),
)


def frozen_module_for(path: str):
    for pattern, module in FROZEN_ROUTES:
        if pattern.match(path):
            return module
    return None


class ModuleFlagMiddleware:
    """Выключенный модуль отвечает 404 на любой метод и любому пользователю (включая staff).

    Стоит до аутентификации и не ходит в БД. Админка Django (/admin/) не затрагивается.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        module = frozen_module_for(request.path_info)
        if module is not None and not module_enabled(module):
            return JsonResponse({'detail': 'Not found.'}, status=404)
        return self.get_response(request)


# ─── Раздел «Оголошення по Україні» (задача 6.7) ──────────────────────────────
# Единственные списки C2C-префиксов; тест core/tests_c2c_flag.py сверяет их с urlconf.
C2C_PREFIXES = (
    '/api/v1/local/',
    '/api/v1/deals/',
    '/api/v1/messages/',
    '/api/v1/saved-searches/',
    '/api/v1/payments/',
)
# Дополнительно закрыто в режиме «засев» (C2C включён, подача для всех закрыта): их фичи чинятся на ВОЛНЕ-2.
C2C_SEEDING_CLOSED_PREFIXES = (
    '/api/v1/messages/',
    '/api/v1/deals/',
    '/api/v1/saved-searches/',
)
C2C_SEEDING_CLOSED_PATTERNS = (
    re.compile(r'^/api/v1/local/listings/[^/]+/promote/?$'),
)
# Внутри C2C-префиксов, но не закрывается ни флагом, ни режимом (Q17): callback LiqPay всегда принимается,
# подпись проверяет view; закрывается только создание оплат.
C2C_OPEN_PATHS = (
    '/api/v1/payments/liqpay/callback/',
)
# Смешанные API: лоты и C2C в одних эндпоинтах, закрываются в сервисе по типу связи, а не префиксом.
MIXED_API_PREFIXES = (
    '/api/v1/favorites/',
    '/api/v1/reports/',
)

_MULTI_SLASH = re.compile(r'/{2,}')


def _normalize(path: str) -> str:
    """Нижний регистр и схлопнутые слэши: обход вида `/API/v1//local/` не должен проскочить мимо префикса."""
    return _MULTI_SLASH.sub('/', path).lower()


def _under(path: str, prefix: str) -> bool:
    """Путь внутри префикса; сам префикс без завершающего слэша тоже считается."""
    return path.startswith(prefix) or path + '/' == prefix


def c2c_closed_reason(path: str):
    """'section' (раздел выключен), 'seeding' (режим «засев») или None, если C2C-флаги путь не закрывают."""
    path = _normalize(path)
    if path in C2C_OPEN_PATHS:
        return None
    if not c2c_enabled():
        return 'section' if any(_under(path, p) for p in C2C_PREFIXES) else None
    if not c2c_public_posting_enabled():
        if any(_under(path, p) for p in C2C_SEEDING_CLOSED_PREFIXES) or any(
            pat.match(path) for pat in C2C_SEEDING_CLOSED_PATTERNS
        ):
            return 'seeding'
    return None


class C2CFlagMiddleware:
    """Раздел C2C: выключенный раздел или режим «засев» отвечают 404 на любой метод любому пользователю (и staff).

    Стоит после CommonMiddleware и до аутентификации, не ходит в БД. Админка Django (/admin/) не затрагивается.

    Что закрыто чем (C2C_ENABLED=false / C2C_ENABLED=true и C2C_PUBLIC_POSTING_ENABLED=false «засев»):

    | Эндпоинт                                  | Закрыто middleware                 | В сервисе / permission            | Не затрагивается |
    |-------------------------------------------|------------------------------------|-----------------------------------|------------------|
    | /api/v1/local/* (каталог, карточка, ...)  | C2C off                            | -                                 | в засеве открыто |
    | /api/v1/local/listings/<id>/promote/      | C2C off и засев                    | PAYMENTS_ENABLED (404)            | -                |
    | /api/v1/local/* write (подача, фото, VIN) | C2C off                            | CanPostLocalListing (403, засев)  | -                |
    | /api/v1/messages/*, deals/*, saved-searches/* | C2C off и засев                | -                                 | -                |
    | /api/v1/payments/liqpay/checkout/         | C2C off                            | PAYMENTS_ENABLED (404)            | -                |
    | /api/v1/payments/liqpay/callback/         | никогда (C2C_OPEN_PATHS, Q17)      | подпись, 503 без ключа/режим off  | всегда открыт    |
    | /api/v1/favorites/* (listing_type=local)  | -                                  | favorites.views: 404 C2C off/засев | лоты работают    |
    | /api/v1/reports/ (жалоба на C2C)          | -                                  | reports.serializers: 404          | лоты работают    |
    | Celery: check_saved_searches, warn_expiring_listings, expire_listings | -      | ранний возврат                    | -                |
    | pricing, listings, shipments, users, leads, site-settings, admin/       | -    | -                                 | да               |
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if c2c_closed_reason(request.path_info) is not None:
            return JsonResponse({'detail': 'Not found.'}, status=404)
        return self.get_response(request)
