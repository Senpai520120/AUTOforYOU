from rest_framework.permissions import BasePermission


def can_view_wholesale(user):
    """
    Wholesale видят верифицированные дилеры и администраторы (role=admin+is_staff
    или superuser). is_staff сам по себе прав не даёт: его имеют broker и moderator
    ради доступа в Django Admin.
    """
    from core.modules import module_enabled
    return bool(
        module_enabled('b2b')  # 2.8: B2B заморожен - wholesale не выдаётся никому
        and user
        and user.is_authenticated
        and (user.is_verified_dealer or user.is_admin_role)
    )


class IsVerifiedDealerOrAdmin(BasePermission):
    """Wholesale-контент видят только верифицированные дилеры и администраторы."""
    message = 'Доступ только для верифицированных перекупщиков.'

    def has_permission(self, request, view):
        return can_view_wholesale(request.user)
