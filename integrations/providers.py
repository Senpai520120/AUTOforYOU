"""
Интерфейсы и стабы внешних интеграций.

Реальные провайдеры подключаются через переменные окружения (API-ключи).
До получения ключей все провайдеры возвращают демо-данные с флагом demo=True.

NHTSAVinDecodeProvider — реальный бесплатный декодер NHTSA vPIC (без ключа).
AuctionHistoryProvider — заглушка BidFax/Carfax (платный, ключ не подключён).
AuctionLotProvider — импорт лотов: ManualLotProvider (всегда), ApifyLotProvider (с токеном).
"""
import logging
from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from .base import BaseProvider, http_timeout, mask_secrets

logger = logging.getLogger(__name__)

# Общий текст ошибки для пользователя: ни ключей, ни URL, ни текста исключения.
PROVIDER_ERROR_CODE = 'service_unavailable'
PROVIDER_ERROR_MESSAGE = 'Сервіс тимчасово недоступний. Спробуйте пізніше.'
REGISTRY_ERROR_MESSAGE = 'Сервіс реєстрів тимчасово недоступний. Спробуйте пізніше.'


# ─── VIN-провайдер ───────────────────────────────────────────────────────────

class VinProvider(ABC):
    @abstractmethod
    def get_report(self, vin: str) -> dict:
        """Возвращает dict с полем demo: bool и данными отчёта."""


class StubVinProvider(VinProvider):
    """
    Демо-провайдер VIN-отчётов.
    Возвращает фиктивные данные. demo=True обязателен — UI покажет метку «Демо-данные».
    """

    def get_report(self, vin: str) -> dict:
        return {
            'demo': True,
            'provider': 'stub',
            'vin': vin,
            'make': 'Toyota',
            'model': 'Camry',
            'year': 2019,
            'title_status': 'salvage',
            'odometer_km': 65000,
            'accidents': [
                {
                    'date': '2023-03-15',
                    'severity': 'major',
                    'description': 'Frontal collision — airbags deployed (ДЕМО)',
                }
            ],
            'owners_count': 2,
            'last_auction': 'Copart Dallas',
            'auction_date': str(date.today()),
            'note': '⚠ Демо-данные. Підключіть реального провайдера (CarVertical / VinCheck).',
        }



# ─── NHTSA vPIC — реальный VIN-декодер (бесплатно, без ключа) ───────────────

_NHTSA_URL = 'https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/{vin}?format=json'

_FUEL_MAP = {
    'gasoline': 'petrol',
    'petrol': 'petrol',
    'diesel': 'diesel',
    'flex fuel (ffv)': 'petrol',
    'electric': 'electric',
    'plug-in hybrid electric': 'phev',
    'hybrid (hev)': 'hybrid',
    'natural gas': 'petrol',
}


def _int(val):
    try:
        return int(float(val)) if val else None
    except (ValueError, TypeError):
        return None


def nhtsa_error_ok(error_code) -> bool:
    """ErrorCode NHTSA: '0' - без ошибок; '1,8' и т.п. - есть проблемы (03-Q9)."""
    codes = [c.strip() for c in str(error_code or '').split(',') if c.strip()]
    return bool(codes) and all(c == '0' for c in codes)


class NHTSAVinDecodeProvider(BaseProvider):
    """Декодер VIN через NHTSA vPIC (бесплатно, без ключа). Режим - `VIN_DECODE_MODE`.

    `decode()` сам ничего не глотает: сетевые и HTTP-сбои обрабатывает вызывающий
    (`integrations.services.decode_vin`), который отдаёт пользователю общий текст.
    """
    key = 'vin_decode'
    title = 'VIN-декодер (NHTSA)'
    needs_credentials = False
    checklist_anchor = '2.5'

    def demo_data(self, vin: str) -> dict:
        return {
            'provider': 'demo', 'vin': vin, 'make': 'ДЕМО', 'model': 'ДЕМО', 'year': None,
            'engine_cc': None, 'fuel_type': None, 'valid': True,
        }

    def decode(self, vin: str) -> dict:
        import httpx

        # vin уже прошёл валидатор; quote - второй рубеж: сегмент пути не выходит за свои границы.
        url = _NHTSA_URL.format(vin=quote(vin.upper(), safe=''))
        resp = httpx.get(url, timeout=http_timeout())
        resp.raise_for_status()
        body = resp.json()
        results = body.get('Results') if isinstance(body, dict) else None
        if not isinstance(results, list) or not results or not isinstance(results[0], dict):
            raise ValueError('Unexpected NHTSA response shape')
        r = results[0]

        raw_fuel = (r.get('FuelTypePrimary') or '').lower()
        fuel_type = _FUEL_MAP.get(raw_fuel, 'petrol') if raw_fuel else None
        engine_cc = _int(r.get('DisplacementCC'))
        ok = nhtsa_error_ok(r.get('ErrorCode'))

        data = {
            'provider': 'nhtsa_vpic',
            'vin': vin.upper(),
            'valid': ok,
            'make': r.get('Make') or None,
            'model': r.get('Model') or None,
            'year': _int(r.get('ModelYear')),
            'engine_cc': engine_cc,
            'fuel_type': fuel_type,
            'body_class': r.get('BodyClass') or None,
            'engine_cylinders': _int(r.get('EngineCylinders')),
            'displacement_cc': engine_cc,
            'fuel_type_primary_raw': r.get('FuelTypePrimary') or None,
        }
        if not ok:
            data['error_code'] = r.get('ErrorCode')
            data['error_text'] = r.get('AdditionalErrorText') or r.get('ErrorText') or None
        return data


# ─── История торгов (BidFax) ─────────────────────────────────────────────────

class AuctionHistoryProvider(ABC):
    @abstractmethod
    def get_history(self, vin: str) -> dict:
        """История лотов на аукционах."""


class StubAuctionHistoryProvider(AuctionHistoryProvider):
    def get_history(self, vin: str) -> dict:
        return {
            'demo': True,
            'provider': 'stub_bidfax',
            'vin': vin,
            'lots': [
                {
                    'auction': 'Copart',
                    'location': 'Dallas, TX',
                    'date': '2023-04-01',
                    'sale_price_usd': 8500,
                    'damage': 'Front End',
                    'note': '⚠ Демо-дані (BIDFAX stub)',
                }
            ],
        }


# ─── Opendatabot (UA реестры) ─────────────────────────────────────────────────

# ВАЖНО: сверить эндпоинты с актуальной документацией Opendatabot (opendatabot.ua/doc)
# до активации в продакшене. URL-шаблоны установлены на основе публичной документации v1.
_ODB_VIN_URL = 'https://api.opendatabot.ua/v1/vehicle/vin/{vin}'
_ODB_NUMBER_URL = 'https://api.opendatabot.ua/v1/vehicle/number/{number}'


class OpendatabotProvider(ABC):
    @abstractmethod
    def get_vehicle_info(self, vin: str = None, plate: str = None) -> dict:
        """Данные из реестров Украины (угон, ограничения, история регистраций)."""


class StubOpendatabotProvider(OpendatabotProvider):
    def get_vehicle_info(self, vin: str = None, plate: str = None) -> dict:
        return {
            'demo': True,
            'provider': 'stub_opendatabot',
            'vin': vin,
            'plate': plate,
            'stolen': False,
            'restrictions': [],
            'ua_registrations': [],
            'note': '⚠ Демо-дані. Підключіть Opendatabot API-ключ.',
        }


class RealOpendatabotProvider(OpendatabotProvider):
    """
    Реальный клиент Opendatabot API (httpx).

    Если OPENDATABOT_API_KEY не задан — возвращает демо-ответ (demo=True),
    не бросает исключение и не кидает 500.

    Документация: https://opendatabot.ua/doc
    Сверить _ODB_VIN_URL / _ODB_NUMBER_URL с актуальными эндпоинтами.
    """

    def __init__(self, api_key: str = ''):
        self._api_key = api_key

    def get_vehicle_info(self, vin: str = None, plate: str = None) -> dict:
        if not self._api_key:
            return {
                'demo': True,
                'provider': 'opendatabot',
                'vin': vin,
                'plate': plate,
                'note': '⚠ OPENDATABOT_API_KEY не задан — демо-режим.',
            }

        import httpx

        try:
            if vin:
                url = _ODB_VIN_URL.format(vin=vin.upper())
            elif plate:
                url = _ODB_NUMBER_URL.format(number=plate.upper())
            else:
                return {'demo': True, 'provider': 'opendatabot', 'error': 'Не передано ні VIN, ні номер.'}

            # Ключ в query: передача заголовком в документации
            # https://opendatabot.ua/doc не подтверждена. URL с ключом наружу не отдаём (см. mask_secrets).
            resp = httpx.get(url, params={'apikey': self._api_key}, timeout=10.0)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            logger.warning('Opendatabot request failed: %s', mask_secrets(str(exc)))
            return {
                'demo': False,
                'provider': 'opendatabot',
                'error': PROVIDER_ERROR_CODE,
                'message': REGISTRY_ERROR_MESSAGE,
                'vin': vin,
                'plate': plate,
            }

        data = body.get('data', body)

        return {
            'demo': False,
            'provider': 'opendatabot',
            'vin': data.get('vin') or vin,
            'plate': data.get('number') or plate,
            'brand': data.get('brand'),
            'model': data.get('model'),
            'year': data.get('year'),
            'color': data.get('color'),
            'fuel': data.get('fuelName'),
            'engine_volume': data.get('engineVolume'),
            'stolen': data.get('stolen', False),
            'restrictions': data.get('restrictions', []),
            'owners': data.get('owners', []),
            'odometer': data.get('odometer'),
            'raw': data,
        }


# ─── Фабрика — выбирает реального или stub-провайдера ────────────────────────

VIN_REPORT_NOT_CONFIGURED_MESSAGE = 'Звіт за VIN не налаштовано'


class UnconfiguredVinProvider(VinProvider):
    """Боевой ответ без провайдера отчётов: никаких фейковых полей (make, model, accidents)."""

    def get_report(self, vin: str) -> dict:
        return {'configured': False, 'demo': False, 'message': VIN_REPORT_NOT_CONFIGURED_MESSAGE}


def demo_vin_report_allowed() -> bool:
    """Фейковый StubVinProvider допустим только в dev (DEBUG) или при явном VIN_REPORT_MODE=demo."""
    from django.conf import settings

    from .base import MODE_DEMO, configured_mode
    return bool(settings.DEBUG) or configured_mode('vin_report') == MODE_DEMO


def get_vin_provider() -> VinProvider:
    if demo_vin_report_allowed():
        return StubVinProvider()
    return UnconfiguredVinProvider()


def get_auction_history_provider() -> AuctionHistoryProvider:
    return StubAuctionHistoryProvider()


class UnconfiguredOpendatabotProvider(OpendatabotProvider):
    """OPENDATABOT_MODE=off: платный вызов не делается, ответ без данных."""

    def get_vehicle_info(self, vin: str = None, plate: str = None) -> dict:
        return {'configured': False, 'demo': False, 'provider': 'opendatabot',
                'message': 'Перевірка за реєстрами не налаштована'}


def get_opendatabot_provider() -> OpendatabotProvider:
    from django.conf import settings

    from .base import MODE_OFF, configured_mode
    if configured_mode('opendatabot') == MODE_OFF:
        return UnconfiguredOpendatabotProvider()
    api_key = getattr(settings, 'OPENDATABOT_API_KEY', '')
    if api_key:
        return RealOpendatabotProvider(api_key=api_key)
    return RealOpendatabotProvider(api_key='')  # demo mode, safe without key


# ─── Импорт аукционных лотов ─────────────────────────────────────────────────

_VALID_AUCTIONS = {'copart', 'iaai', 'other'}
_VALID_FUEL_TYPES = {'petrol', 'diesel', 'electric', 'hybrid', 'phev'}


def _normalize_lot(raw: dict) -> dict:
    """Приводит сырые поля лота к каноническому виду. Не кидает исключений."""
    vin = (raw.get('vin') or '').strip().upper()
    if not vin or len(vin) != 17:
        return {'error': 'VIN обязателен (ровно 17 символов)', 'demo': False}

    try:
        final_bid = Decimal(str(raw.get('final_bid') or '0'))
    except InvalidOperation:
        final_bid = Decimal('0')

    auction = (raw.get('auction') or 'other').lower()
    if auction not in _VALID_AUCTIONS:
        auction = 'other'

    fuel_type = (raw.get('fuel_type') or 'petrol').lower()
    if fuel_type not in _VALID_FUEL_TYPES:
        fuel_type = 'petrol'

    return {
        'demo': bool(raw.get('demo', False)),
        'provider': raw.get('provider', 'manual'),
        'vin': vin,
        'auction': auction,
        'lot_number': str(raw.get('lot_number') or ''),
        'make': str(raw.get('make') or ''),
        'model': str(raw.get('model') or ''),
        'year': int(raw.get('year') or 2000),
        'engine_cc': int(raw.get('engine_cc') or 0),
        'fuel_type': fuel_type,
        'damage_type': str(raw.get('damage_type') or ''),
        'mileage_km': int(raw.get('mileage_km') or 0),
        'final_bid': final_bid,
        'photos': list(raw.get('photos') or []),
        'location': str(raw.get('location') or ''),
    }


class AuctionLotProvider(ABC):
    @abstractmethod
    def fetch_lot(self, lot_url_or_data) -> dict:
        """
        Возвращает нормализованный dict лота или {'error': ..., 'demo': False}.
        Никогда не кидает исключение.
        """


class ManualLotProvider(AuctionLotProvider):
    """
    Нормализует вручную переданные данные лота (dict).
    Нет внешних зависимостей — рабочий MVP-провайдер.
    """

    def fetch_lot(self, lot_url_or_data) -> dict:
        if not isinstance(lot_url_or_data, dict):
            return {'error': 'ManualLotProvider очікує dict з даними лота', 'demo': False}
        return _normalize_lot({**lot_url_or_data, 'provider': 'manual'})


class ApifyLotProvider(AuctionLotProvider):
    """
    Заглушка под Apify-актор (управляемый скрейпер Copart/IAAI).

    Прямой парсинг Copart/IAAI обходит Cloudflare — не делаем.
    Без APIFY_TOKEN возвращает demo=True, не кидает 500.
    Документация Apify: https://apify.com/docs/api
    """

    def __init__(self, token: str = ''):
        self._token = token

    def fetch_lot(self, lot_url_or_data) -> dict:
        if not self._token:
            return {
                'demo': True,
                'provider': 'apify',
                'note': '⚠ APIFY_TOKEN не задан — демо-режим. Подключите токен для реального импорта.',
                'vin': None,
            }

        import httpx

        # Apify actor run endpoint (dataset v2).
        # Замените YOUR_ACTOR_ID на актуальный ID актора Copart/IAAI.
        # Сверьте с документацией вашего актора: https://apify.com
        _apify_run_url = 'https://api.apify.com/v2/acts/YOUR_ACTOR_ID/run-sync-get-dataset-items'

        try:
            resp = httpx.post(
                _apify_run_url,
                json={'startUrls': [{'url': lot_url_or_data}]},
                headers={'Authorization': f'Bearer {self._token}'},
                timeout=60.0,
            )
            resp.raise_for_status()
            items = resp.json()
            if not items:
                return {'error': 'Apify актор вернул пустой результат', 'demo': False}
            return _normalize_lot({**items[0], 'provider': 'apify'})
        except Exception as exc:
            logger.warning('Apify request failed: %s', mask_secrets(str(exc)))
            return {
                'error': PROVIDER_ERROR_CODE,
                'message': PROVIDER_ERROR_MESSAGE,
                'demo': False,
                'provider': 'apify',
            }


def get_lot_provider() -> AuctionLotProvider:
    from django.conf import settings
    token = getattr(settings, 'APIFY_TOKEN', '')
    if token:
        return ApifyLotProvider(token=token)
    return ApifyLotProvider(token='')  # demo mode, safe without token
