"""Каркас адаптеров внешних провайдеров (задача 3.1).

Общие правила:
- один переключатель на провайдера: `<КЛЮЧ>_MODE=auto|real|demo|off` в `.env`;
- плейсхолдеры (`your_*`, `changeme`, пусто) считаются «не налаштовано»;
- в статус, лог и `IntegrationHealth.last_error` секреты не попадают, только имена переменных.
"""
import logging
import re
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone

from core.test_runner import ExternalNetworkBlocked

logger = logging.getLogger(__name__)

MODE_AUTO = 'auto'
MODE_REAL = 'real'
MODE_DEMO = 'demo'
MODE_OFF = 'off'
MODES = (MODE_AUTO, MODE_REAL, MODE_DEMO, MODE_OFF)
# У LiqPay демо-режим называется sandbox (тестовые ключи кабинета), значения demo там нет.
MODE_SANDBOX = 'sandbox'
LIQPAY_MODES = (MODE_AUTO, MODE_REAL, MODE_SANDBOX, MODE_OFF)

# Сетевые сбои, на которых допустим повтор (03-C9). Остальные исключения адаптер не глотает.
RETRYABLE_EXCEPTIONS = (httpx.TransportError, urllib.error.URLError, OSError)

LAST_ERROR_MAX_LEN = 500

ENV_SET = 'задано'
ENV_UNSET = 'не задано'
ENV_PLACEHOLDER = 'плейсхолдер'

_PLACEHOLDER_RE = re.compile(
    r'^(your[_-].*|changeme.*|change[_-]?me.*|x{3,}|<.*>|test|dummy|placeholder|none|null|todo)$', re.IGNORECASE,
)


def http_timeout() -> int:
    """Единый таймаут HTTP-вызовов провайдеров, секунды (`INTEGRATIONS_HTTP_TIMEOUT`)."""
    return int(getattr(settings, 'INTEGRATIONS_HTTP_TIMEOUT', 10))


def is_placeholder(value) -> bool:
    """True для пустого значения и заглушек из шаблонов `.env` (03-C1)."""
    text = str(value or '').strip()
    return not text or bool(_PLACEHOLDER_RE.match(text))


def env_state(name: str) -> str:
    """Состояние переменной настроек без значения: задано / не задано / плейсхолдер."""
    raw = str(getattr(settings, name, '') or '').strip()
    if not raw:
        return ENV_UNSET
    return ENV_PLACEHOLDER if is_placeholder(raw) else ENV_SET


def mode_setting_name(key: str) -> str:
    return f'{key.upper()}_MODE'


def allowed_modes(key: str) -> tuple:
    return LIQPAY_MODES if key == 'liqpay' else MODES


def configured_mode(key: str) -> str:
    return str(getattr(settings, mode_setting_name(key), MODE_AUTO) or MODE_AUTO).strip().lower()


# ─── Маскировка секретов ─────────────────────────────────────────────────────

_SECRET_QS_RE = re.compile(r"(?i)(api[_-]?key|access_token|token|key|secret|password)=[^&\s'\"]+")
_TELEGRAM_TOKEN_RE = re.compile(r'(?<!\d)\d{6,}:[A-Za-z0-9_-]{30,}')
_DSN_RE = re.compile(r'(\b[a-z][a-z0-9+.-]*://[^\s:/@]*:)[^\s@/]+@', re.IGNORECASE)
_HEADER_RE = re.compile(
    r"(?i)(authorization|proxy-authorization|x-api-key|api-key|x-auth-token)([\"']?\s*[:=]\s*)"
    r"((?:bearer|basic|token)\s+)?[^\s,;\"'}]+"
)
_JSON_SECRET_RE = re.compile(
    r"(?i)([\"'][\w-]*(?:api[_-]?key|token|secret|password|passwd)[\"']\s*:\s*)([\"'])(.*?)\2"
)
_URL_QUERY_RE = re.compile(r"(https?://[^\s?'\"]+)\?[^\s'\"]*")
_SECRET_NAME_RE = re.compile(r'(KEY|TOKEN|SECRET|PASSWORD)')
_MIN_SECRET_LEN = 6


def _secret_values():
    values = set()
    for name in dir(settings):
        if not name.isupper() or not _SECRET_NAME_RE.search(name):
            continue
        value = getattr(settings, name, None)
        if isinstance(value, str) and len(value) >= _MIN_SECRET_LEN and not is_placeholder(value):
            values.add(value)
    for db in (getattr(settings, 'DATABASES', None) or {}).values():
        password = db.get('PASSWORD') if isinstance(db, dict) else None
        if isinstance(password, str) and len(password) >= _MIN_SECRET_LEN:
            values.add(password)
    return sorted(values, key=len, reverse=True)


def mask_secrets(text) -> str:
    """Убирает из текста query-строки URL, `apikey=...` и значения секретных настроек."""
    result = _URL_QUERY_RE.sub(r'\1', str(text))
    result = _TELEGRAM_TOKEN_RE.sub('***', result)
    result = _DSN_RE.sub(r'\1***@', result)
    result = _HEADER_RE.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(3) or ""}***', result)
    result = _JSON_SECRET_RE.sub(lambda m: f'{m.group(1)}{m.group(2)}***{m.group(2)}', result)
    result = _SECRET_QS_RE.sub(lambda m: f'{m.group(1)}=***', result)
    for secret in _secret_values():
        result = result.replace(secret, '***')
    return result


# ─── Статус и выбор режима ───────────────────────────────────────────────────

@dataclass
class ProviderStatus:
    key: str
    title: str
    mode: str = MODE_OFF                  # real / demo / off
    configured: bool = False
    reason: str = ''
    env_vars: tuple = ()                  # только имена переменных
    env_states: dict = field(default_factory=dict)   # имя -> задано / не задано / плейсхолдер
    notes: list = field(default_factory=list)        # дополнительные строки статуса
    checklist_anchor: str = ''
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str = ''
    mode_setting: str = ''
    mode_setting_valid: bool = True
    mode_display: str = ''                # подпись режима, если она не совпадает с real/demo/off (LiqPay: sandbox)
    skipped_count: int = 0                # сколько раз операция пропущена из-за «не налаштовано»

    @property
    def mode_label(self) -> str:
        if self.mode_display:
            return self.mode_display
        return {MODE_REAL: 'real', MODE_DEMO: 'demo', MODE_OFF: 'off'}.get(self.mode, self.mode)

    @property
    def env_rows(self) -> list:
        return [(name, self.env_states.get(name, '')) for name in self.env_vars]

    @property
    def has_recent_error(self) -> bool:
        if not self.last_error_at:
            return False
        return timezone.now() - self.last_error_at < timedelta(hours=24)

    @property
    def needs_attention(self) -> bool:
        broken_real = self.mode == MODE_REAL and not self.configured
        return broken_real or self.has_recent_error


@dataclass(frozen=True)
class ModeResolution:
    mode: str
    configured: bool
    reason: str
    valid: bool = True


def _missing_text(env_vars) -> str:
    return ', '.join(env_vars) if env_vars else 'налаштувань'


def resolve_mode(key, has_credentials, needs_credentials=True, env_vars=()) -> ModeResolution:
    """Единое правило выбора реализации по `<КЛЮЧ>_MODE`.

    auto: ключ есть (и не плейсхолдер) -> real, иначе off; без ключей (НБУ, NHTSA) auto = real.
    """
    setting = mode_setting_name(key)
    value = configured_mode(key)
    creds_ok = has_credentials or not needs_credentials
    missing = _missing_text(env_vars)

    if value not in MODES:
        return ModeResolution(
            MODE_OFF, False,
            f'Помилка конфігурації: недопустиме значення {setting} (потрібно auto, real, demo або off)',
            valid=False,
        )
    if value == MODE_DEMO:
        return ModeResolution(MODE_DEMO, True, 'Демо-режим: відповіді позначені demo')
    if value == MODE_OFF:
        return ModeResolution(MODE_OFF, False, f'Вимкнено ({setting}=off)')
    if value == MODE_REAL:
        if creds_ok:
            return ModeResolution(MODE_REAL, True, 'Налаштовано')
        return ModeResolution(
            MODE_REAL, False, f'Помилка конфігурації: {setting}=real, але немає {missing}',
        )
    # auto
    if creds_ok:
        return ModeResolution(MODE_REAL, True, 'Налаштовано')
    return ModeResolution(MODE_OFF, False, f'Не налаштовано: немає {missing}')


class BaseProvider:
    """Базовый адаптер. Real- и demo-реализации наследуют его.

    Подкласс задаёт `key`, `title`, `env_vars` и переопределяет `has_credentials()`.
    """
    key = ''
    title = ''
    env_vars: tuple = ()          # переменные ключей/настроек (для статуса и причины)
    needs_credentials = True
    checklist_anchor = ''

    def has_credentials(self) -> bool:
        return True

    def resolution(self) -> ModeResolution:
        return resolve_mode(
            self.key, self.has_credentials(), self.needs_credentials, env_vars=self.env_vars,
        )

    @property
    def mode(self) -> str:
        return self.resolution().mode

    def is_configured(self) -> bool:
        return self.resolution().configured

    def status(self) -> ProviderStatus:
        res = self.resolution()
        setting = mode_setting_name(self.key)
        names = tuple(self.env_vars) + (setting,)
        return ProviderStatus(
            key=self.key, title=self.title, mode=res.mode, configured=res.configured,
            reason=res.reason, env_vars=names,
            env_states={name: env_state(name) for name in names},
            checklist_anchor=self.checklist_anchor, mode_setting=setting,
            mode_setting_valid=res.valid,
        )

    # --- форма ответа ---------------------------------------------------
    def wrap_response(self, data: dict | None = None) -> dict:
        """Ответ адаптера всегда содержит `configured` и `demo`."""
        res = self.resolution()
        if res.mode in (MODE_OFF,) or not res.configured:
            # off или real без ключа: никаких фейковых полей данных.
            return {'configured': False, 'demo': False, 'reason': res.reason}
        payload = dict(data or {})
        payload['configured'] = True
        payload['demo'] = res.mode == MODE_DEMO
        return payload

    def call(self, func, *args, **kwargs):
        """Вызов внешнего API с учётом здоровья.

        Узкие сетевые сбои -> запись в IntegrationHealth и ответ-ошибка. Сетевой предохранитель
        тестов (`ExternalNetworkBlocked`) и прочие исключения не глотаются (03-Q12).
        """
        try:
            result = func(*args, **kwargs)
        except ExternalNetworkBlocked:
            raise
        except RETRYABLE_EXCEPTIONS as exc:
            record_error(self.key, exc)
            return {'configured': True, 'demo': False, 'error': 'service_unavailable'}
        except Exception as exc:
            record_error(self.key, exc)
            raise
        record_success(self.key)
        return result


# ─── Журнал здоровья ─────────────────────────────────────────────────────────

def record_success(key: str) -> None:
    from .models import IntegrationHealth
    try:
        with transaction.atomic():
            IntegrationHealth.objects.update_or_create(
                provider_key=key, defaults={'last_success_at': timezone.now()},
            )
    except DatabaseError:
        logger.warning('Integration %s: не удалось записать успех в журнал', key)


def record_skip(key: str) -> None:
    """Считает пропуск из-за «не налаштовано»: админ видит число на странице статуса."""
    from .models import IntegrationHealth
    try:
        with transaction.atomic():
            row, _ = IntegrationHealth.objects.get_or_create(provider_key=key)
            IntegrationHealth.objects.filter(pk=row.pk).update(skipped_count=F('skipped_count') + 1)
    except DatabaseError:
        logger.warning('Integration %s: не удалось записать пропуск в журнал', key)


def record_error(key: str, exc: BaseException) -> None:
    """Пишет ошибку провайдера в журнал и лог. Секреты и query-строки отрезаются."""
    from .models import IntegrationHealth
    if isinstance(exc, ExternalNetworkBlocked):
        return
    text = mask_secrets(f'{type(exc).__name__}: {exc}')[:LAST_ERROR_MAX_LEN]
    logger.warning('Integration %s error: %s', key, text)
    try:
        with transaction.atomic():
            row, _ = IntegrationHealth.objects.get_or_create(provider_key=key)
            IntegrationHealth.objects.filter(pk=row.pk).update(
                last_error_at=timezone.now(), last_error=text, error_count=F('error_count') + 1,
            )
    except DatabaseError:
        logger.warning('Integration %s: не удалось записать ошибку в журнал', key)
