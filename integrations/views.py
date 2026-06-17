from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VinReport
from .providers import get_vin_provider, get_auction_history_provider, get_opendatabot_provider


@extend_schema(
    tags=['vehicles'],
    summary='VIN-отчёт',
    description=(
        'Возвращает агрегированный отчёт по VIN: история аварий, торги, реестры UA.\n\n'
        '**Важно**: данные кэшируются в БД. При отсутствии ключей провайдера '
        'возвращаются демо-данные с полем `demo: true` и меткой «Демо-данные» в UI.'
    ),
    responses={
        200: OpenApiResponse(description='Отчёт (реальный или демо)'),
        400: OpenApiResponse(description='Некорректный VIN'),
    },
)
class VinReportView(APIView):
    def get(self, request, vin: str):
        vin = vin.upper().strip()
        if len(vin) != 17:
            return Response({'error': 'VIN должен содержать ровно 17 символов.'}, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем кэш
        cached = VinReport.objects.filter(vin=vin, provider='stub').first()
        if cached:
            return Response({**cached.report_data, 'cached': True, 'cache_id': cached.pk})

        # Получаем от провайдеров
        vin_data = get_vin_provider().get_report(vin)
        auction_data = get_auction_history_provider().get_history(vin)
        ua_data = get_opendatabot_provider().get_vehicle_info(vin)

        report = {
            **vin_data,
            'auction_history': auction_data.get('lots', []),
            'ua_registry': {
                'stolen': ua_data.get('stolen'),
                'restrictions': ua_data.get('restrictions', []),
                'ua_registrations': ua_data.get('ua_registrations', []),
            },
            'demo': True,
            'cached': False,
        }

        VinReport.objects.create(vin=vin, provider='stub', report_data=report, demo=True)

        return Response(report)
