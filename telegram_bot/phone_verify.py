"""Подтверждение телефона (задача 4.10, часть 1): контакт из Telegram и заглушка SMS.

Телефон подтверждается только для чата, уже привязанного к аккаунту (одноразовый токен 5.4), и только
собственным контактом отправителя: ``contact.user_id == from_user.id``. Пересланная карточка, чужой
контакт и контакт без ``user_id`` отклоняются. Номер хранится в E.164 и уникален среди подтверждённых
(``CustomUser.verified_phone``); поле профиля ``phone`` пользователь правит сам и для доверия не используется.
SMS - этап «Рост»: ``SmsVerifier`` при ``SMS_VERIFY_ENABLED=false`` бросает ``NotConfigured``.
"""
import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

OK, NOT_OWN, NOT_LINKED, TAKEN, BAD_PHONE = 'ok', 'not_own', 'not_linked', 'taken', 'bad_phone'


class NotConfigured(RuntimeError):
    pass


def normalize_e164(raw: str) -> str:
    """Telegram отдаёт номер с '+' или без; оставляем цифры и ведущий '+'. Не E.164 - пустая строка."""
    digits = re.sub(r'\D', '', raw or '')
    if not 8 <= len(digits) <= 15:
        return ''
    return f'+{digits}'


def mask_phone(phone: str) -> str:
    """Для логов и ответов: +380******67."""
    if len(phone) < 6:
        return '***'
    return f'{phone[:4]}{"*" * (len(phone) - 6)}{phone[-2:]}'


class PhoneVerifier:
    """Интерфейс адаптера подтверждения телефона."""

    def start(self, user):
        raise NotImplementedError

    def confirm(self, **kwargs) -> str:
        raise NotImplementedError


class TelegramContactVerifier(PhoneVerifier):
    """start - deep-link привязки (TelegramLinkTokenView, 5.4); confirm - контакт из бота."""

    def confirm(self, *, telegram_id: int, contact_user_id, phone_number: str) -> str:
        from users.models import CustomUser

        if not contact_user_id or int(contact_user_id) != int(telegram_id):
            return NOT_OWN
        phone = normalize_e164(phone_number)
        if not phone:
            return BAD_PHONE
        with transaction.atomic():
            user = CustomUser.objects.select_for_update().filter(
                telegram_id=telegram_id, is_active=True, deleted_at__isnull=True,
            ).first()
            if user is None:
                return NOT_LINKED
            if CustomUser.objects.filter(verified_phone=phone).exclude(pk=user.pk).exists():
                return TAKEN
            user.verified_phone = phone
            user.phone_verified_at = timezone.now()
            try:
                with transaction.atomic():
                    user.save(update_fields=['verified_phone', 'phone_verified_at'])
            except IntegrityError:  # гонка: тот же номер подтвердили параллельно на другом аккаунте
                return TAKEN
        return OK


class SmsVerifier(PhoneVerifier):
    """Заглушка до этапа «Рост»: реальный SMS-провайдер не подключён."""

    def _check(self):
        if not getattr(settings, 'SMS_VERIFY_ENABLED', False):
            raise NotConfigured('SMS-підтвердження вимкнено (SMS_VERIFY_ENABLED=false).')
        raise NotConfigured('SMS-провайдер не підключено (етап «Ріст»).')

    def start(self, user):
        self._check()

    def confirm(self, **kwargs) -> str:
        self._check()
