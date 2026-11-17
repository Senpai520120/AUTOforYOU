"""Сервисы интеграций (задача 3.2a): единая точка NHTSA-декодирования VIN для всех view."""
import logging

import httpx

from .base import MODE_DEMO, MODE_OFF
from .models import VinReport
from .providers import PROVIDER_ERROR_CODE, PROVIDER_ERROR_MESSAGE, NHTSAVinDecodeProvider
from .validators import VIN_ERROR_MESSAGE, is_valid_vin

logger = logging.getLogger(__name__)

NHTSA_CACHE_PROVIDER = 'nhtsa_vpic'
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAVAILABLE = 503


def decode_vin(vin: str) -> tuple[dict, int]:
    """Декодирует VIN через NHTSA: (тело ответа, HTTP-код). Вызывающий передаёт нормализованный VIN.

    - невалидный VIN -> 400, сеть не трогаем;
    - VIN_DECODE_MODE=off -> 503 `configured: false`;
    - кэш (VinReport) читается и пишется через get_or_create: два запроса одного VIN - одна запись;
    - сбой сети/HTTP -> 503 с общим текстом (текст исключения наружу не идёт), в кэш не пишем;
    - ErrorCode != 0 -> 200 `valid: false`, в кэш не пишем (03-Q9).
    """
    if not is_valid_vin(vin):
        return {'error': 'invalid_vin', 'message': VIN_ERROR_MESSAGE}, HTTP_BAD_REQUEST

    provider = NHTSAVinDecodeProvider()
    mode = provider.resolution().mode
    if mode == MODE_OFF:
        return provider.wrap_response(), HTTP_UNAVAILABLE
    if mode == MODE_DEMO:  # без сети и без кэша: фейковые данные в БД не попадают
        return {**provider.wrap_response(provider.demo_data(vin)), 'cached': False}, HTTP_OK

    cached = VinReport.objects.filter(
        vin=vin, provider=NHTSA_CACHE_PROVIDER, report_data__valid=True,
    ).first()
    if cached:
        return {**cached.report_data, 'cached': True, 'cache_id': cached.pk}, HTTP_OK

    try:
        data = provider.call(provider.decode, vin)
    except (httpx.HTTPError, ValueError):
        # HTTP 4xx/5xx и битый JSON: сбой провайдера, но не TransportError. provider.call уже записал
        # ошибку в IntegrationHealth и перебросил исключение - здесь только общий ответ.
        data = {'error': PROVIDER_ERROR_CODE}
    if data.get('error'):
        return {
            'error': PROVIDER_ERROR_CODE, 'message': PROVIDER_ERROR_MESSAGE,
            'demo': False, 'provider': NHTSA_CACHE_PROVIDER, 'cached': False,
        }, HTTP_UNAVAILABLE

    payload = provider.wrap_response(data)
    if data.get('valid'):
        VinReport.objects.get_or_create(
            vin=vin, provider=NHTSA_CACHE_PROVIDER, defaults={'report_data': payload, 'demo': False},
        )
    return {**payload, 'cached': False}, HTTP_OK
