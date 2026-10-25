"""Расширяемый реестр провайдеров и их статусов (задача 3.1).

Адаптер регистрирует себя сам: `register_provider(key, title, status_fn, env_vars, checklist_anchor)`
вызывается из `AppConfig.ready()` своего приложения. Базовые 8 ключей регистрируются здесь
(`register_builtin_providers`). Пока провайдер не переведён на адаптер (3.2–3.4), статус
считается по `settings`, без вызова внешнего API и без обращения к БД.
"""
import logging
from dataclasses import dataclass
from typing import Callable

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from core.modules import module_enabled

from .base import (
    ENV_SET,
    MODE_OFF,
    ProviderStatus,
    env_state,
    is_placeholder,
    mode_setting_name,
    resolve_mode,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisteredProvider:
    key: str
    title: str
    status_fn: Callable[[], ProviderStatus]
    env_vars: tuple = ()
    checklist_anchor: str = ''


# Пока провайдер не переведён на адаптер (3.2–3.4), его *_MODE кодом не применяется.
NOT_APPLIED_NOTE = 'режим ще не застосовується кодом (задачі 3.2–3.4)'

_REGISTRY: dict = {}


def register_provider(key, title, status_fn, env_vars=(), checklist_anchor=''):
    if key in _REGISTRY:
        raise ImproperlyConfigured(f'Провайдер интеграций «{key}» уже зарегистрирован.')
    _REGISTRY[key] = RegisteredProvider(key, title, status_fn, tuple(env_vars), checklist_anchor)


def unregister_provider(key):
    """Для тестов и перерегистрации."""
    _REGISTRY.pop(key, None)


def is_registered(key) -> bool:
    return key in _REGISTRY


def get_providers() -> list:
    return list(_REGISTRY.values())


def build_status(provider: RegisteredProvider) -> ProviderStatus:
    """Статус одного провайдера. Сбой статус-функции не ломает страницу."""
    try:
        status = provider.status_fn()
    except Exception as exc:  # noqa: BLE001 - страница статуса обязана открываться всегда
        logger.warning('Статус провайдера %s не построен: %s', provider.key, type(exc).__name__)
        return ProviderStatus(
            key=provider.key, title=provider.title, mode=MODE_OFF, configured=False,
            reason='Помилка перевірки статусу', env_vars=provider.env_vars,
            checklist_anchor=provider.checklist_anchor,
        )
    status.key = provider.key
    status.title = status.title or provider.title
    if not status.env_vars:
        status.env_vars = provider.env_vars
    status.checklist_anchor = status.checklist_anchor or provider.checklist_anchor
    return status


def get_statuses(with_health=True) -> list:
    """Статусы всех зарегистрированных провайдеров. with_health=False не трогает БД (для checks)."""
    statuses = [build_status(p) for p in get_providers()]
    if with_health:
        from .models import IntegrationHealth
        rows = {h.provider_key: h for h in IntegrationHealth.objects.all()}
        for status in statuses:
            row = rows.get(status.key)
            if row:
                status.last_success_at = row.last_success_at
                status.last_error_at = row.last_error_at
                status.last_error = row.last_error
    return statuses


def attention_needed() -> bool:
    return any(s.needs_attention for s in get_statuses())


# ─── Статус по настройкам (до перевода провайдеров на адаптеры) ──────────────

def settings_status(key, title, credentials=(), extra_vars=(), needs_credentials=True,
                    checklist_anchor='', has_credentials=None, notes=()) -> ProviderStatus:
    """Статус по `settings`: какие переменные нужны, заданы ли, не плейсхолдеры ли."""
    if has_credentials is None:
        has_credentials = bool(credentials) and all(env_state(n) == ENV_SET for n in credentials)
    res = resolve_mode(key, has_credentials, needs_credentials, env_vars=credentials)
    setting = mode_setting_name(key)
    names = tuple(credentials) + tuple(extra_vars) + (setting,)
    return ProviderStatus(
        key=key, title=title, mode=res.mode, configured=res.configured, reason=res.reason,
        env_vars=names, env_states={n: env_state(n) for n in names}, notes=list(notes),
        checklist_anchor=checklist_anchor, mode_setting=setting, mode_setting_valid=res.valid,
    )


def _nbu():
    return settings_status('nbu', 'Курс НБУ', needs_credentials=False, checklist_anchor='2.5')


def _vin_decode():
    return settings_status('vin_decode', 'VIN-декодер (NHTSA)', needs_credentials=False,
                           checklist_anchor='2.5')


FROZEN_REASON = 'Вимкнено (заморожено до розморозки, VIN_REPORTS_ENABLED=false). Налаштовувати не потрібно'


def _frozen_status(key, title) -> ProviderStatus:
    """Платные VIN-провайдеры заморожены флагом: статус «вимкнено», а не «не налаштовано» (3.2a)."""
    setting = mode_setting_name(key)
    return ProviderStatus(
        key=key, title=title, mode=MODE_OFF, configured=False, reason=FROZEN_REASON,
        env_vars=('VIN_REPORTS_ENABLED', setting), mode_setting=setting,
        env_states={n: env_state(n) for n in (setting,)},
        notes=['Заморожено: ключі не потрібні'], checklist_anchor='3.2a',
    )


def _vin_report():
    if not module_enabled('vin_reports'):
        return _frozen_status('vin_report', 'VIN-звіт (carVertical)')
    return settings_status('vin_report', 'VIN-звіт (carVertical)', credentials=('CARVERTICAL_API_KEY',),
                           checklist_anchor='2.5')


def _opendatabot():
    if not module_enabled('vin_reports'):
        return _frozen_status('opendatabot', 'Opendatabot (реєстри)')
    return settings_status('opendatabot', 'Opendatabot (реєстри)', credentials=('OPENDATABOT_API_KEY',),
                           checklist_anchor='2.5')


def _lots():
    return settings_status('lots', 'Джерело лотів (Apify / ручне введення)', credentials=('APIFY_TOKEN',),
                           checklist_anchor='2.5')


def _liqpay():
    sandbox = 'пісочниця (LIQPAY_SANDBOX=true)' if getattr(settings, 'LIQPAY_SANDBOX', True) else 'бойовий режим'
    return settings_status('liqpay', 'LiqPay (платежі)',
                           credentials=('LIQPAY_PUBLIC_KEY', 'LIQPAY_PRIVATE_KEY'),
                           extra_vars=('LIQPAY_SANDBOX',), checklist_anchor='2.6',
                           notes=[f'Режим LiqPay: {sandbox}', NOT_APPLIED_NOTE])


def _email():
    backend = str(getattr(settings, 'EMAIL_BACKEND', '') or '')
    is_smtp = 'smtp' in backend.lower()
    host_ok = env_state('EMAIL_HOST') == ENV_SET
    from_ok = not is_placeholder(getattr(settings, 'DEFAULT_FROM_EMAIL', ''))
    ok = is_smtp and host_ok and from_ok
    status = settings_status(
        'email', 'Пошта (SMTP)', credentials=('EMAIL_BACKEND', 'EMAIL_HOST', 'DEFAULT_FROM_EMAIL'),
        extra_vars=('EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD'), has_credentials=ok, checklist_anchor='2.4',
    )
    if not ok and status.mode == MODE_OFF and not status.reason.startswith('Помилка'):
        status.reason = 'Не налаштовано: потрібні EMAIL_BACKEND (smtp), EMAIL_HOST, DEFAULT_FROM_EMAIL'
    return status


def _telegram():
    status = settings_status(
        'telegram', 'Telegram', credentials=('TELEGRAM_BOT_TOKEN',),
        extra_vars=('TELEGRAM_CHANNEL_ID', 'TELEGRAM_B2B_CHANNEL_ID', 'TELEGRAM_WEBHOOK_SECRET'),
        checklist_anchor='2.7',
    )
    status.notes.append(NOT_APPLIED_NOTE)
    for name in ('TELEGRAM_CHANNEL_ID', 'TELEGRAM_B2B_CHANNEL_ID', 'TELEGRAM_WEBHOOK_SECRET'):
        status.notes.append(f'{name}: {env_state(name)}')
    return status


def register_builtin_providers():
    register_provider('nbu', 'Курс НБУ', _nbu, (), '2.5')
    register_provider('vin_decode', 'VIN-декодер (NHTSA)', _vin_decode, (), '2.5')
    register_provider('vin_report', 'VIN-звіт (carVertical)', _vin_report, ('CARVERTICAL_API_KEY',), '2.5')
    register_provider('opendatabot', 'Opendatabot (реєстри)', _opendatabot, ('OPENDATABOT_API_KEY',), '2.5')
    register_provider('lots', 'Джерело лотів (Apify / ручне введення)', _lots, ('APIFY_TOKEN',), '2.5')
    register_provider('liqpay', 'LiqPay (платежі)', _liqpay, ('LIQPAY_PUBLIC_KEY', 'LIQPAY_PRIVATE_KEY'), '2.6')
    register_provider('email', 'Пошта (SMTP)', _email, ('EMAIL_BACKEND', 'EMAIL_HOST', 'DEFAULT_FROM_EMAIL'), '2.4')
    register_provider('telegram', 'Telegram', _telegram, ('TELEGRAM_BOT_TOKEN',), '2.7')
