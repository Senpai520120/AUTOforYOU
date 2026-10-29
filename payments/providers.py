"""Платёжный провайдер как адаптер (задача 3.4b, 06-C2).

`PaymentProvider` - интерфейс, `LiqPayProvider` - реализация поверх протокола из `liqpay_client.py`
(подпись и формат не менялись). Режим - `LIQPAY_MODE`:
- auto: ключи заданы и не плейсхолдеры -> режим по `LIQPAY_SANDBOX` (по умолчанию real: LIQPAY_SANDBOX=false); иначе «не налаштовано»;
- sandbox: тестовые ключи кабинета LiqPay, реальные деньги не списываются (`sandbox=1`);
- real: боевой режим (`sandbox=0`);
- off: оплата выключена.

Адаптер НЕ читает `PAYMENTS_ENABLED` (создание оплат закрывают views через core.c2c.payments_enabled, 6.7).
Отказ callback при пустом ключе/режиме off (503) делает view до `decode_callback` (6.7, минимум от 06-S1).
"""
import logging

from django.conf import settings
from rest_framework import status as http_status
from rest_framework.response import Response

from core.c2c import payments_enabled
from integrations.base import (
    LIQPAY_MODES,
    MODE_AUTO,
    MODE_DEMO,
    MODE_OFF,
    MODE_REAL,
    MODE_SANDBOX,
    BaseProvider,
    ModeResolution,
    configured_mode,
    is_placeholder,
    mode_setting_name,
)

from .liqpay_client import LiqPayClient, LiqPayNotConfigured

logger = logging.getLogger(__name__)

SANDBOX_KEY_PREFIX = 'sandbox_'   # так начинаются тестовые ключи кабинета LiqPay
PAYMENT_UNAVAILABLE_DETAIL = 'Оплата тимчасово недоступна'


class PaymentNotConfigured(Exception):
    """Checkout запрошен у провайдера, который не налаштовано (вызывающий код обязан проверить is_configured)."""


class PaymentProvider(BaseProvider):
    """Интерфейс платёжного провайдера."""

    @property
    def is_sandbox(self) -> bool:
        raise NotImplementedError

    def create_checkout(self, order_id, amount, currency, description, result_url='', server_url='') -> dict:
        raise NotImplementedError

    def decode_callback(self, data: str, signature: str) -> dict:
        raise NotImplementedError

    def map_status(self, provider_status: str) -> str:
        raise NotImplementedError


class LiqPayProvider(PaymentProvider):
    key = 'liqpay'
    title = 'LiqPay (платежі)'
    env_vars = ('LIQPAY_PUBLIC_KEY', 'LIQPAY_PRIVATE_KEY', 'LIQPAY_SANDBOX')
    checklist_anchor = '2.6'

    # ── ключи и режим ────────────────────────────────────────────────────────
    @staticmethod
    def _public_key() -> str:
        return str(getattr(settings, 'LIQPAY_PUBLIC_KEY', '') or '')

    @staticmethod
    def _private_key() -> str:
        return str(getattr(settings, 'LIQPAY_PRIVATE_KEY', '') or '')

    def has_credentials(self) -> bool:
        return not is_placeholder(self._public_key()) and not is_placeholder(self._private_key())

    def resolution(self) -> ModeResolution:
        setting = mode_setting_name(self.key)
        value = configured_mode(self.key)
        if value not in LIQPAY_MODES:
            return ModeResolution(
                MODE_OFF, False,
                f'Помилка конфігурації: недопустиме значення {setting} (потрібно auto, real, sandbox або off)',
                valid=False,
            )
        if value == MODE_OFF:
            return ModeResolution(MODE_OFF, False, f'Вимкнено ({setting}=off)')
        keys_ok = self.has_credentials()
        if not keys_ok:
            if value == MODE_AUTO:
                return ModeResolution(
                    MODE_OFF, False, 'Не налаштовано: немає LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY',
                )
            mode = MODE_REAL if value == MODE_REAL else MODE_DEMO
            return ModeResolution(
                mode, False, f'Помилка конфігурації: {setting}={value}, але немає LIQPAY_PUBLIC_KEY, LIQPAY_PRIVATE_KEY',
            )
        if value == MODE_AUTO:
            value = MODE_SANDBOX if getattr(settings, 'LIQPAY_SANDBOX', False) else MODE_REAL
        if value == MODE_SANDBOX:
            return ModeResolution(MODE_DEMO, True, 'Налаштовано: sandbox (реальні гроші не списуються)')
        if self._public_key().startswith(SANDBOX_KEY_PREFIX):
            return ModeResolution(
                MODE_REAL, False,
                'Помилка конфігурації: бойовий режим, але LIQPAY_PUBLIC_KEY - sandbox-ключ',
            )
        return ModeResolution(MODE_REAL, True, 'Налаштовано: бойовий режим')

    @property
    def is_sandbox(self) -> bool:
        """True в режиме sandbox. Для не налаштованого провайдера - True (безопасная сторона)."""
        res = self.resolution()
        return not (res.configured and res.mode == MODE_REAL)

    def status(self):
        st = super().status()
        res = self.resolution()
        if res.configured and res.mode == MODE_DEMO:
            st.mode_display = MODE_SANDBOX
            if not self._public_key().startswith(SANDBOX_KEY_PREFIX):
                st.notes.append('Увага: режим sandbox, але LIQPAY_PUBLIC_KEY схожий на бойовий ключ')
        # Два независимых уровня: режим провайдера и открытость платных услуг (PAYMENTS_ENABLED, задача 4.1).
        enabled = payments_enabled()
        st.notes.append(f'Платежі: {"увімкнено" if enabled else "вимкнено"} (PAYMENTS_ENABLED)')
        return st

    # ── протокол ─────────────────────────────────────────────────────────────
    def _client(self, sandbox: bool | None = None) -> LiqPayClient:
        return LiqPayClient(
            public_key=self._public_key(), private_key=self._private_key(),
            sandbox=self.is_sandbox if sandbox is None else sandbox,
        )

    def create_checkout(self, order_id, amount, currency, description, result_url='', server_url='') -> dict:
        if not self.is_configured():
            raise PaymentNotConfigured(self.resolution().reason)
        return self._client().create_checkout(
            order_id=order_id, amount=amount, currency=currency, description=description,
            result_url=result_url, server_url=server_url,
        )

    def decode_callback(self, data: str, signature: str) -> dict:
        # 503 до БД делает view; здесь вторая линия защиты (F1): режим off/невалидный/без ключей - исключение.
        # Подпись сравнивается через hmac.compare_digest (06-S10).
        if not self.is_configured():
            raise LiqPayNotConfigured(self.resolution().reason)
        return self._client().decode_callback(data, signature)

    def map_status(self, provider_status: str) -> str:
        # F6: «sandbox» - тестовая оплата; засчитывается только в реально выбранном режиме sandbox
        # (resolution: LIQPAY_MODE=sandbox или auto + LIQPAY_SANDBOX=true), в боевом режиме - нет.
        if provider_status == 'sandbox':
            res = self.resolution()
            if not (res.configured and res.mode == MODE_DEMO):
                logger.warning('LiqPay: статус sandbox вне режима sandbox - оплата не засчитана')
                return 'failed'
        return LiqPayClient.map_status(provider_status)


def get_payment_provider() -> PaymentProvider:
    """Фабрика платёжного провайдера (сейчас единственный - LiqPay)."""
    return LiqPayProvider()


def unavailable_response() -> Response:
    """503 для checkout, когда провайдер не налаштовано или выключен. Текст читает PromoteModal из `detail`."""
    return Response(
        {'detail': PAYMENT_UNAVAILABLE_DETAIL, 'configured': False},
        status=http_status.HTTP_503_SERVICE_UNAVAILABLE,
    )
