"""Права подачи C2C-объявлений (задача 6.7).

`CanPostLocalListing`: пока `C2C_PUBLIC_POSTING_ENABLED=false` («засев»), подавать может только staff/admin
(`is_staff` или роль admin); остальным 403 «Подача оголошень поки закрита». Выключенный раздел целиком
закрывает middleware (404). Ставится ПОСЛЕ IsAuthenticated: аноним получает 401 от него, а не 403 отсюда.

Write-эндпоинты подачи (Grep по local_listings/urls.py), на всех стоит этот класс (тест local_listings/tests_posting.py):
- POST  listings/                         LocalListingListCreateView   - создание объявления
- PATCH/DELETE listings/<pk>/             LocalListingDetailView       - правка и удаление
- POST  listings/<pk>/images/             LocalListingImageUploadView  - загрузка фото
- PATCH/DELETE listings/<pk>/images/<id>/ LocalListingImageDetailView  - главное фото, удаление фото
- GET   vin-prefill/<vin>/                VinPrefillView               - помощник формы подачи (ходит в NHTSA);
                                         публичный (AllowAny), поэтому проверка `posting_allowed` внутри get()
Не затрагиваются: чтение каталога и карточки, contact, my-listings, tariffs, regions, cities;
promote закрыт отдельно (middleware в засеве, PAYMENTS_ENABLED).
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.c2c import c2c_public_posting_enabled

POSTING_CLOSED_DETAIL = 'Подача оголошень поки закрита'


def is_staff_or_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or getattr(user, 'is_admin_role', False)))


def posting_allowed(user) -> bool:
    """Подача открыта всем или пользователь - staff/admin."""
    return c2c_public_posting_enabled() or is_staff_or_admin(user)


class CanPostLocalListing(BasePermission):
    message = POSTING_CLOSED_DETAIL

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return posting_allowed(request.user)
