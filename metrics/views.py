from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import MetricEventSerializer
from .services import record_metric


class MetricEventView(APIView):
    """POST /api/v1/metrics/event/ - событие с фронта (визит калькулятора, клик мобильной панели).

    Без аутентификации и сессий (не нужен CSRF, cookie не читаются); IP и user-agent не сохраняются.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'metrics_event'

    @extend_schema(
        tags=['metrics'], summary='Подія лічильника (без ПДн)', request=MetricEventSerializer,
        responses={204: OpenApiResponse(description='Засчитано'), 400: OpenApiResponse(description='Ключ не з білого списку'),
                   429: OpenApiResponse(description='Ліміт')},
    )
    def post(self, request):
        serializer = MetricEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        record_metric(serializer.validated_data['key'])
        return Response(status=status.HTTP_204_NO_CONTENT)
