"""
Интерфейсы и стабы внешних интеграций.

Реальные провайдеры подключаются через переменные окружения (API-ключи).
До получения ключей все провайдеры возвращают демо-данные с флагом demo=True.

NHTSAVinDecodeProvider — реальный бесплатный декодер NHTSA vPIC (без ключа).
AuctionHistoryProvider — заглушка BidFax/Carfax (платный, ключ не подключён).
"""
from abc import ABC, abstractmethod
from datetime import date


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


class NHTSAVinDecodeProvider:
    """
    Декодирует VIN через NHTSA vPIC API.
    Возвращает технические характеристики: make, model, year, engine_cc, fuel_type, body.
    demo=False — данные реальные из федеральной базы США.
    """

    def decode(self, vin: str) -> dict:
        import httpx

        url = _NHTSA_URL.format(vin=vin.upper())
        try:
            resp = httpx.get(url, timeout=10.0)
            resp.raise_for_status()
            results = resp.json().get('Results', [{}])
        except Exception as exc:
            return {'error': str(exc), 'demo': False, 'provider': 'nhtsa_vpic'}

        r = results[0] if results else {}

        def _int(val):
            try:
                return int(float(val)) if val else None
            except (ValueError, TypeError):
                return None

        raw_fuel = (r.get('FuelTypePrimary') or '').lower()
        fuel_type = _FUEL_MAP.get(raw_fuel, 'petrol') if raw_fuel else None

        engine_cc_raw = r.get('DisplacementCC') or ''
        engine_cc = _int(engine_cc_raw)

        return {
            'demo': False,
            'provider': 'nhtsa_vpic',
            'vin': vin.upper(),
            'make': r.get('Make') or None,
            'model': r.get('Model') or None,
            'year': _int(r.get('ModelYear')),
            'engine_cc': engine_cc,
            'fuel_type': fuel_type,
            'body_class': r.get('BodyClass') or None,
            'engine_cylinders': _int(r.get('EngineCylinders')),
            'displacement_cc': engine_cc,
            'fuel_type_primary_raw': r.get('FuelTypePrimary') or None,
            'error_code': r.get('ErrorCode'),
            'error_text': r.get('AdditionalErrorText') or r.get('ErrorText') or None,
        }


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

class OpendatabotProvider(ABC):
    @abstractmethod
    def get_vehicle_info(self, vin: str) -> dict:
        """Данные из реестров Украины (угон, ограничения, история регистраций)."""


class StubOpendatabotProvider(OpendatabotProvider):
    def get_vehicle_info(self, vin: str) -> dict:
        return {
            'demo': True,
            'provider': 'stub_opendatabot',
            'vin': vin,
            'stolen': False,
            'restrictions': [],
            'ua_registrations': [],
            'note': '⚠ Демо-дані. Підключіть Opendatabot API-ключ.',
        }


# ─── Фабрика — выбирает реального или stub-провайдера ────────────────────────

def get_vin_provider() -> VinProvider:
    """
    В будущем: читать из settings.VIN_PROVIDER_API_KEY и возвращать
    реального провайдера. Пока всегда StubVinProvider.
    """
    return StubVinProvider()


def get_auction_history_provider() -> AuctionHistoryProvider:
    return StubAuctionHistoryProvider()


def get_opendatabot_provider() -> OpendatabotProvider:
    return StubOpendatabotProvider()
