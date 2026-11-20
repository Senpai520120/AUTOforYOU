"""10.23 (F1, F4): телефон объявления - подтверждённый номер владельца.

Подтверждённый номер (`CustomUser.verified_phone` + `phone_verified_at`, ставит бот 4.10) подставляется
сервером; клиентское поле `contact_phone` для такого владельца игнорируется. Исключения: admin/суперпользователь («засев»)
и режим `PHONE_VERIFICATION_REQUIRED=false` - там остаётся номер из запроса (прежнее поведение).
Показ: подтверждение снято (`/unlink`, админка) - телефон в объявлениях скрывается, данные не удаляются.
"""
from django.conf import settings

PHONE_NEEDED = (
    'Підтвердіть телефон через Telegram (розділ «Telegram» в особистому кабінеті), '
    'щоб подати або відправити оголошення на модерацію.'
)


def verified_phone(user) -> str:
    """Подтверждённый номер владельца или пустая строка."""
    if user is not None and user.phone_verified_at is not None and user.verified_phone:
        return user.verified_phone
    return ''


def phone_exempt(user) -> bool:
    """Подтверждение не требуется: флаг выключен или роль admin/суперпользователь (засев).

    Модератор и брокер с `is_staff` не исключены: непроверенный номер публиковать им нельзя.
    """
    return (not settings.PHONE_VERIFICATION_REQUIRED) or bool(getattr(user, 'is_admin_role', False))


def can_publish(user) -> bool:
    return bool(verified_phone(user)) or phone_exempt(user)


def effective_contact_phone(listing) -> str:
    """Телефон, который можно показывать по объявлению (контакт-эндпоинт, кабинет владельца)."""
    owner = listing.owner
    if phone_exempt(owner):
        return listing.contact_phone or ''
    return verified_phone(owner)
