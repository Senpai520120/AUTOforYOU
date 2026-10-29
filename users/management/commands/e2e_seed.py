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

E2E_SITE_SETTINGS = {
    'owner_legal_form': 'fop',
    'owner_legal_name': f'{E2E_PREFIX} Тестовий Власник',
    'owner_code': '1234567890',
    'owner_address': 'м. Київ, вул. Тестова, 1',
    'support_email': 'support@e2e.test',
    'privacy_email': 'privacy@e2e.test',
    'phone': '+380500000000',
    'telegram_channel_url': 'https://t.me/e2e_channel',
    'partner_name': f'{E2E_PREFIX} Партнер',
    'legal_docs_approved': True,
    'legal_docs_updated_at': date(2026, 10, 1),
    'legal_docs_version': '2026-10-01',
}

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
            self._site_settings()
            self._leads(users['buyer'])
            self._ua_delivery_and_broker()
            self._content()
            self._landings()

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
        # Событие с фото (задача 1.10): проверка приватной отдачи на реальном файле.
        from shipments.models import TrackingEvent

        if not TrackingEvent.objects.filter(shipment=shipment).exclude(photo='').exclude(photo=None).exists():
            data = self._photo_bytes(FIXTURE_PHOTOS[0])
            if data:
                event = TrackingEvent(shipment=shipment, status=shipment.status, note=f'{E2E_PREFIX} Фото в порту')
                event.photo.save('e2e-port.jpg', ContentFile(data), save=True)

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

    def _leads(self, buyer):
        """Заявки для кабинета брокера (2.4): клиент buyer с UTM tiktok и заявка с вредным utm_campaign."""
        from unittest import mock

        from leads.models import Lead
        from leads.services import create_lead

        spec = (
            (f'{E2E_PREFIX} Клієнт брокера', buyer,
             {'source': 'tiktok', 'medium': 'cpc', 'campaign': 'spring'}, '@e2e_client'),
            (f'{E2E_PREFIX} Гість XSS', None,
             {'source': 'xss-src', 'campaign': '<script>window.__xss=1</script>'}, ''),
        )
        for name, user, utm, handle in spec:
            created = not Lead.objects.filter(name=name).exists()
            if created:
                data = {'name': name, 'phone': '0671234567', 'source': 'landing',
                        'contact_method': 'telegram' if handle else 'phone', 'contact_handle': handle,
                        'comment': '' if handle else '<img src=x onerror=window.__xss=2>',
                        'vehicle_label': f'{E2E_PREFIX} Toyota RAV4'}
                # Без уведомлений брокеру: сид не должен слать в Telegram.
                with mock.patch('leads.services.transaction.on_commit'):
                    lead = create_lead(user=user, data=data)
                # Вредное значение кладём напрямую: clean_attribution его бы отсёк, а тест проверяет экранирование.
                Lead.objects.filter(pk=lead.pk).update(utm=utm)
            self._note('leads', created)

    def _ua_delivery_and_broker(self):
        """Демо-строки для calculator-ua-delivery.spec.ts (2.7): только e2e, не проверены (is_demo)."""
        from datetime import date
        from decimal import Decimal

        from pricing.models import BrokerServiceFee, UaDeliveryRate

        start = date(2000, 1, 1)
        _, created = UaDeliveryRate.objects.get_or_create(
            destination='[E2E] Київ', eu_port='', valid_from=start, defaults={'cost_usd': Decimal('300')})
        self._note('ua_delivery_rate', created)
        _, created = UaDeliveryRate.objects.get_or_create(
            destination='[E2E] Ужгород', eu_port='', valid_from=start, defaults={'quote_on_request': True})
        self._note('ua_delivery_rate', created)
        _, created = BrokerServiceFee.objects.get_or_create(
            title='[E2E] Послуги брокера', valid_from=start, defaults={'amount_usd': Decimal('500')})
        self._note('broker_service_fee', created)

    def _content(self):
        """Активные записи для trust-pages.spec.ts (2.13); чернетки из миграции остаются неактивными."""
        from content.models import FaqItem, ImportStep

        for order, title in enumerate(('[E2E] Етап перший', '[E2E] Етап другий', '[E2E] Етап третій'), start=1):
            _, created = ImportStep.objects.get_or_create(
                title=title, defaults={'order': order, 'description': f'[E2E] Опис етапу {order}', 'is_active': True})
            self._note('import_step', created)
        for order, (question, on_calc) in enumerate((('[E2E] Питання для сторінки?', False),
                                                      ('[E2E] Питання для калькулятора?', True)), start=1):
            _, created = FaqItem.objects.get_or_create(
                question=question,
                defaults={'order': order, 'answer': f'[E2E] Відповідь {order}', 'is_active': True,
                          'show_on_calculator': on_calc})
            self._note('faq_item', created)

    def _landings(self):
        """Страницы моделей для landing.spec.ts (2.16): опубликованная с расчётом и черновик без цены.

        Расчёт берётся из ставок, которые засеяли seed_rates / seed_auction_fees выше: цифр здесь нет.
        """
        from decimal import Decimal

        from landings.models import ModelLandingPage
        from landings.services import can_publish

        inputs = {
            'year_from': 2015, 'year_to': 2020, 'calc_year': 2018, 'auction_price_usd': Decimal('5000'),
            'fuel_type': 'petrol', 'engine_cc': 2000, 'auction': 'copart', 'auction_location': 'general',
            'us_port': 'houston', 'eu_port': 'klaipeda',
        }
        texts = {
            'intro': f'{E2E_PREFIX} Вступ сторінки моделі.',
            'included_text': f'{E2E_PREFIX} Аукціонний збір, доставка, розмитнення.',
            'typical_term_text': f'{E2E_PREFIX} 2-3 місяці',
        }
        page, created = ModelLandingPage.objects.get_or_create(
            slug='e2e-toyota-camry',
            defaults={'make': E2E_PREFIX, 'model': 'Toyota Camry', 'sort_order': 9990, **inputs, **texts})
        self._note('landing_page', created)
        if created and can_publish(page):
            page.is_published = True
            page.save()
        draft, created = ModelLandingPage.objects.get_or_create(
            slug='e2e-draft', defaults={'make': E2E_PREFIX, 'model': 'Чернетка', 'sort_order': 9991})
        self._note('landing_page', created)

    def _site_settings(self):
        """Реквизиты и документы для legal.spec.ts (синглтон pk=1)."""
        from site_settings.models import SiteSettings

        obj = SiteSettings.load()
        for field, value in E2E_SITE_SETTINGS.items():
            setattr(obj, field, value)
        obj.save()
        self._note('site_settings', False)
