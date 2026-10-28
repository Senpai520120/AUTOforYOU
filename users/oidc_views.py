"""Маршруты входа через Keycloak (SSO-1): start -> Keycloak -> callback, и logout.

Это переходы браузера, а не fetch: ответы - 302, ошибки - 302 на /login?sso_error=<код>
без подробностей (причина в лог). При OIDC_ENABLED=false все маршруты отдают 404.
"""
import hmac
import logging
import re
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponseRedirect
from django.middleware.csrf import rotate_token
from django.utils.http import url_has_allowed_host_and_scheme
from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.exceptions import Throttled
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import oidc
from .cookies import clear_auth_cookies, set_auth_cookies, set_sso_hint_cookie
from .jwt import VersionedRefreshToken

logger = logging.getLogger(__name__)

FLOW_COOKIE = 'afy_oidc'
FLOW_COOKIE_PATH = '/api/v1/auth/oidc/'
FLOW_COOKIE_SALT = 'users.oidc.flow'
FLOW_MAX_AGE = 600
LOGIN_PAGE = '/login'


def safe_next(value):
    """Только относительный путь своего сайта, иначе '/'."""
    if (
        isinstance(value, str) and value.startswith('/') and len(value) <= 500
        and url_has_allowed_host_and_scheme(value, allowed_hosts=set())
    ):
        return value
    return '/'


def _refuse(code):
    response = HttpResponseRedirect(f'{LOGIN_PAGE}?{urlencode({"sso_error": code})}')
    response.delete_cookie(FLOW_COOKIE, path=FLOW_COOKIE_PATH, samesite='Lax')
    return response


class _OidcView(APIView):
    # Публичные переходы браузера: без DRF-аутентификации (её CSRF-проверка тут не к месту).
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def initial(self, request, *args, **kwargs):
        if not settings.OIDC_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        # Это переход браузера: вместо JSON 429 - страница входа с понятным текстом.
        if isinstance(exc, Throttled):
            return _refuse('throttled')
        return super().handle_exception(exc)


@extend_schema(tags=['auth'], summary='SSO: перейти на вход Keycloak', request=None, responses={302: None, 404: None})
class OidcStartView(_OidcView):
    # Лимит и без nginx (dev, прямой доступ к backend). Не scope login: иначе один вход тратит две попытки.
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        url, flow = oidc.build_auth_request(safe_next(request.query_params.get('next')))
        response = HttpResponseRedirect(url)
        # Lax, а не AUTH_COOKIE_SAMESITE: возврат из Keycloak - кросс-сайтовый переход, Strict cookie не пришлёт.
        response.set_cookie(
            FLOW_COOKIE, signing.dumps(flow, salt=FLOW_COOKIE_SALT),
            max_age=FLOW_MAX_AGE, path=FLOW_COOKIE_PATH,
            secure=settings.AUTH_COOKIE_SECURE, httponly=True, samesite='Lax',
        )
        return response


@extend_schema(
    tags=['auth'], summary='SSO: возврат из Keycloak',
    description='Ставит httpOnly-cookie access/refresh и ведёт на next; при отказе - на /login?sso_error=<код>.',
    request=None, responses={302: None, 404: None},
)
class OidcCallbackView(_OidcView):
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle]
    throttle_scope = 'login'

    def get(self, request):
        try:
            flow = self._load_flow(request)
            claims = oidc.verify_id_token(
                oidc.exchange_code(request.query_params.get('code', ''), flow['code_verifier']),
                flow['nonce'],
            )
            user = oidc.find_user(claims)
        except oidc.OidcError as exc:
            logger.warning('SSO sign-in refused: %s', exc.reason)
            return _refuse(exc.code)
        oidc.mark_signed_in(user, claims)
        refresh = VersionedRefreshToken.for_user(user)
        rotate_token(request)  # новый csrftoken на новую сессию, как при входе паролем
        response = HttpResponseRedirect(flow['next'])
        response.delete_cookie(FLOW_COOKIE, path=FLOW_COOKIE_PATH, samesite='Lax')
        set_sso_hint_cookie(response)
        return set_auth_cookies(response, refresh.access_token, refresh)

    @staticmethod
    def _load_flow(request):
        error = request.query_params.get('error')
        if error:
            # Пользователь нажал «Отмена» или Keycloak отказал: в token endpoint не ходим.
            code = 'cancelled' if error == 'access_denied' else 'failed'
            raise oidc.OidcError(code, f'Keycloak error: {re.sub(r"[^a-z_]", "", error)[:50]}')
        raw = request.COOKIES.get(FLOW_COOKIE)
        if not raw:
            raise oidc.OidcError('failed', 'no flow cookie')
        try:
            flow = signing.loads(raw, salt=FLOW_COOKIE_SALT, max_age=FLOW_MAX_AGE)
        except signing.BadSignature:  # и SignatureExpired
            raise oidc.OidcError('failed', 'bad or expired flow cookie') from None
        state = request.query_params.get('state', '')
        if not isinstance(flow, dict) or not hmac.compare_digest(str(flow.get('state', '')), state):
            raise oidc.OidcError('failed', 'state mismatch')
        if not request.query_params.get('code'):
            raise oidc.OidcError('failed', 'no code')
        return flow


@extend_schema(tags=['auth'], summary='SSO: выйти и из Keycloak', request=None, responses={302: None, 404: None})
class OidcLogoutView(_OidcView):
    def get(self, request):
        # Обычно refresh уже отозвал POST token/logout/; если тот не дошёл - отзываем здесь.
        raw = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # протух или уже в blacklist
        return clear_auth_cookies(HttpResponseRedirect(oidc.keycloak_logout_url()))
