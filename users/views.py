import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import generics, permissions, status
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, BaseThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from integrations.captcha import captcha_public_config, require_captcha

from . import lockout
from .authentication import enforce_csrf
from .cookies import clear_auth_cookies, set_auth_cookies
from .emails import send_already_registered_email, send_verification_email
from .export import build_user_export
from .jwt import TokenObtainPairSerializer, TokenRefreshSerializer, VersionedRefreshToken
from .models import CustomUser, DealerApplication, TrustedShop
from .permissions import IsEmailVerified
from .serializers import (
    AccountDeleteSerializer,
    DealerApplicationCreateSerializer,
    DealerApplicationSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    TrustedShopSerializer,
    UserProfileSerializer,
)
from .services import (
    AccountDeletionError,
    DuplicatePendingError,
    apply_for_dealer,
    cancel_account_deletion,
    revoke_all_sessions,
    schedule_account_deletion,
)
from .tasks import send_password_reset_email_task
from .tokens import email_verification_token

logger = logging.getLogger(__name__)


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
    serializer_class = TokenObtainPairSerializer
    parser_classes = [JSONParser]
    # Scoped-лимит по IP поверх общих anon/user (значения — THROTTLE_LOGIN_RATE).
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle, UserRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        email = request.data.get('email') if hasattr(request.data, 'get') else None
        email = email if isinstance(email, str) else ''
        # Порядок проверок: throttle → блокировка → капча → занять попытку → пароль.
        retry_after, count = None, 0
        if email:
            retry_after = lockout.is_locked(email)
        if not retry_after:
            # Капча: всегда при CAPTCHA_ON_LOGIN, иначе после N неудач по аккаунту (счётчик 1.5).
            failures = lockout.failure_count(email) if email else 0
            if settings.CAPTCHA_ON_LOGIN or failures >= settings.CAPTCHA_LOGIN_AFTER_FAILURES:
                require_captcha(request, request.data, point='login', extra={'captcha_required': True})
            if email:
                count, retry_after = lockout.reserve_attempt(email, BaseThrottle().get_ident(request))
        if retry_after:
            response = Response(
                {'detail': 'Забагато спроб. Спробуйте пізніше.', 'retry_after': retry_after},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
            response['Retry-After'] = str(retry_after)
            return response
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed as exc:
            # Одинаково для существующего и несуществующего email; попытка уже занята.
            return Response(
                {
                    'detail': exc.detail,
                    'captcha_required': count >= settings.CAPTCHA_LOGIN_AFTER_FAILURES,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        if email:
            lockout.reset(email)
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
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle, UserRateThrottle]
    throttle_scope = 'refresh'

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
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle, UserRateThrottle]
    throttle_scope = 'register'

    def create(self, request, *args, **kwargs):
        require_captcha(request, request.data, point='register')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # 01-S11: на занятый email отвечаем так же, как на новый; владельцу уходит отдельное письмо.
        # Хеш пароля считаем и для занятого email: ответ не выдаёт существование аккаунта по времени.
        existing = CustomUser.objects.filter(email__iexact=data['email']).first()
        if existing is None:
            try:
                with transaction.atomic():
                    user = serializer.save()
            except IntegrityError:  # гонка двух регистраций одного email: отвечаем как на занятый
                existing = CustomUser.objects.filter(email__iexact=data['email']).first()
            else:
                send_verification_email(user)
        if existing is not None:
            make_password(data['password'])
            send_already_registered_email(existing)
        body = {key: data.get(key, '') for key in ('email', 'first_name', 'last_name', 'phone')}
        return Response(body, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=['auth'],
    summary='Подтвердить email по ссылке из письма',
    request={'application/json': {'type': 'object', 'properties': {
        'uid': {'type': 'string'}, 'token': {'type': 'string'}}, 'required': ['uid', 'token']}},
    responses={200: None, 400: None},
)
class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # без cookie-сессии: не нужен CSRF, ссылка открывается откуда угодно
    parser_classes = [JSONParser]

    def post(self, request):
        invalid = Response(
            {'detail': 'Посилання недійсне або термін його дії минув.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
        uid = request.data.get('uid') if hasattr(request.data, 'get') else None
        token = request.data.get('token') if hasattr(request.data, 'get') else None
        if not isinstance(uid, str) or not isinstance(token, str):
            return invalid
        try:
            user = get_user_model().objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (TypeError, ValueError, OverflowError, ObjectDoesNotExist):
            return invalid
        if not email_verification_token.check_token(user, token):
            return invalid
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])
        return Response({'ok': True})


@extend_schema(
    tags=['auth'],
    summary='Отправить письмо подтверждения ещё раз',
    request=None,
    responses={200: None, 429: None},
)
class ResendVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'verify_resend'

    def post(self, request):
        if not request.user.is_email_verified:
            send_verification_email(request.user)
        return Response({'ok': True})


RESET_REQUESTED_DETAIL = 'Якщо акаунт із такою адресою існує, ми надіслали на неї лист із посиланням.'


@extend_schema(
    tags=['auth'],
    summary='Запросить сброс пароля',
    description=(
        'Всегда 200 с одним текстом, существует аккаунт или нет. Порядок: throttle password_reset -> '
        'honeypot -> капча (400 captcha_failed) -> только затем поиск пользователя и письмо.'
    ),
    request=PasswordResetRequestSerializer,
    responses={200: None, 400: None, 429: None},
)
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # гость; чужая cookie-сессия не должна требовать CSRF
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        require_captcha(request, request.data, point='password_reset')
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Всегда одно и то же действие; поиск пользователя - в задаче, не в запросе.
        try:
            send_password_reset_email_task.delay(serializer.validated_data['email'])
        except Exception as exc:  # брокер недоступен: клиенту тот же ответ, в лог - без email
            logger.error('Не удалось поставить письмо password_reset в очередь: %s', type(exc).__name__)
        return Response({'detail': RESET_REQUESTED_DETAIL})


@extend_schema(
    tags=['auth'],
    summary='Задать новый пароль по ссылке из письма',
    request=PasswordResetConfirmSerializer,
    responses={200: None, 400: None, 429: None},
)
class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle, AnonRateThrottle]
    throttle_scope = 'password_reset'  # капчи нет: токен из письма - секрет и одноразовый

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        with transaction.atomic():
            user.set_password(serializer.validated_data['new_password'])
            user.save(update_fields=['password'])
            revoke_all_sessions(user)
        lockout.reset(user.email)  # владелец подтвердил почту: блокировка входа снимается
        return clear_auth_cookies(Response({'ok': True}))


@extend_schema(
    tags=['auth'],
    summary='Сменить пароль (отзыв всех сессий, новая пара cookie текущему устройству)',
    request=PasswordChangeSerializer,
    responses={200: None, 400: None, 401: None, 429: None},
)
class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'  # перебор старого пароля с украденной сессией

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        with transaction.atomic():
            user.set_password(serializer.validated_data['new_password'])
            user.save(update_fields=['password'])
            revoke_all_sessions(user)
        refresh = VersionedRefreshToken.for_user(user)
        response = Response(_token_body({'access': str(refresh.access_token), 'refresh': str(refresh)}))
        return set_auth_cookies(response, refresh.access_token, refresh)


@extend_schema(
    tags=['auth'],
    summary='Выйти на всех устройствах',
    request=None,
    responses={200: None, 401: None},
)
class LogoutAllView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        revoke_all_sessions(request.user)
        return clear_auth_cookies(Response({'ok': True}))


@extend_schema(
    tags=['auth'],
    summary='Публичная конфигурация входа и регистрации',
    description='Капча (провайдер, публичный ключ, пороги) и флаг обязательности подтверждения email. Без секретов.',
    responses={200: None},
)
class AuthConfigView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        response = Response({
            'captcha': captcha_public_config(request),
            'email_verification_required': settings.EMAIL_VERIFICATION_REQUIRED,
        })
        response['Cache-Control'] = 'no-store'
        return response


@extend_schema_view(
    get=extend_schema(tags=['auth'], summary='Получить профиль текущего пользователя'),
    put=extend_schema(tags=['auth'], summary='Обновить профиль'),
    patch=extend_schema(tags=['auth'], summary='Частично обновить профиль'),
    delete=extend_schema(
        tags=['auth'],
        summary='Запросить удаление аккаунта (подтверждение паролем)',
        description=(
            'Ставит аккаунт на удаление с периодом отмены (SiteSettings.account_deletion_grace_days): '
            'объявления снимаются, все сессии отзываются, cookie удаляются. По истечении периода '
            'данные обезличиваются задачей anonymize_due_accounts. Отмена - cancel-deletion/.'
        ),
        request=AccountDeleteSerializer,
        responses={202: inline_serializer('AccountDeletionScheduled', {
            'deletion_scheduled_for': drf_serializers.DateTimeField()}), 400: None, 401: None, 429: None},
    ),
)
class ProfileView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_throttles(self):
        # Подбор пароля с украденной сессией: DELETE под лимитом password_reset, как смена пароля.
        if self.request.method == 'DELETE':
            self.throttle_scope = 'password_reset'
            return [ScopedRateThrottle(), *super().get_throttles()]
        return super().get_throttles()

    def destroy(self, request, *args, **kwargs):
        serializer = AccountDeleteSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        try:
            due = schedule_account_deletion(request.user)
        except AccountDeletionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = Response({'deletion_scheduled_for': due.isoformat()}, status=status.HTTP_202_ACCEPTED)
        return clear_auth_cookies(response)


@extend_schema(
    tags=['auth'],
    summary='Отменить удаление аккаунта (в период отмены)',
    description='Снятые объявления остаются снятыми: владелец публикует их заново сам.',
    request=None,
    responses={200: UserProfileSerializer, 401: None},
)
class CancelDeletionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        cancel_account_deletion(request.user)
        return Response(UserProfileSerializer(request.user).data)


@extend_schema(
    tags=['me'],
    summary='Выгрузка всех моих данных (JSON-файл)',
    description='Только данные самого пользователя; контрагенты - отображаемым именем. Лимит data_export.',
    responses={200: {'type': 'object'}, 401: None, 429: None},
)
class DataExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle, UserRateThrottle]
    throttle_scope = 'data_export'

    def get(self, request):
        data = build_user_export(request.user)
        filename = f'autoforyou-data-{timezone.localdate():%Y-%m-%d}.json'
        response = HttpResponse(
            json.dumps(data, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2),
            content_type='application/json; charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Cache-Control'] = 'no-store'
        return response


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
    permission_classes = [permissions.IsAuthenticated, IsEmailVerified]

    def post(self, request):
        require_captcha(request, request.data, point='dealer_apply')
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
