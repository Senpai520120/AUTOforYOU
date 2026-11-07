"""Флаги раздела «Оголошення по Україні» и платежей (задача 6.7). Единственная точка чтения.

Нигде больше `settings.C2C_ENABLED`, `settings.C2C_PUBLIC_POSTING_ENABLED` и `settings.PAYMENTS_ENABLED`
напрямую не читаются. Источник правды - переменные окружения; смена значения требует перезапуска backend.

Матрица:
- C2C_ENABLED=false: раздел закрыт целиком (404 от middleware), подача невозможна ни у кого, кроме Django Admin;
- C2C_ENABLED=true, C2C_PUBLIC_POSTING_ENABLED=false: режим «засев» - каталог, карточка и телефон авторизованному
  открыты, подача только у staff/admin, переписка/сделки/сохранённые поиски/избранное и жалобы по C2C/promote закрыты;
- оба true: ВОЛНА-2.
PAYMENTS_ENABLED закрывает только создание оплат и от C2C-флагов не зависит.
"""
from django.conf import settings


def c2c_enabled() -> bool:
    return bool(getattr(settings, 'C2C_ENABLED', False))


def c2c_public_posting_enabled() -> bool:
    """Подача открыта обычным пользователям. При выключенном разделе значения не имеет (всё закрыто)."""
    return c2c_enabled() and bool(getattr(settings, 'C2C_PUBLIC_POSTING_ENABLED', False))


def c2c_seeding_mode() -> bool:
    """Раздел виден, но подача закрыта («засев»)."""
    return c2c_enabled() and not c2c_public_posting_enabled()


def payments_enabled() -> bool:
    """Открыто ли создание оплат (promote, checkout). Callback LiqPay этим флагом не закрывается."""
    return bool(getattr(settings, 'PAYMENTS_ENABLED', False))
