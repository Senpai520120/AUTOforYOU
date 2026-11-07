"""
Модель прав AUTOforYOU - единый источник истины.

- buyer: по умолчанию (регистрация роль не принимает).
- dealer: только через одобрение заявки (approve_application), это
  is_verified_dealer=True. B2B-доступ определяется флагом, не role.
- broker, moderator, admin: назначает только администратор в админке
  (действия «Призначити брокером/модератором»); сами не выбираются.
- is_staff: ТОЛЬКО доступ в Django Admin, не право на бизнес-действия.
- is_superuser: полный доступ.
- Модерация объявлений: Django-permission local_listings.moderate_locallisting
  (группы «Модератори» и «Адміністратори»), а не роль и не is_staff.
- Импортные диалоги и заявки брокеру: broker и admin.
"""
from rest_framework.permissions import BasePermission


def _authed(request):
    return bool(request.user and request.user.is_authenticated)


class IsBroker(BasePermission):
    def has_permission(self, request, view):
        return _authed(request) and request.user.is_broker


class IsBrokerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return _authed(request) and (u.is_broker or u.is_admin_role)


class IsModerator(BasePermission):
    """role == moderator, admin или superuser."""
    def has_permission(self, request, view):
        u = request.user
        return _authed(request) and (u.is_moderator or u.is_admin_role)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return _authed(request) and request.user.is_admin_role


class IsEmailVerified(BasePermission):
    """Действия, рассылающие данные другим людям, - только с подтверждённым email (задача 1.6).

    Включается флагом EMAIL_VERIFICATION_REQUIRED. Ставить ВМЕСТЕ с IsAuthenticated:
    аноним здесь получает отказ, а код ответа определяет IsAuthenticated.
    """
    code = 'email_not_verified'
    message = {'detail': 'Підтвердіть email, щоб виконати цю дію.', 'code': 'email_not_verified'}

    def has_permission(self, request, view):
        from django.conf import settings
        if not settings.EMAIL_VERIFICATION_REQUIRED:
            return True
        u = request.user
        return _authed(request) and (u.is_email_verified or u.is_superuser)
