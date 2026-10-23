"""Middleware проекта. ModuleFlagMiddleware - заморозка модулей по флагам (задача 2.8).

Сюда же 6.7 добавляет C2CFlagMiddleware (одна точка, общий файл).
"""
import re

from django.http import JsonResponse

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
