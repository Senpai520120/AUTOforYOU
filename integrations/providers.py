"""
Интерфейсы и стабы внешних интеграций.

Реальные провайдеры подключаются через переменные окружения (API-ключи).
До получения ключей все провайдеры возвращают демо-данные с флагом demo=True.
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
