from rest_framework.permissions import BasePermission


class IsVerifiedDealerOrAdmin(BasePermission):
    """Wholesale-контент видят только верифицированные дилеры и администраторы."""
    message = 'Доступ только для верифицированных перекупщиков.'

    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            (request.user.is_verified_dealer or request.user.role == 'admin')
        )
