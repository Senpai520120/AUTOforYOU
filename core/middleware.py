"""404 для API замороженных модулей (2.8). До аутентификации и без обращений к БД.

Любой метод и пользователь (включая staff) получает 404; Django-админка не затрагивается.
Новый маршрут под одним из префиксов обязан быть классифицирован в core/tests_module_flags.py.
"""
import re

from django.http import JsonResponse

from .modules import module_enabled

# (модуль, регулярка пути). /vehicles/<vin>/decode|report|registry/ (VIN-сервисы) сюда не входят.
FROZEN_API_PATHS = (
    ('lots', re.compile(r'^/api/v1/listings/')),
    ('lots', re.compile(r'^/api/v1/lots/import/')),
    ('lots', re.compile(r'^/api/v1/vehicles/(\d+/)?$')),
    ('b2b', re.compile(r'^/api/v1/b2b/')),
    ('dealers', re.compile(r'^/api/v1/dealers/')),
    ('shipments', re.compile(r'^/api/v1/shipments/')),
    ('shipments', re.compile(r'^/api/v1/auth/me/shipments/')),
)


def frozen_module_for(path: str):
    for module, pattern in FROZEN_API_PATHS:
        if pattern.match(path):
            return module
    return None


class ModuleFlagMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        module = frozen_module_for(request.path_info)
        if module is not None and not module_enabled(module):
            return JsonResponse({'detail': 'Не знайдено.'}, status=404)
        return self.get_response(request)
