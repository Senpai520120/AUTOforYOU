from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .importer import import_lot
from .models import VinReport, RegistryReport
from .providers import (
    NHTSAVinDecodeProvider,
    ManualLotProvider,
    get_vin_provider, get_auction_history_provider, get_opendatabot_provider, get_lot_provider,
)
from .serializers import LotImportRequestSerializer


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


@extend_schema(
    tags=['lots'],
    summary='Імпорт лоту аукціону',
    description=(
        'Тільки для адміністраторів.\n\n'
        '**source=manual** (за замовчуванням): приймає `lot_data` dict з полями лоту — '
        'рабочий MVP без зовнішніх залежностей.\n\n'
        '**source=apify**: `lot_url` — URL лоту на Copart/IAAI; '
        'потребує `APIFY_TOKEN`; без токену повертає `demo=true`.\n\n'
        'Повторний імпорт того ж VIN оновлює Vehicle, не плодить дублів.\n\n'
        '⚠ Автоматичний імпорт за розкладом — Celery (промт 10).',
    ),
    request=LotImportRequestSerializer,
    responses={
        201: OpenApiResponse(description='Лот створено (новий Vehicle+Listing)'),
        200: OpenApiResponse(description='Лот оновлено (Vehicle з таким VIN вже існував)'),
        400: OpenApiResponse(description='Помилка валідації або провайдера'),
        403: OpenApiResponse(description='Тільки адміністратори'),
    },
)
class LotImportView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        ser = LotImportRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        source = ser.validated_data['source']

        if source == 'manual':
            provider = ManualLotProvider()
            lot_data = provider.fetch_lot(ser.validated_data['lot_data'])
        else:
            provider = get_lot_provider()
            lot_data = provider.fetch_lot(ser.validated_data['lot_url'])

        if lot_data.get('error'):
            return Response({'error': lot_data['error']}, status=status.HTTP_400_BAD_REQUEST)

        try:
            vehicle, listing, created = import_lot(lot_data, seller=request.user)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'vehicle_id': vehicle.id,
                'vin': vehicle.vin,
                'listing_id': listing.id,
                'listing_status': listing.status,
                'created': created,
                'demo': lot_data.get('demo', False),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
