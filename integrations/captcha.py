"""Антибот-адаптер (задача 1.6, решение Q2).

Интерфейс ``CaptchaVerifier.verify(token, ip) -> bool``. Провайдер - ``settings.CAPTCHA_PROVIDER``:

- ``turnstile`` - Cloudflare Turnstile (нужен TURNSTILE_SECRET_KEY, иначе остаётся только honeypot
  и предупреждение в логе: честный статус «не настроено», сайт не падает);
- ``honeypot`` - без внешнего сервиса: скрытое поле ``website`` пустое + подписанная метка времени
  выдачи формы (``/auth/config/`` -> captcha.form_token) не моложе CAPTCHA_MIN_FILL_SECONDS;
- ``off`` - ничего не проверяет (только DEBUG и тесты, см. system check).

Honeypot-поле ``website`` проверяется ВСЕГДА (кроме ``off``), Turnstile добавляется поверх.

Все точки используют только ``require_captcha(request, data, *, point)``. Тело отказа:
``{"code": "captcha_failed", "captcha_token": ["..."]}`` (для входа ещё ``captcha_required: true``).
В лог пишутся ``point`` и причина (missing | invalid | network | honeypot | reuse), но не токен и не секрет.

Реестр точек Q2 (источник правды для 1.5, 1.7, 2.1, 2.3, 4.5):

| Точка          | Когда нужна капча                                      | Сервер | UI  | Throttle       |
|----------------|--------------------------------------------------------|--------|-----|----------------|
| register       | всегда                                                 | 1.6    | 1.6 | register (1.5) |
| login          | после CAPTCHA_LOGIN_AFTER_FAILURES неудач или ON_LOGIN | 1.6    | 1.6 | login (1.5)    |
| dealer_apply   | всегда                                                 | 1.6    | 1.6 | существующий   |
| password_reset | запрос сброса (ссылка из письма - без капчи)           | 1.7    | 1.7 | password_reset |
| broker_lead    | всегда, гость и вошедший (заполненный honeypot -       | 2.1    | 2.3 | lead (2.1)     |
|                | тихо 201 без записи)                                   |        |     |                |
| guest_phone    | гость, POST /contact/                                  | 4.5    | 4.5 | contact_guest  |
| жалоба         | капчи нет                                              | -      | -   | reports (4.5)  |
"""
import logging
import secrets
import time
from typing import NamedTuple

import httpx
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from rest_framework.exceptions import ValidationError
from rest_framework.throttling import BaseThrottle

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
TURNSTILE_TIMEOUT = 5
HONEYPOT_FIELD = 'website'
FORM_TOKEN_SALT = 'integrations.captcha.form'
NONCE_CACHE_PREFIX = 'captcha:nonce:'
FAILURE_MESSAGE = 'Не вдалося пройти перевірку. Спробуйте ще раз.'


class CaptchaResult(NamedTuple):
    ok: bool
    reason: str = ''  # missing | invalid | network


def issue_form_token(ip=''):
    """Подписанный одноразовый токен формы для honeypot-режима: время, nonce, IP выдачи."""
    payload = {'t': int(time.time()), 'n': secrets.token_hex(8), 'ip': ip or ''}
    return signing.dumps(payload, salt=FORM_TOKEN_SALT)


class CaptchaVerifier:
    def check(self, token, ip) -> CaptchaResult:
        raise NotImplementedError

    def verify(self, token, ip) -> bool:
        return self.check(token, ip).ok


class DisabledVerifier(CaptchaVerifier):
    def check(self, token, ip):
        return CaptchaResult(True)


class HoneypotVerifier(CaptchaVerifier):
    """Проверяет форм-токен: подпись, возраст (мин. CAPTCHA_MIN_FILL_SECONDS, макс.
    CAPTCHA_FORM_TOKEN_MAX_AGE), привязку к IP и одноразовость (nonce гасится после успеха)."""

    def check(self, token, ip):
        if not token or not isinstance(token, str):
            return CaptchaResult(False, 'missing')
        try:
            payload = signing.loads(
                token, salt=FORM_TOKEN_SALT, max_age=settings.CAPTCHA_FORM_TOKEN_MAX_AGE,
            )
            issued, nonce, token_ip = int(payload['t']), str(payload['n']), payload['ip']
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            return CaptchaResult(False, 'invalid')
        if (token_ip or '') != (ip or ''):
            return CaptchaResult(False, 'invalid')
        age = time.time() - issued
        if age < settings.CAPTCHA_MIN_FILL_SECONDS or age > settings.CAPTCHA_FORM_TOKEN_MAX_AGE:
            return CaptchaResult(False, 'invalid')
        # Гасим токен только после успешной проверки; add атомарен - гонка двух запросов отсекается.
        if not cache.add(NONCE_CACHE_PREFIX + nonce, 1, settings.CAPTCHA_FORM_TOKEN_MAX_AGE):
            return CaptchaResult(False, 'reuse')
        return CaptchaResult(True)


class TurnstileVerifier(CaptchaVerifier):
    def __init__(self, secret):
        self._secret = secret

    def check(self, token, ip):
        if not token or not isinstance(token, str):
            return CaptchaResult(False, 'missing')
        payload = {'secret': self._secret, 'response': token}
        if ip:
            payload['remoteip'] = ip
        try:
            response = httpx.post(TURNSTILE_VERIFY_URL, data=payload, timeout=TURNSTILE_TIMEOUT)
            body = response.json()
        except Exception as exc:  # сеть, таймаут, не-JSON; текст ошибки не логируем
            logger.warning('turnstile siteverify недоступен: %s', type(exc).__name__)
            return CaptchaResult(False, 'network')
        if isinstance(body, dict) and body.get('success') is True:
            return CaptchaResult(True)
        return CaptchaResult(False, 'invalid')


def get_captcha_verifier() -> CaptchaVerifier:
    provider = settings.CAPTCHA_PROVIDER
    if provider == 'off':
        return DisabledVerifier()
    if provider == 'turnstile':
        if settings.TURNSTILE_SECRET_KEY:
            return TurnstileVerifier(settings.TURNSTILE_SECRET_KEY)
        logger.warning('CAPTCHA_PROVIDER=turnstile, но TURNSTILE_SECRET_KEY не задан: только honeypot')
    return HoneypotVerifier()


def captcha_public_config(request=None):
    """Публичная часть конфигурации для /auth/config/ (без секретов)."""
    verifier = get_captcha_verifier()
    if isinstance(verifier, TurnstileVerifier):
        effective = 'turnstile'
    elif isinstance(verifier, HoneypotVerifier):
        effective = 'honeypot'
    else:
        effective = 'off'
    config = {
        'provider': effective,
        'site_key': settings.TURNSTILE_SITE_KEY if effective == 'turnstile' else '',
        'login_after_failures': settings.CAPTCHA_LOGIN_AFTER_FAILURES,
        'on_login': settings.CAPTCHA_ON_LOGIN,
    }
    if effective == 'honeypot':
        config['form_token'] = issue_form_token(BaseThrottle().get_ident(request) if request else '')
    return config


class CaptchaFailed(ValidationError):
    def __init__(self, extra=None):
        super().__init__()
        # Плоский dict: bool в ValidationError превращается в строку, поэтому задаём detail напрямую.
        self.detail = {'code': 'captcha_failed', 'captcha_token': [FAILURE_MESSAGE], **(extra or {})}


def require_captcha(request, data, *, point, extra=None):
    """Проверить капчу или бросить CaptchaFailed (400, code=captcha_failed).

    ``data`` - тело запроса (dict-подобное): ``captcha_token`` и honeypot-поле ``website``.
    ``extra`` - дополнительные ключи тела отказа (вход: ``{'captcha_required': True}``).
    """
    verifier = get_captcha_verifier()
    if isinstance(verifier, DisabledVerifier):
        return
    getter = data.get if hasattr(data, 'get') else (lambda key, default=None: default)
    if getter(HONEYPOT_FIELD):
        logger.warning('captcha failed: point=%s reason=honeypot', point)
        raise CaptchaFailed(extra)
    ip = BaseThrottle().get_ident(request)
    result = verifier.check(getter('captcha_token'), ip)
    if not result.ok:
        logger.warning('captcha failed: point=%s reason=%s', point, result.reason)
        raise CaptchaFailed(extra)
