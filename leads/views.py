import logging
from collections.abc import Mapping

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from integrations.captcha import HONEYPOT_FIELD, require_captcha
from site_settings.models import SiteSettings

from .models import Lead, LeadCounter
from .serializers import LeadCreatedSerializer, LeadCreateSerializer, LeadMineSerializer
from .services import PartnerNotConfigured, create_lead

logger = logging.getLogger(__name__)

PARTNER_NOT_CONFIGURED = {'detail': 'Партнер не налаштований'}


def _fake_public_id():
    """Правдоподобный следующий номер: счётчик года + 1, без инкремента и записи."""
    year = timezone.now().year
    last = LeadCounter.objects.filter(year=year).values_list('last_number', flat=True).first() or 0
    return f'AFY-{year}-{last + 1:04d}'


@extend_schema(
    tags=['leads'],
    summary='Заявка брокеру',
    description='Гость или вошедший пользователь. Порядок: throttle, honeypot (заполнен: тихий 201 без записи), '
                'капча (400 captcha_failed), поля. Пустой SiteSettings.partner_name даёт 503. '
                'ПДн в ответе не возвращаются.',
    request=LeadCreateSerializer,
    responses={
        201: LeadCreatedSerializer,
        400: OpenApiResponse(description='Ошибка полей или captcha_failed'),
        429: OpenApiResponse(description='Лимит заявок'),
        503: OpenApiResponse(description='Партнер не налаштований'),
    },
)
class LeadCreateView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
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
        require_captcha(request, data, point='lead')
        serializer = LeadCreateSerializer(data=data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        try:
            lead = create_lead(
                user=request.user, data=validated,
                calculation=validated['calculation'], listing=validated['listing'],
            )
        except PartnerNotConfigured:
            return Response(PARTNER_NOT_CONFIGURED, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(LeadCreatedSerializer(lead).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=['leads'], summary='Мои заявки', responses=LeadMineSerializer(many=True))
class MyLeadsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LeadMineSerializer

    def get_queryset(self):
        return Lead.objects.filter(user=self.request.user).order_by('-created_at', '-pk')
