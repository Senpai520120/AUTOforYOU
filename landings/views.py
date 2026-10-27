from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LandingDetailSerializer, LandingListSerializer
from .services import get_published_page, published_with_calculation


class _PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # Публичный GET без ПДн и без записи в БД. Throttle выключен: SSR Next ходит с одного IP (как content/).
    # Нагрузку держит кэш расчётов (landings.services, TTL CACHE_TTL); лимита запросов на этих адресах
    # нет ни в Django, ни в nginx (limit_req стоит только на auth и admin/login).
    throttle_classes = []


@extend_schema(
    tags=['landings'], operation_id='landings_list', summary='Опубликованные страницы моделей',
    description='Только страницы, у которых расчёт получается при активных ставках. Поля: slug, make, model, '
                'total_usd, total_uah, updated_at. Ничего не пишет в БД.',
    responses={200: inline_serializer('LandingListResponse', {'results': serializers.ListField()})},
)
class LandingListView(_PublicView):
    def get(self, request):
        return Response({'results': LandingListSerializer(published_with_calculation(), many=True).data})


@extend_schema(
    tags=['landings'], operation_id='landings_detail', summary='Страница модели «Пригон з США» с расчётом',
    description='Расчёт - чистая функция по ставкам из БД, `is_estimate: true`, суммы - Decimal-строки. '
                '404, если страница не опубликована или расчёт не получается. Не создаёт Calculation.',
    responses={200: LandingDetailSerializer, 404: OpenApiResponse(description='Нет страницы или расчёта')},
)
class LandingDetailView(_PublicView):
    def get(self, request, slug):
        pair = get_published_page(slug)
        if pair is None:
            raise NotFound()
        return Response(LandingDetailSerializer(pair).data)
