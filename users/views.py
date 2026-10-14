from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.middleware.csrf import rotate_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .authentication import enforce_csrf
from .cookies import clear_auth_cookies, set_auth_cookies

from .models import CustomUser, DealerApplication, TrustedShop
from .serializers import (
    DealerApplicationCreateSerializer,
    DealerApplicationSerializer,
    RegisterSerializer,
    TrustedShopSerializer,
    UserProfileSerializer,
)
from .services import DuplicatePendingError, apply_for_dealer


def _refresh_from_request(request):
    """refresh из тела (Bearer-клиенты, переходный фронт) или из httpOnly-cookie.

    Тело важнее: браузер сам его не подставит, значит CSRF не нужен.
    Cookie браузер шлёт сам — тогда CSRF проверяется (шаг 5 задачи 1.3).
    """
    body = request.data.get('refresh') if hasattr(request.data, 'get') else None
    if body:
        return body
    cookie = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH_NAME)
    if cookie:
        enforce_csrf(request)
    return cookie


def _token_body(data):
    if settings.AUTH_TOKENS_IN_BODY:
        return {'ok': True, **data}
    return {'ok': True}


@extend_schema(
    tags=['auth'],
    summary='Получить JWT (login)',
    description=(
        'Ставит httpOnly-cookie `access` и `refresh`. Токенов в теле нет '
        '(AUTH_TOKENS_IN_BODY=False с задачи 1.4). Принимает только JSON.'
    ),
)
class CookieTokenObtainView(TokenObtainPairView):
    # Login-CSRF: CSRF-токена у гостя ещё нет, а SameSite=Lax не мешает браузеру
    # ПРИНЯТЬ Set-Cookie после кросс-сайтовой HTML-формы. Только JSON: чужой
    # сайт не отправит его без CORS-preflight, а preflight отсекает CORS-whitelist.
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        data = serializer.validated_data
        rotate_token(request)  # новый csrftoken на новую сессию, как django.contrib.auth.login
        response = Response(_token_body(data), status=status.HTTP_200_OK)
        return set_auth_cookies(response, data['access'], data['refresh'])


@extend_schema(
    tags=['auth'],
    summary='Обновить access-токен',
    description=(
        'refresh — из тела или из cookie (тогда нужен заголовок X-CSRFToken). '
        'Старый refresh уходит в blacklist, новые токены ставятся в cookie.'
    ),
)
class CookieTokenRefreshView(TokenRefreshView):
    serializer_class = TokenRefreshSerializer
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        refresh = _refresh_from_request(request)
        serializer = self.get_serializer(data={'refresh': refresh or ''})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, ValidationError, AuthenticationFailed, ObjectDoesNotExist):
            # ObjectDoesNotExist: SimpleJWT 5.5 ищет пользователя через .get() — удалённый даёт 500.
            response = Response(
                {'detail': 'Сесія завершилась. Увійдіть знову.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            return clear_auth_cookies(response)
        data = serializer.validated_data
        response = Response(_token_body(data), status=status.HTTP_200_OK)
        return set_auth_cookies(response, data['access'], data.get('refresh'))


@extend_schema(
    tags=['auth'],
    summary='Выход из системы (отзыв refresh-токена)',
    description=(
        'refresh — из тела или из cookie. Работает и с протухшим access. Если пользователь '
        'аутентифицирован, refresh должен принадлежать ему. Cookie удаляются в любом случае.'
    ),
    request=None,
    responses={200: None, 400: None},
)
class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser]  # иначе кросс-сайтовая форма стирает cookie жертвы

    def post(self, request):
        refresh = _refresh_from_request(request)
        if not refresh:
            response = Response({'detail': 'Сесію вже завершено.'}, status=status.HTTP_400_BAD_REQUEST)
            return clear_auth_cookies(response)
        try:
            token = RefreshToken(refresh)
        except TokenError:
            response = Response({'detail': 'Сесію вже завершено.'}, status=status.HTTP_400_BAD_REQUEST)
            return clear_auth_cookies(response)
        # 01-S13: чужой refresh не отзываем.
        if request.user.is_authenticated and str(token.get('user_id')) != str(request.user.pk):
            response = Response({'detail': 'Невірний токен сесії.'}, status=status.HTTP_400_BAD_REQUEST)
            return clear_auth_cookies(response)
        try:
            token.blacklist()
        except TokenError:
            pass  # уже в blacklist — результат тот же
        return clear_auth_cookies(Response({'ok': True}))


@extend_schema(
    tags=['auth'],
    summary='Выдать CSRF-cookie',
    description='Ставит cookie `csrftoken` (не httpOnly). Фронт шлёт её значение в заголовке `X-CSRFToken`.',
    request=None,
    responses={204: None},
)
@method_decorator(ensure_csrf_cookie, name='get')
class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=['auth'], summary='Регистрация нового пользователя')
class RegisterView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


@extend_schema_view(
    get=extend_schema(tags=['auth'], summary='Получить профиль текущего пользователя'),
    put=extend_schema(tags=['auth'], summary='Обновить профиль'),
    patch=extend_schema(tags=['auth'], summary='Частично обновить профиль'),
)
class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


# --- Личный кабинет ---

@extend_schema(tags=['me'], summary='История моих расчётов')
class MyCalculationsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from pricing.models import Calculation
        return Calculation.objects.filter(user=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        from pricing.serializers import CalculationSerializer
        return CalculationSerializer


@extend_schema(tags=['me'], summary='Мои отслеживаемые контейнеры')
class MyShipmentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from shipments.models import Shipment
        return Shipment.objects.filter(watchers=self.request.user).prefetch_related('vehicles')

    def get_serializer_class(self):
        from shipments.serializers import ShipmentListSerializer
        return ShipmentListSerializer


@extend_schema_view(
    get=extend_schema(tags=['me'], summary='Мои проверенные партнёры (СТО, маляры, запчасти)'),
    post=extend_schema(tags=['me'], summary='Добавить партнёра'),
)
class TrustedShopListView(generics.ListCreateAPIView):
    serializer_class = TrustedShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TrustedShop.objects.filter(owner=self.request.user)


@extend_schema_view(
    get=extend_schema(tags=['me'], summary='Детали партнёра'),
    put=extend_schema(tags=['me'], summary='Обновить партнёра'),
    patch=extend_schema(tags=['me'], summary='Частично обновить партнёра'),
    delete=extend_schema(tags=['me'], summary='Удалить партнёра'),
)
class TrustedShopDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TrustedShopSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TrustedShop.objects.filter(owner=self.request.user)


# --- Верификация дилеров ---

@extend_schema(
    tags=['dealers'],
    summary='Подать заявку на статус дилера',
    description=(
        'Создаёт заявку со статусом pending. '
        'Повторная подача при наличии pending-заявки возвращает 409.'
    ),
)
class DealerApplyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DealerApplicationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            application = apply_for_dealer(
                user=request.user,
                **serializer.validated_data,
            )
        except DuplicatePendingError as e:
            return Response({'detail': str(e)}, status=status.HTTP_409_CONFLICT)
        return Response(DealerApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['dealers'],
    summary='Статус собственной заявки',
    description='Возвращает последнюю заявку текущего пользователя (или 404).',
)
class DealerApplicationStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        application = (
            DealerApplication.objects.filter(user=request.user).order_by('-created_at').first()
        )
        if not application:
            return Response({'detail': 'Заявка не найдена.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(DealerApplicationSerializer(application).data)
