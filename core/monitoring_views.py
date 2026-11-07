"""Приём ошибок фронтенда (задача 7.6, 08-Q17): error.tsx, global-error.tsx и SSR (instrumentation.ts).

Без сессии и CSRF (ничего не меняет в БД), лимит client_errors на IP, тело до 4 КБ.
Стек и данные пользователя не принимаются; текст проходит scrub, путь - без query.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.logging_filters import scrub
from core.monitoring import capture_message

MAX_BODY_BYTES = 4096


class ClientErrorSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=500)
    digest = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    path = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')
    component = serializers.ChoiceField(choices=['frontend', 'frontend-ssr'], default='frontend')

    def validate_path(self, value):
        return value.split('?', 1)[0].split('#', 1)[0]


class _SizeLimitedJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        request = (parser_context or {}).get('request')
        try:
            length = int(request.META.get('CONTENT_LENGTH') or 0) if request is not None else 0
        except (TypeError, ValueError):
            length = 0  # нечисловой заголовок: размер проверит чтение потока ниже
        if length > MAX_BODY_BYTES:
            from rest_framework.exceptions import ParseError
            raise ParseError('Тіло запиту завелике.')
        data = stream.read(MAX_BODY_BYTES + 1) if stream is not None else b''
        if len(data) > MAX_BODY_BYTES:
            from rest_framework.exceptions import ParseError
            raise ParseError('Тіло запиту завелике.')
        import io
        return super().parse(io.BytesIO(data), media_type, parser_context)


@extend_schema(
    tags=['monitoring'],
    summary='Отчёт об ошибке фронтенда',
    description='204 при валидных данных, даже если мониторинг выключен. Лимит client_errors на IP, тело до 4 КБ.',
    request=ClientErrorSerializer,
    responses={204: None, 400: None, 429: None},
)
class ClientErrorView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # без cookie-сессии: CSRF не нужен, пользователь не определяется
    parser_classes = [_SizeLimitedJSONParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'client_errors'

    def post(self, request):
        serializer = ClientErrorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # frontend-ssr шлёт только Next изнутри сети (backend:8000, без nginx и X-Forwarded-For).
        # Запрос через nginx (с XFF) выдать себя за SSR не может.
        component = data['component']
        if component == 'frontend-ssr' and request.META.get('HTTP_X_FORWARDED_FOR'):
            component = 'frontend'
        capture_message(
            f'Frontend error: {scrub(data["message"])}',
            level='error',
            extra={'component': component, 'path': scrub(data['path']), 'digest': data['digest']},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
