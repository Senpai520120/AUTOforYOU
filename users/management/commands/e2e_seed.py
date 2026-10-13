"""Сид тестовых данных для e2e (задача 0.4).

Работает только при E2E_SEED_ALLOWED=true и заданном E2E_PASSWORD.
Идемпотентна: всё создаётся через get_or_create по email / заголовку / VIN.
Все записи помечены: пользователи на @e2e.test, объявления с префиксом [E2E].
"""
import os
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

E2E_DOMAIN = '@e2e.test'
E2E_PREFIX = '[E2E]'
E2E_VIN_PREFIX = 'E2E'
E2E_CONTAINER_PREFIX = 'E2E-'

FIXTURE_PHOTOS = ('car-1.jpg', 'car-2.jpg')


def require_e2e_allowed():
    """Предохранитель: команды e2e не должны работать на проде."""
    if os.environ.get('E2E_SEED_ALLOWED', '').strip().lower() != 'true':
        raise CommandError(
            'E2E_SEED_ALLOWED не равно true: команда разрешена только для тестового стека.'
        )


class Command(BaseCommand):
    help = 'Создаёт тестовые данные для e2e (только E2E_SEED_ALLOWED=true, пароль из E2E_PASSWORD).'

    def handle(self, *args, **options):
        require_e2e_allowed()
        password = os.environ.get('E2E_PASSWORD', '')
        if not password:
            raise CommandError('E2E_PASSWORD пуст: пароль по умолчанию не предусмотрен.')

        self.created = {}
        self.existing = {}

        # Справочники для расчёта и форм (идемпотентные команды).
        with open(os.devnull, 'w') as sink:
            for name in ('seed_regions', 'seed_rates', 'seed_auction_fees'):
                call_command(name, stdout=sink)

        with transaction.atomic():
            users = self._users(password)
            self._local_listings(users['seller'])
            vehicles = self._listings(users['seller'])
            self._shipment(users['buyer'], vehicles['retail'])
            self._conversation(users['buyer'], users['seller'])

        self.stdout.write('E2E seed: сводка (создано / уже было)')
        for key in sorted(set(self.created) | set(self.existing)):
            self.stdout.write(f'  {key}: {self.created.get(key, 0)} / {self.existing.get(key, 0)}')

    def _note(self, key, created):
        bucket = self.created if created else self.existing
        bucket[key] = bucket.get(key, 0) + 1

    def _users(self, password):
        User = get_user_model()
        spec = {
            'buyer': {'role': 'buyer'},
            'seller': {'role': 'buyer'},
            'dealer': {'role': 'dealer', 'is_verified_dealer': True},
            'staff': {'role': 'buyer', 'is_staff': True},
            'broker': {'role': 'broker', 'is_staff': True},
            # самозваная роль admin без is_staff и без верификации: регресс 09-S2
            'fakeadmin': {'role': 'admin'},
        }
        result = {}
        for name, extra in spec.items():
            user, created = User.objects.get_or_create(
                email=f'{name}{E2E_DOMAIN}',
                defaults={**extra, 'is_email_verified': True},
            )
            if created:
                user.set_password(password)
                user.save()
            self._note('users', created)
            result[name] = user
        return result

    def _photo_bytes(self, name):
        path = settings.BASE_DIR / 'frontend' / 'e2e' / 'fixtures' / name
        try:
            return path.read_bytes()
        except OSError:
            self.stderr.write(f'Фото {path} не найдено, объявление создаётся без фото.')
            return None

    def _local_listings(self, seller):
        from local_listings.models import City, LocalListing, LocalListingImage, Region

        region = Region.objects.order_by('id').first()
        city = City.objects.filter(region=region).order_by('id').first() if region else None
        if not city:
            raise CommandError('Нет регионов/городов: seed_regions не отработал.')
        spec = (
            ('Skoda', 'Octavia', LocalListing.Status.ACTIVE, FIXTURE_PHOTOS[0]),
            ('Toyota', 'Camry', LocalListing.Status.PENDING, FIXTURE_PHOTOS[1]),
        )
        for make, model, status, photo in spec:
            # Заголовка у LocalListing нет: маркер [E2E] кладём в описание,
            # по нему же get_or_create и cleanup.
            marker = f'{E2E_PREFIX} {make} {model} ({status})'
            listing, created = LocalListing.objects.get_or_create(
                owner=seller, description=marker,
                defaults={
                    'make': make, 'model': model, 'year': 2018, 'mileage_km': 120000,
                    'engine_cc': 1600, 'fuel_type': 'petrol', 'transmission': 'auto',
                    'body_type': 'sedan', 'price': Decimal('9000'), 'currency': 'USD',
                    'region': region, 'city': city, 'status': status,
                    'agreed_to_rules': True,
                },
            )
            if created:
                data = self._photo_bytes(photo)
                if data:
                    img = LocalListingImage(listing=listing, is_primary=True)
                    img.image.save(f'e2e-{photo}', ContentFile(data), save=True)
            self._note('local_listings', created)

    def _listings(self, seller):
        from listings.models import Listing
        from vehicles.models import Vehicle

        result = {}
        for channel, vin, price in (
            ('retail', f'{E2E_VIN_PREFIX}RETAIL0000001', '15000'),
            ('wholesale', f'{E2E_VIN_PREFIX}WHOLESALE00001', '11000'),
        ):
            vehicle, v_created = Vehicle.objects.get_or_create(
                vin=vin,
                defaults={
                    'make': 'Toyota', 'model': f'{E2E_PREFIX} RAV4 {channel}', 'year': 2019,
                    'engine_cc': 2000, 'fuel_type': 'petrol', 'mileage_km': 60000,
                    'source_auction': 'copart', 'lot_number': f'E2E-{channel}',
                },
            )
            self._note('vehicles', v_created)
            _, l_created = Listing.objects.get_or_create(
                vehicle=vehicle, seller=seller, channel=channel,
                defaults={'price': Decimal(price), 'currency': 'USD',
                          'repair_description': f'{E2E_PREFIX} тестовый лот'},
            )
            self._note('listings', l_created)
            result[channel] = vehicle
        return result

    def _shipment(self, buyer, vehicle):
        from shipments.models import Shipment

        shipment, created = Shipment.objects.get_or_create(
            container_no=f'{E2E_CONTAINER_PREFIX}0000001',
            defaults={'vessel': f'{E2E_PREFIX} Vessel', 'status': Shipment.Status.IN_OCEAN,
                      'eta': date.today()},
        )
        shipment.vehicles.add(vehicle)
        shipment.watchers.add(buyer)
        self._note('shipments', created)

    def _conversation(self, buyer, seller):
        from local_listings.models import LocalListing
        from messaging.models import Conversation, Message

        listing = LocalListing.objects.filter(
            owner=seller, description__startswith=E2E_PREFIX,
            status=LocalListing.Status.ACTIVE,
        ).first()
        conv, created = Conversation.objects.get_or_create(initiator=buyer, local_listing=listing)
        conv.participants.add(buyer, seller)
        if created:
            Message.objects.create(conversation=conv, sender=buyer, text=f'{E2E_PREFIX} Здравствуйте!')
        self._note('conversations', created)
