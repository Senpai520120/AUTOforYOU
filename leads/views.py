import logging
import re
import uuid
from collections.abc import Mapping

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.throttles import FailOpenScopedRateThrottle, _alert_once, cache_errors
from integrations.captcha import HONEYPOT_FIELD, require_captcha
from site_settings.models import SiteSettings
from users.permissions import IsBrokerOrAdmin

from . import exports
from .models import Lead, LeadCounter, LeadSource, LeadStatus
from .serializers import (
    BrokerLeadDetailSerializer,
    BrokerLeadListSerializer,
    LeadCreatedSerializer,
    LeadCreateSerializer,
    LeadMineSerializer,
    PartnerStatusSerializer,
    QualificationSerializer,
    StatusChangeSerializer,
)
from .services import (
    AlreadyTaken,
    InvalidTransition,
    KeyConflict,
    PartnerNotConfigured,
    broker_change_status,
    create_lead,
    find_replay,
    qualify_lead,
    set_partner_status,
    take_lead,
)
from .validators import normalize_ua_phone

logger = logging.getLogger(__name__)

PARTNER_NOT_CONFIGURED = {'detail': 'Партнер не налаштований'}
CACHE_DOWN = {'detail': 'Тимчасово недоступно, спробуйте пізніше'}
KEY_CONFLICT = {'detail': 'Ця заявка вже надіслана з іншими даними. Оновіть сторінку та спробуйте ще раз.'}
IDEMPOTENCY_HEADER = 'Idempotency-Key'
REPLAY_HEADER = 'Idempotent-Replay'


def _idempotency_key(request):
    """UUID из заголовка Idempotency-Key; отсутствует или невалиден - None (заявка создаётся как обычно)."""
    raw = request.headers.get(IDEMPOTENCY_HEADER)
    if not raw:
        return None
    try:
        return uuid.UUID(raw.strip())
    except (ValueError, AttributeError):
        return None


def _replay_response(lead):
    response = Response(LeadCreatedSerializer(lead).data, status=status.HTTP_200_OK)
    response[REPLAY_HEADER] = 'true'
    logger.info('lead.dedup reason=key public_id=%s', lead.public_id)
    return response


def _fake_public_id():
    """Правдоподобный следующий номер: счётчик года + 1, без инкремента и записи."""
    year = timezone.now().year
    last = LeadCounter.objects.filter(year=year).values_list('last_number', flat=True).first() or 0
    return f'AFY-{year}-{last + 1:04d}'


@extend_schema(
    tags=['leads'],
    summary='Заявка брокеру',
    description='Гость или вошедший пользователь. Порядок: throttle, honeypot (заполнен: тихий 201 без записи), '
                '503 при пустом partner_name, поиск по Idempotency-Key (до капчи), капча (400 captcha_failed), поля. '
                'Тот же ключ и телефон: 200 с первой заявкой и заголовком Idempotent-Replay, без новой записи. '
                'Тот же ключ и другой телефон: 409 без данных. Тот же телефон в окне '
                'LEAD_DUPLICATE_WINDOW_MINUTES: новая заявка с пометкой «повтор» (в ответе не видна). '
                'ПДн в ответе не возвращаются.',
    parameters=[OpenApiParameter(
        name='Idempotency-Key', type=OpenApiTypes.UUID, location=OpenApiParameter.HEADER, required=False,
        description='UUID одной отправки формы. Невалидный заголовок игнорируется.')],
    request=LeadCreateSerializer,
    responses={
        200: OpenApiResponse(response=LeadCreatedSerializer, description='Повтор отправки: первая заявка'),
        201: LeadCreatedSerializer,
        409: OpenApiResponse(description='Ключ уже использован с другими данными'),
        400: OpenApiResponse(description='Ошибка полей или captcha_failed'),
        429: OpenApiResponse(description='Лимит заявок'),
        503: OpenApiResponse(description='Партнер не налаштований'),
    },
)
class LeadCreateView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [FailOpenScopedRateThrottle]
    throttle_scope = 'lead'

    def post(self, request):
        # Throttle уже отработал в initial(). Дальше: honeypot -> 503 -> капча -> поля -> создание.
        data = request.data
        if not isinstance(data, Mapping):
            raise ValidationError({'non_field_errors': ['Очікується JSON-обʼєкт.']})
        if data.get(HONEYPOT_FIELD):
            logger.warning('lead.honeypot_hit')
            return Response(
                {'public_id': _fake_public_id(), 'status': 'new', 'created_at': timezone.now()},
                status=status.HTTP_201_CREATED,
            )
        if not SiteSettings.load().partner_name.strip():
            return Response(PARTNER_NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        key = _idempotency_key(request)
        if key is not None:
            # До капчи: токен одноразовый, у повторной отправки он уже использован.
            try:
                phone = normalize_ua_phone(data.get('phone'))
            except DjangoValidationError:
                phone = None  # обычная валидация ниже вернёт 400
            if phone:
                try:
                    replay = find_replay(key, phone)
                except KeyConflict:
                    return Response(KEY_CONFLICT, status=status.HTTP_409_CONFLICT)
                if replay is not None:
                    return _replay_response(replay)
        try:
            require_captcha(request, data, point='lead')
        except cache_errors() as exc:
            # Капча (одноразовый nonce в кэше) без Redis не проверяется; fail-open для неё НЕ делаем (10.16).
            logger.warning('lead.captcha_cache_down (%s)', type(exc).__name__)
            _alert_once()
            return Response(CACHE_DOWN, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        serializer = LeadCreateSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        try:
            lead = create_lead(
                user=request.user, data=validated,
                calculation=validated['calculation'], listing=validated['listing'],
                landing=validated['landing'], idempotency_key=key,
            )
        except PartnerNotConfigured:
            return Response(PARTNER_NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except IntegrityError:
            # Гонка: параллельный запрос с тем же ключом успел раньше (уникальный индекс). Не наш случай - 500.
            if key is None:
                raise
            try:
                replay = find_replay(key, validated['phone'])
            except KeyConflict:
                return Response(KEY_CONFLICT, status=status.HTTP_409_CONFLICT)
            if replay is None:
                raise
            return _replay_response(replay)
        return Response(LeadCreatedSerializer(lead).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['leads'], summary='Мои заявки', responses=LeadMineSerializer(many=True))
class MyLeadsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LeadMineSerializer

    def get_queryset(self):
        return Lead.objects.filter(user=self.request.user).order_by('-created_at', '-pk')


# ---- Кабинет брокера (задача 2.4). Видят все заявки: broker и admin; moderator/buyer/dealer - 403. ----

MAX_FILTER_LEN = 100
TAKEN_BY_OTHER = 'Заявку вже взяв інший брокер'
ORDERINGS = {'created_at': ('created_at', 'pk'), '-created_at': ('-created_at', '-pk')}


class BrokerLeadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data['new_count'] = Lead.objects.filter(status=LeadStatus.NEW).count()
        return response


def _broker_queryset():
    return Lead.objects.select_related('assigned_to', 'duplicate_of')


_BROKER_ERRORS = {
    401: OpenApiResponse(description='Не авторизован'),
    403: OpenApiResponse(description='Не broker и не admin'),
    404: OpenApiResponse(description='Заявку не знайдено'),
}


@extend_schema(
    tags=['broker'],
    summary='Заявки (кабинет брокера)',
    description='Только broker и admin. Фильтры по whitelist: status, source, assigned_to=me, utm_source '
                '(точное совпадение, до 100 символов), search (имя или телефон), ordering=created_at|-created_at. '
                'Неизвестное значение status/source/assigned_to/ordering или слишком длинное значение дают 400. '
                'В ответе new_count - число новых заявок.',
    responses={200: BrokerLeadListSerializer(many=True), 401: _BROKER_ERRORS[401], 403: _BROKER_ERRORS[403]},
)
class BrokerLeadListView(generics.ListAPIView):
    permission_classes = [IsBrokerOrAdmin]
    serializer_class = BrokerLeadListSerializer
    pagination_class = BrokerLeadPagination

    def get_queryset(self):
        params = self.request.query_params
        qs = _broker_queryset()
        errors = {}

        def value(name):
            raw = params.get(name, '').strip()
            if len(raw) > MAX_FILTER_LEN:
                errors[name] = 'Занадто довге значення.'
                return ''
            return raw

        status_ = value('status')
        if status_:
            if status_ not in LeadStatus.values:
                errors['status'] = 'Невідомий статус.'
            else:
                qs = qs.filter(status=status_)
        source = value('source')
        if source:
            if source not in LeadSource.values:
                errors['source'] = 'Невідоме джерело.'
            else:
                qs = qs.filter(source=source)
        assigned = value('assigned_to')
        if assigned:
            if assigned != 'me':
                errors['assigned_to'] = 'Дозволено лише me.'
            else:
                qs = qs.filter(assigned_to=self.request.user)
        utm_source = value('utm_source')
        if utm_source:
            qs = qs.filter(utm__source=utm_source)
        search = value('search')
        if search:
            cond = Q(name__icontains=search)
            digits = re.sub(r'\D', '', search)
            if len(digits) >= 3:
                cond |= Q(phone__contains=digits[1:] if digits.startswith('0') else digits)
            qs = qs.filter(cond)
        ordering = params.get('ordering', '-created_at')
        if ordering not in ORDERINGS:
            errors['ordering'] = 'Дозволено created_at або -created_at.'
        if errors:
            raise ValidationError(errors)
        return qs.order_by(*ORDERINGS[ordering])


class _BrokerLeadMixin:
    permission_classes = [IsBrokerOrAdmin]

    def get_lead(self, pk):
        lead = _broker_queryset().select_related('listing').filter(pk=pk).first()
        if lead is None:
            raise NotFound()
        return lead

    def detail(self, lead):
        lead = _broker_queryset().select_related('listing').prefetch_related(
            'status_changes__changed_by').get(pk=lead.pk)
        return Response(BrokerLeadDetailSerializer(lead, context={'request': self.request}).data)


@extend_schema(tags=['broker'], summary='Картка заявки (кабинет брокера)',
               responses={200: BrokerLeadDetailSerializer, **_BROKER_ERRORS})
class BrokerLeadDetailView(_BrokerLeadMixin, APIView):
    def get(self, request, pk):
        return self.detail(self.get_lead(pk))


@extend_schema(tags=['broker'], summary='Змінити статус заявки', request=StatusChangeSerializer,
               responses={200: BrokerLeadDetailSerializer, 400: OpenApiResponse(description='Недопустимий перехід'),
                          409: OpenApiResponse(description='Заявку вже взяв інший брокер'), **_BROKER_ERRORS})
class BrokerLeadStatusView(_BrokerLeadMixin, APIView):
    def post(self, request, pk):
        lead = self.get_lead(pk)
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            broker_change_status(lead, serializer.validated_data['status'], by=request.user,
                                 note=serializer.validated_data['note'], is_admin=request.user.is_admin_role)
        except AlreadyTaken:
            return Response({'detail': TAKEN_BY_OTHER}, status=status.HTTP_409_CONFLICT)
        except InvalidTransition as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.detail(lead)


@extend_schema(tags=['broker'], summary='Взяти заявку в роботу', request=None,
               responses={200: BrokerLeadDetailSerializer, 400: OpenApiResponse(description='Заявку закрито'),
                          409: OpenApiResponse(description='Заявку вже взяв інший брокер'), **_BROKER_ERRORS})
class BrokerLeadTakeView(_BrokerLeadMixin, APIView):
    def post(self, request, pk):
        lead = self.get_lead(pk)
        try:
            take_lead(lead, request.user)
        except AlreadyTaken:
            return Response({'detail': TAKEN_BY_OTHER}, status=status.HTTP_409_CONFLICT)
        except InvalidTransition as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.detail(lead)


@extend_schema(tags=['broker'], summary='Статус партнера (вручну, окремо від статусу заявки)',
               request=PartnerStatusSerializer,
               responses={200: BrokerLeadDetailSerializer, 400: OpenApiResponse(description='Невідомий статус'),
                          409: OpenApiResponse(description='Заявку вже взяв інший брокер'), **_BROKER_ERRORS})
class BrokerLeadPartnerStatusView(_BrokerLeadMixin, APIView):
    def post(self, request, pk):
        lead = self.get_lead(pk)
        serializer = PartnerStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            set_partner_status(lead, serializer.validated_data['partner_status'], by=request.user,
                               is_admin=request.user.is_admin_role)
        except AlreadyTaken:
            return Response({'detail': TAKEN_BY_OTHER}, status=status.HTTP_409_CONFLICT)
        return self.detail(lead)


@extend_schema(tags=['broker'], summary='Кваліфікація заявки (чотири відповіді так/ні)',
               request=QualificationSerializer,
               responses={200: BrokerLeadDetailSerializer,
                          409: OpenApiResponse(description='Заявку вже взяв інший брокер'), **_BROKER_ERRORS})
class BrokerLeadQualificationView(_BrokerLeadMixin, APIView):
    def post(self, request, pk):
        lead = self.get_lead(pk)
        serializer = QualificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            qualify_lead(lead, dict(serializer.validated_data), by=request.user,
                         is_admin=request.user.is_admin_role)
        except AlreadyTaken:
            return Response({'detail': TAKEN_BY_OTHER}, status=status.HTTP_409_CONFLICT)
        return self.detail(lead)


@extend_schema(
    tags=['broker'], summary='CSV-експорт заявок (без персональних даних)',
    description='Только broker и admin. Параметры: status, date_from, date_to (YYYY-MM-DD, по UTC, включительно). '
                'Колонки без имени, телефона, email, комментария, referrer и URL. Каждая выгрузка пишется в аудит.',
    responses={(200, 'text/csv'): OpenApiResponse(description='CSV-файл'),
               400: OpenApiResponse(description='Неверный фильтр'),
               401: _BROKER_ERRORS[401], 403: _BROKER_ERRORS[403], 429: OpenApiResponse(description='Лимит выгрузок')},
)
class LeadExportView(APIView):
    permission_classes = [IsBrokerOrAdmin]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'lead_export'

    def get(self, request):
        params = request.query_params
        errors = {}
        status_ = params.get('status', '').strip()
        if status_ and status_ not in LeadStatus.values:
            errors['status'] = 'Невідомий статус.'
        days = {}
        for name in ('date_from', 'date_to'):
            raw = params.get(name, '').strip()
            if raw:
                try:
                    days[name] = exports.parse_day(raw)
                except ValueError:
                    errors[name] = 'Очікується дата у форматі РРРР-ММ-ДД.'
        if errors:
            raise ValidationError(errors)
        qs = exports.filter_leads(status_, days.get('date_from'), days.get('date_to'))
        filters = {'status': status_, **{k: v.isoformat() for k, v in days.items()}}
        return exports.csv_response(qs, user=request.user, channel='api', filters=filters)
