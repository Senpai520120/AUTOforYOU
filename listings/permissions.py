from rest_framework.permissions import BasePermission


class IsVerifiedDealerOrAdmin(BasePermission):
    """
    Wholesale-контент видят только верифицированные дилеры и администраторы.

    Признак администратора — is_staff, а не role. Поле role пользователь
    указывает сам при регистрации, и раньше значение 'admin' открывало
    эту доску кому угодно.
    """
    message = 'Доступ только для верифицированных перекупщиков.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.is_verified_dealer or request.user.is_staff)
        )
