from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import MetricEventSerializer
from .services import record_metric


@extend_schema(
    tags=['metrics'],
    summary='Клієнтська подія-лічильник',
    description='Лише calculator_visit і mobile_bar_click. Без ПДн, IP і user-agent не зберігаються. 204 без тіла.',
    request=MetricEventSerializer,
    responses={204: None, 400: None, 429: None},
)
class MetricEventView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # без сессии и CSRF; пользователь не определяется
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'metrics_event'

    def post(self, request):
        serializer = MetricEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record_metric(serializer.validated_data['key'])
        return Response(status=status.HTTP_204_NO_CONTENT)
