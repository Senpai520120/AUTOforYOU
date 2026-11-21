"""Демо-объявления C2C с настоящими фото для локального стенда.

Работает только при DEMO_SEED_ALLOWED=true (на проде не задавать). Фото берутся из --photos-dir
(файлы `<slug>-1.jpg`, `<slug>-2.jpg`; в репозитории их нет: лицензии CC BY-SA). Необязательный
CREDITS.txt (колонки через TAB: файл, лицензия, ссылка) даёт ссылку-атрибуцию в описание.
Идемпотентна: ключ - (демо-продавец, марка, модель, год). `--clear` удаляет только объявления `[DEMO]`.
"""
import os
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from core.uploads import ImageUploadError, make_thumbnail, max_bytes_from_setting, sanitize_image
from local_listings.models import City, LocalListing, LocalListingImage

DEMO_PREFIX = '[DEMO]'
DEMO_EMAIL = 'demo-seller@demo.test'
DEMO_PHONE = '+380500000123'

L = LocalListing
# slug фото, марка, модель, год, пробег, куб.см, паливо, КПП, кузов, ціна, валюта, примітка
DEMO_CARS = [
    ('toyota-camry-xv70', 'Toyota', 'Camry', 2019, 62000, 2500, L.FuelType.PETROL, L.Transmission.AUTO,
     L.BodyType.SEDAN, '21500', 'USD', ''),
    ('volkswagen-golf-vii', 'Volkswagen', 'Golf', 2017, 98000, 1400, L.FuelType.PETROL, L.Transmission.MANUAL,
     L.BodyType.HATCHBACK, '520000', 'UAH', ''),
    ('skoda-octavia-iii', 'Skoda', 'Octavia', 2018, 143000, 1600, L.FuelType.DIESEL, L.Transmission.ROBOT,
     L.BodyType.HATCHBACK, '14200', 'USD', ''),
    ('ford-focus-iii', 'Ford', 'Focus', 2016, 121000, 1600, L.FuelType.PETROL, L.Transmission.MANUAL,
     L.BodyType.HATCHBACK, '8900', 'EUR', ''),
    ('hyundai-tucson-tl', 'Hyundai', 'Tucson', 2018, 87000, 2000, L.FuelType.PETROL, L.Transmission.AUTO,
     L.BodyType.SUV, '19800', 'USD', ''),
    ('kia-sportage-ql', 'Kia', 'Sportage', 2019, 91000, 1700, L.FuelType.DIESEL, L.Transmission.AUTO,
     L.BodyType.SUV, '780000', 'UAH', ''),
    ('renault-megane-iv', 'Renault', 'Megane', 2018, 110000, 1500, L.FuelType.DIESEL, L.Transmission.MANUAL,
     L.BodyType.HATCHBACK, '11900', 'USD', ''),
    ('nissan-leaf-ze1', 'Nissan', 'Leaf', 2019, 54000, None, L.FuelType.ELECTRIC, L.Transmission.AUTO,
     L.BodyType.HATCHBACK, '15500', 'USD', 'Електро, батарея 40 кВт·год.'),
    ('tesla-model-3', 'Tesla', 'Model 3', 2021, 38000, None, L.FuelType.ELECTRIC, L.Transmission.AUTO,
     L.BodyType.SEDAN, '29900', 'USD', 'Електро.'),
    ('bmw-f30', 'BMW', '320d (F30)', 2016, 156000, 2000, L.FuelType.DIESEL, L.Transmission.AUTO,
     L.BodyType.SEDAN, '16800', 'USD', ''),
]


def require_demo_allowed():
    """Предохранитель: демо-данные не должны попасть на прод."""
    if os.environ.get('DEMO_SEED_ALLOWED', '').strip().lower() != 'true':
        raise CommandError(
            'DEMO_SEED_ALLOWED не равно true: команда разрешена только для локального/тестового стенда.'
        )


def _read_credits(photos_dir: Path) -> dict:
    """{имя файла: (лицензия, ссылка)}; нет файла или строка битая - пропускаем."""
    path = photos_dir / 'CREDITS.txt'
    result = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding='utf-8').splitlines()[1:]:
        parts = line.split('\t')
        if len(parts) >= 3:
            result[parts[0].strip()] = (parts[1].strip(), parts[2].strip())
    return result


class Command(BaseCommand):
    help = 'Создаёт 10 демо-объявлений [DEMO] с фото (только DEMO_SEED_ALLOWED=true).'

    def add_arguments(self, parser):
        parser.add_argument('--photos-dir', required=True, help='Папка с фото <slug>-1.jpg, <slug>-2.jpg')
        parser.add_argument('--clear', action='store_true', help='Удалить только объявления [DEMO] и их фото')

    def handle(self, *args, **options):
        require_demo_allowed()
        photos_dir = Path(options['photos_dir'])
        if not photos_dir.is_dir():
            raise CommandError(f'Папка с фото не найдена: {photos_dir}')

        if options['clear']:
            with transaction.atomic():
                deleted = 0
                for listing in LocalListing.objects.filter(description__startswith=DEMO_PREFIX):
                    listing.delete()  # фото-записи каскадом, файлы - сигналом post_delete
                    deleted += 1
            self.stdout.write(f'удалено: {deleted}')
            return

        cities = list(City.objects.filter(is_active=True, region__is_active=True, is_major=True)
                      .select_related('region').order_by('pk')[:5])
        if not cities:
            cities = list(City.objects.filter(is_active=True, region__is_active=True)
                          .select_related('region').order_by('pk')[:5])
        if not cities:
            raise CommandError('Нет городов в БД: сначала seed_regions.')

        credits = _read_credits(photos_dir)
        created = existed = photos = 0
        with transaction.atomic():
            seller = self._seller()
            for i, spec in enumerate(DEMO_CARS):
                listing, is_new = self._listing(seller, spec, cities[i % len(cities)], photos_dir, credits)
                created += is_new
                existed += not is_new
                if not listing.images.exists():
                    photos += self._photos(listing, photos_dir, spec[0])
        self.stdout.write(f'создано: {created}, было: {existed}, фото: {photos}')

    def _seller(self):
        user_model = get_user_model()
        user = user_model.objects.filter(email=DEMO_EMAIL).first()
        if user is None:
            user = user_model.objects.create_user(
                email=DEMO_EMAIL, password=get_random_string(32), first_name='Демо', last_name='Продавець',
                is_email_verified=True, verified_phone=DEMO_PHONE, phone_verified_at=timezone.now(),
            )
        return user

    def _listing(self, seller, spec, city, photos_dir, credits):
        slug, make, model, year, mileage, cc, fuel, gearbox, body, price, currency, note = spec
        existing = LocalListing.objects.filter(owner=seller, make=make, model=model, year=year).first()
        if existing is not None:
            return existing, False
        links = [
            f'{credits[name][1]} ({credits[name][0]})'
            for name in (f'{slug}-1.jpg', f'{slug}-2.jpg') if name in credits
        ]
        description = (
            f'{DEMO_PREFIX} Тестове оголошення, фото: Wikimedia Commons, ліцензія в CREDITS. '
            f'{note}'.strip()
        )
        if links:
            description += '\nДжерело фото: ' + '; '.join(links)
        now = timezone.now()
        listing = LocalListing.objects.create(
            owner=seller, make=make, model=model, year=year, mileage_km=mileage, engine_cc=cc,
            fuel_type=fuel, transmission=gearbox, body_type=body, condition=L.Condition.USED,
            price=Decimal(price), currency=currency, price_type=L.PriceType.NEGOTIABLE,
            region=city.region, city=city, description=description, status=L.Status.ACTIVE,
            seller_type=L.SellerType.PRIVATE, contact_phone=seller.verified_phone or DEMO_PHONE,
            moderated_at=now, agreed_to_rules=True, agreed_to_rules_at=now,
            legal_confirmed=True, legal_confirmed_at=now,
        )
        return listing, True

    def _photos(self, listing, photos_dir, slug) -> int:
        max_bytes = max_bytes_from_setting('LOCAL_LISTING_PHOTO_MAX_SIZE_MB')
        max_side = int(settings.LOCAL_LISTING_PHOTO_MAX_SIDE)
        thumb_side = int(settings.LOCAL_LISTING_THUMB_MAX_SIDE)
        count = 0
        for n in (1, 2):
            path = photos_dir / f'{slug}-{n}.jpg'
            if not path.is_file():
                continue
            try:
                with open(path, 'rb') as fh:
                    f = File(fh, name=path.name)
                    content = sanitize_image(f, max_bytes=max_bytes, max_side=max_side)
                thumb = make_thumbnail(content, max_side=thumb_side)
            except ImageUploadError as exc:
                raise CommandError(f'{path.name}: {exc}') from exc
            LocalListingImage.objects.create(
                listing=listing, image=content, thumbnail=thumb, is_primary=(count == 0),
            )
            count += 1
        return count
