"""
Сервис импорта аукционного лота в доменные модели.

Принимает нормализованный dict от AuctionLotProvider и создаёт/обновляет:
  Vehicle (upsert по VIN) → VehicleImage (source_url MVP) → Listing (in_transit, retail).

Идемпотентен: повторный вызов с тем же VIN обновляет Vehicle, не плодит дублей.
Скачивание фото в S3 — промт 7.
"""
from decimal import Decimal

from vehicles.models import Vehicle, VehicleImage
from listings.models import Listing


def import_lot(lot_data: dict, seller) -> tuple:
    """
    Args:
        lot_data: нормализованный dict от AuctionLotProvider (см. providers._normalize_lot).
        seller: пользователь, к которому будет привязан Listing.

    Returns:
        (vehicle, listing, listing_created: bool)

    Raises:
        ValueError: если lot_data содержит поле 'error'.
    """
    if lot_data.get('error'):
        raise ValueError(lot_data['error'])

    vin = (lot_data.get('vin') or '').strip().upper()
    if not vin:
        raise ValueError('VIN обязателен для импорта лота')

    vehicle, _ = Vehicle.objects.update_or_create(
        vin=vin,
        defaults={
            'make': lot_data.get('make') or 'Unknown',
            'model': lot_data.get('model') or 'Unknown',
            'year': lot_data.get('year') or 2000,
            'engine_cc': lot_data.get('engine_cc') or 0,
            'fuel_type': lot_data.get('fuel_type') or Vehicle.FuelType.PETROL,
            'mileage_km': lot_data.get('mileage_km') or 0,
            'damage_type': lot_data.get('damage_type') or '',
            'source_auction': lot_data.get('auction') or Vehicle.SourceAuction.OTHER,
            'lot_number': lot_data.get('lot_number') or '',
        },
    )

    # Сохраняем URL фото (скачивание в S3 — промт 7)
    for idx, url in enumerate(lot_data.get('photos') or []):
        if not url:
            continue
        VehicleImage.objects.get_or_create(
            vehicle=vehicle,
            source_url=url,
            defaults={'is_primary': idx == 0},
        )

    final_bid = lot_data.get('final_bid') or Decimal('0')

    listing, created = Listing.objects.get_or_create(
        vehicle=vehicle,
        status=Listing.ListingStatus.IN_TRANSIT,
        defaults={
            'seller': seller,
            'price': final_bid,
            'currency': Listing.Currency.USD,
            'channel': Listing.Channel.RETAIL,
        },
    )

    if not created and final_bid:
        listing.price = final_bid
        listing.save(update_fields=['price', 'updated_at'])

    return vehicle, listing, created
