from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VinReport, RegistryReport
from .providers import (
    NHTSAVinDecodeProvider,
    get_vin_provider, get_auction_history_provider, get_opendatabot_provider,
)


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
    # noinspection PyMethodMayBeStatic
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


@extend_schema(
    tags=['vehicles'],
    summary='VIN-декод через NHTSA vPIC',
    description=(
        'Декодирует VIN через бесплатный API NHTSA vPIC (федеральная база США).\n\n'
        'Возвращает технические характеристики: марку, модель, год, объём двигателя, '
        'тип топлива, тип кузова. Результат кэшируется — повторный запрос не обращается к NHTSA.\n\n'
        'История ДТП и торги — отдельный эндпоинт `/report/` (заглушка, требует Carfax/BidFax).\n\n'
        '`demo: false` — данные реальные из NHTSA.'
    ),
    responses={
        200: OpenApiResponse(description='Технические данные из NHTSA vPIC'),
        400: OpenApiResponse(description='Некорректный VIN'),
    },
)
class VinDecodeView(APIView):
    def get(self, request, vin: str):
        vin = vin.upper().strip()
        if len(vin) != 17:
            return Response(
                {'error': 'VIN должен содержать ровно 17 символов.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cached = VinReport.objects.filter(vin=vin, provider='nhtsa_vpic').first()
        if cached:
            return Response({**cached.report_data, 'cached': True, 'cache_id': cached.pk})

        data = NHTSAVinDecodeProvider().decode(vin)

        if 'error' not in data or data.get('make'):
            VinReport.objects.create(
                vin=vin,
                provider='nhtsa_vpic',
                report_data=data,
                demo=False,
            )

        return Response({**data, 'cached': False})


@extend_schema(
    tags=['vehicles'],
    summary='Перевірка по реєстрах України (Opendatabot)',
    description=(
        'Повертає дані з українських реєстрів: власники, пробіг, обтяження (арешти/застави).\n\n'
        'Результат кешується — повторний запрос по тому ж VIN/номеру не звертається до API.\n\n'
        '**Без ключа** (`OPENDATABOT_API_KEY` не задано): `demo: true`, безпечний fallback.\n\n'
        '**З ключем**: реальні дані з Opendatabot.'
    ),
    parameters=[
        OpenApiParameter('vin', OpenApiTypes.STR, location=OpenApiParameter.PATH,
                         description='VIN (17 символів) або `_` при пошуку за номером'),
        OpenApiParameter('plate', OpenApiTypes.STR, location=OpenApiParameter.QUERY,
                         description='Держномер (наприклад AA1234BB). Якщо вказано — пошук за номером.'),
    ],
    responses={
        200: OpenApiResponse(description='Звіт реєстру (реальний або демо)'),
        400: OpenApiResponse(description='Некоректний VIN або не вказано ані VIN, ані номер'),
    },
)
class RegistryReportView(APIView):
    def get(self, request, vin: str):
        plate = request.query_params.get('plate', '').strip().upper() or None
        vin_clean = vin.upper().strip() if vin != '_' else None

        if vin_clean and len(vin_clean) != 17:
            return Response(
                {'error': 'VIN повинен містити рівно 17 символів.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not vin_clean and not plate:
            return Response(
                {'error': 'Вкажіть VIN у шляху або ?plate= у параметрах.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider_name = 'opendatabot'

        # Cache lookup
        cached = None
        if vin_clean:
            cached = RegistryReport.objects.filter(vin=vin_clean, provider=provider_name).first()
        elif plate:
            cached = RegistryReport.objects.filter(plate=plate, provider=provider_name).first()

        if cached:
            return Response({**cached.payload, 'cached': True, 'cache_id': cached.pk})

        # Fetch from provider
        data = get_opendatabot_provider().get_vehicle_info(vin=vin_clean, plate=plate)

        RegistryReport.objects.create(
            vin=vin_clean,
            plate=plate,
            provider=provider_name,
            payload=data,
            demo=data.get('demo', True),
        )

        return Response({**data, 'cached': False})
