"""Вход через Keycloak (SSO-1): authorization code + PKCE, проверка id_token, поиск пользователя.

Keycloak отвечает только «кто ты». Роли, бан и удаление остаются здесь: вход через SSO
не меняет role и группы, а заблокированный в AUTOforYOU не войдёт и с верным паролем AD.

Один человек = один email: в realm `duplicateEmailsAllowed: false`. Привязка - сначала по `sub`
(OidcIdentity), затем по email, но только если Keycloak подтвердил адрес (`email_verified is True`).
Привилегированных по email не привязываем: иначе любая учётка Keycloak с адресом админа
получила бы его права. Их связывает `manage.py link_oidc_user`.

Токены Keycloak нигде не храним и не логируем.
"""
import base64
import hashlib
import hmac
import logging
import secrets
from urllib.parse import urlencode

import httpx
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db import IntegrityError, transaction

from .models import CustomUser, OidcIdentity

logger = logging.getLogger(__name__)

SCOPE = 'openid email profile'
TOKEN_TIMEOUT = 5
PRIVILEGED_ROLES = (CustomUser.Role.BROKER, CustomUser.Role.MODERATOR, CustomUser.Role.ADMIN)


class OidcError(Exception):
    """Отказ во входе. `code` уходит пользователю (?sso_error=), `reason` - только в лог."""

    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _endpoint(base, name):
    return f'{base}/protocol/openid-connect/{name}'


def auth_endpoint():
    return _endpoint(settings.OIDC_BROWSER_URL, 'auth')


def logout_endpoint():
    return _endpoint(settings.OIDC_BROWSER_URL, 'logout')


def token_endpoint():
    return _endpoint(settings.OIDC_BACKEND_URL, 'token')


def certs_endpoint():
    return _endpoint(settings.OIDC_BACKEND_URL, 'certs')


def _code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def build_auth_request(next_path):
    """URL Keycloak и то, что положить в подписанную cookie до возврата пользователя."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(32)
    params = {
        'client_id': settings.OIDC_CLIENT_ID,
        'response_type': 'code',
        'scope': SCOPE,
        'redirect_uri': settings.OIDC_REDIRECT_URI,
        'state': state,
        'nonce': nonce,
        'code_challenge': _code_challenge(code_verifier),
        'code_challenge_method': 'S256',
    }
    flow = {'state': state, 'nonce': nonce, 'code_verifier': code_verifier, 'next': next_path}
    return f'{auth_endpoint()}?{urlencode(params)}', flow


def exchange_code(code, code_verifier):
    """code -> id_token. Access/refresh Keycloak не нужны: дальше живут наши JWT."""
    try:
        response = httpx.post(token_endpoint(), data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.OIDC_REDIRECT_URI,
            'client_id': settings.OIDC_CLIENT_ID,
            'client_secret': settings.OIDC_CLIENT_SECRET,
            'code_verifier': code_verifier,
        }, timeout=TOKEN_TIMEOUT)
        body = response.json() if response.status_code == 200 else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError('failed', f'token endpoint: {type(exc).__name__}') from None
    id_token = body.get('id_token') if isinstance(body, dict) else None
    if not isinstance(id_token, str) or not id_token:
        raise OidcError('failed', f'token endpoint: HTTP {response.status_code}, no id_token')
    return id_token


_jwk_clients = {}


def _jwk_client():
    # Ключи realm кешируются на процесс (PyJWKClient сам перечитает набор при новом kid).
    url = certs_endpoint()
    client = _jwk_clients.get(url)
    if client is None:
        client = _jwk_clients[url] = jwt.PyJWKClient(url, cache_keys=True, timeout=TOKEN_TIMEOUT)
    return client


def verify_id_token(id_token, nonce):
    try:
        key = _jwk_client().get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(
            id_token, key,
            algorithms=['RS256'],
            audience=settings.OIDC_CLIENT_ID,
            issuer=settings.OIDC_ISSUER,
            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']},
        )
    except jwt.PyJWTError as exc:
        raise OidcError('failed', f'id_token: {type(exc).__name__}') from None
    # OIDC Core 3.1.3.7: при нескольких audience azp обязан быть нашим client_id.
    if claims.get('azp', settings.OIDC_CLIENT_ID) != settings.OIDC_CLIENT_ID:
        raise OidcError('failed', 'id_token: foreign azp')
    if not nonce or not hmac.compare_digest(str(claims.get('nonce', '')), nonce):
        raise OidcError('failed', 'id_token: nonce mismatch')
    if not isinstance(claims['sub'], str) or not claims['sub']:
        raise OidcError('failed', 'id_token: empty sub')
    return claims


def verified_email(claims):
    """Email, если Keycloak подтвердил, что он принадлежит человеку; иначе ''."""
    if claims.get('email_verified') is True:
        email = claims.get('email')
        return email.strip() if isinstance(email, str) else ''
    return ''


def is_privileged(user):
    return user.is_staff or user.is_superuser or user.role in PRIVILEGED_ROLES


def _ensure_can_sign_in(user):
    for blocked, reason in (
        (not user.is_active, 'inactive'),
        (user.is_banned, 'banned'),
        (user.deleted_at is not None, 'deleted'),
        (user.deletion_scheduled_at is not None, 'deletion scheduled'),
    ):
        if blocked:
            raise OidcError('not_allowed', f'user {user.pk}: {reason}')


def find_user(claims):
    """Пользователь AUTOforYOU для проверенных claims или OidcError. Новых не создаёт."""
    sub = claims['sub']
    identity = OidcIdentity.objects.select_related('user').filter(sub=sub).first()
    if identity is not None:
        _ensure_can_sign_in(identity.user)
        return identity.user

    email = verified_email(claims)
    if not email:
        raise OidcError('not_allowed', 'email not verified by Keycloak')
    users = list(get_user_model().objects.filter(email__iexact=email)[:2])
    if not users:
        raise OidcError('no_account', 'no user with this email')
    if len(users) > 1:
        raise OidcError('not_allowed', 'email is ambiguous')
    user = users[0]
    if is_privileged(user):
        raise OidcError('not_allowed', f'user {user.pk}: privileged, link with link_oidc_user')
    _ensure_can_sign_in(user)
    if not user.is_email_verified and user.has_usable_password():
        # Аккаунт мог завести паролем кто угодно на чужой адрес: владелец адреса не должен в нём оказаться.
        raise OidcError('not_allowed', f'user {user.pk}: local email not verified')
    if OidcIdentity.objects.filter(user=user).exists():
        raise OidcError('not_allowed', f'user {user.pk}: linked to another sub')
    try:
        with transaction.atomic():
            OidcIdentity.objects.create(user=user, sub=sub)
    except IntegrityError:
        # Два первых входа одновременно: связь уже создал другой запрос. Не угадываем, чья она.
        raise OidcError('not_allowed', f'user {user.pk}: concurrent link') from None
    logger.info('SSO: user %s linked to Keycloak account', user.pk)
    return user


def mark_signed_in(user, claims):
    """last_login и подтверждённый email. role, группы и session_version не трогаем."""
    update_last_login(type(user), user)
    email = verified_email(claims)
    if email and not user.is_email_verified and user.email.lower() == email.lower():
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])


def keycloak_logout_url():
    """Logout Keycloak, чтобы закончилась и его сессия (иначе SSO сразу впустит обратно)."""
    params = {'client_id': settings.OIDC_CLIENT_ID}
    if settings.OIDC_POST_LOGOUT_REDIRECT_URI:
        params['post_logout_redirect_uri'] = settings.OIDC_POST_LOGOUT_REDIRECT_URI
    return f'{logout_endpoint()}?{urlencode(params)}'
