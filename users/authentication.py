"""JWT из заголовка Bearer или из httpOnly-cookie (задача 1.3).

- Bearer — как раньше в SimpleJWT: невалидный токен → 401. CSRF не нужен:
  браузер сам этот заголовок не добавляет.
- Cookie access — небезопасные методы проходят CSRF-проверку, как в DRF
  SessionAuthentication. Невалидная или протухшая cookie → аноним (09-Q7):
  AllowAny-эндпоинты работают, защищённые отвечают 401 (authenticate_header
  у базового класса — Bearer).
"""
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken


def enforce_csrf(request):
    """Та же проверка, что в SessionAuthentication.enforce_csrf. Для GET/HEAD/OPTIONS — no-op."""
    check = CSRFCheck(lambda req: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise exceptions.PermissionDenied(f'CSRF Failed: {reason}')


class CookieJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        if self.get_header(request) is not None:
            result = super().authenticate(request)
            if result is not None:
                return result

        raw = request.COOKIES.get(settings.AUTH_COOKIE_ACCESS_NAME)
        if not raw:
            return None
        try:
            validated = self.get_validated_token(raw.encode())
            user = self.get_user(validated)
        except (InvalidToken, AuthenticationFailed):
            return None
        enforce_csrf(request)
        return user, validated

    def get_user(self, validated_token):
        user = super().get_user(validated_token)  # is_active проверяет SimpleJWT
        if getattr(user, 'is_banned', False):
            raise AuthenticationFailed('Користувача заблоковано.', code='user_inactive')
        return user


class CookieJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'users.authentication.CookieJWTAuthentication'
    name = ['jwtAuth', 'cookieAuth']
    priority = 1

    def get_security_requirement(self, auto_schema):
        # Bearer ИЛИ cookie — отдельные элементы списка (по умолчанию было бы «оба сразу»).
        return [{name: []} for name in self.name]

    def get_security_definition(self, auto_schema):
        return [
            {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'},
            {
                'type': 'apiKey',
                'in': 'cookie',
                'name': settings.AUTH_COOKIE_ACCESS_NAME,
                'description': (
                    'httpOnly-cookie от POST /api/v1/auth/token/. Небезопасные методы '
                    'требуют заголовок X-CSRFToken (cookie csrftoken).'
                ),
            },
        ]
