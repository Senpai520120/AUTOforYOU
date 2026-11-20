"""Задача 10.23 (F1, F4): телефон объявления = подтверждённый номер владельца; /unlink сбрасывает подтверждение."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import Update
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from tests.factories import auth_client, make_local_listing, make_moderator, make_region_city, make_staff, make_user
from users.models import CustomUser

from .models import ContactView, LocalListing

VERIFIED = '+380671234567'
OTHER = '+380501112233'
TG = 424242


def _verified_user(**kw):
    return make_user(verified_phone=VERIFIED, phone_verified_at=timezone.now(), **kw)


@override_settings(PHONE_VERIFICATION_REQUIRED=True)
class TestVerifiedPhoneOnListing(APITestCase):
    LIST_URL = '/api/v1/local/listings/'

    def setUp(self):
        cache.clear()
        self.region, self.city = make_region_city()

    def payload(self, **extra):
        data = {
            'make': 'Skoda', 'model': 'Fabia', 'year': 2015, 'mileage_km': 100000, 'price': '5000',
            'currency': 'USD', 'fuel_type': 'petrol', 'transmission': 'manual', 'body_type': 'hatchback',
            'condition': 'used', 'region': self.region.pk, 'city': self.city.pk, 'description': 'Тест',
            'agreed_to_rules': True, 'legal_confirmed': True,
        }
        data.update(extra)
        return data

    def test_create_ignores_client_phone_and_uses_verified(self):
        user = _verified_user()
        resp = auth_client(user).post(self.LIST_URL, self.payload(contact_phone=OTHER), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(LocalListing.objects.get(owner=user).contact_phone, VERIFIED)

    def test_create_without_phone_field_uses_verified(self):
        user = _verified_user()
        resp = auth_client(user).post(self.LIST_URL, self.payload(), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(LocalListing.objects.get(owner=user).contact_phone, VERIFIED)

    def test_create_unverified_is_403_nothing_created(self):
        resp = auth_client(make_user()).post(self.LIST_URL, self.payload(contact_phone=OTHER), format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(LocalListing.objects.exists())

    def test_create_serializer_rejects_unverified_with_hint(self):
        # Страховка за правом 4.10: даже если право отключить, сериализатор не примет номер без подтверждения.
        from rest_framework.test import APIRequestFactory

        from .serializers import LocalListingCreateSerializer
        request = APIRequestFactory().post(self.LIST_URL)
        request.user = make_user()
        ser = LocalListingCreateSerializer(data=self.payload(contact_phone=OTHER), context={'request': request})
        self.assertFalse(ser.is_valid())
        self.assertIn('Telegram', ser.errors['contact_phone'][0])

    def test_admin_seed_keeps_client_phone(self):
        admin = make_staff(superuser=True)
        resp = auth_client(admin).post(self.LIST_URL, self.payload(contact_phone=OTHER), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(LocalListing.objects.get(owner=admin).contact_phone, OTHER)

    def test_moderator_staff_not_exempt_in_serializer(self):
        # is_staff модератора не даёт права публиковать непроверенный номер (сериализатор, без права 4.10)
        from rest_framework.test import APIRequestFactory

        from .serializers import LocalListingCreateSerializer
        request = APIRequestFactory().post(self.LIST_URL)
        request.user = make_moderator()
        ser = LocalListingCreateSerializer(data=self.payload(contact_phone=OTHER), context={'request': request})
        self.assertFalse(ser.is_valid())
        self.assertIn('Telegram', ser.errors['contact_phone'][0])

    def test_patch_ignores_client_phone_for_verified_owner(self):
        user = _verified_user()
        listing = make_local_listing(user, contact_phone=OTHER)
        resp = auth_client(user).patch(f'{self.LIST_URL}{listing.pk}/', {'contact_phone': '+380991119999'},
                                       format='json')
        self.assertEqual(resp.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.contact_phone, VERIFIED)

    def test_patch_garbage_phone_ignored_for_verified_owner(self):
        user = _verified_user()
        listing = make_local_listing(user, contact_phone=OTHER)
        resp = auth_client(user).patch(f'{self.LIST_URL}{listing.pk}/', {'contact_phone': 'abc'}, format='json')
        self.assertEqual(resp.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.contact_phone, VERIFIED)

    def test_moderator_patch_uses_owner_phone_not_moderator_phone(self):
        owner = _verified_user()
        listing = make_local_listing(owner, contact_phone=OTHER)
        moderator = make_moderator()
        CustomUser.objects.filter(pk=moderator.pk).update(verified_phone='+380930000000',
                                                          phone_verified_at=timezone.now())
        moderator.refresh_from_db()
        resp = auth_client(moderator).patch(f'{self.LIST_URL}{listing.pk}/', {'description': 'Нове'}, format='json')
        self.assertEqual(resp.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.contact_phone, VERIFIED)

    def test_edit_to_pending_without_verified_phone_is_400(self):
        user = make_user()  # подтверждение снято (/unlink)
        listing = make_local_listing(user, status=LocalListing.Status.REJECTED, contact_phone=OTHER)
        resp = auth_client(user).patch(f'{self.LIST_URL}{listing.pk}/', {'description': 'Виправлено'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Telegram', resp.json()['contact_phone'][0])
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.REJECTED)

    def test_edit_to_pending_with_verified_phone_ok(self):
        user = _verified_user()
        listing = make_local_listing(user, status=LocalListing.Status.REJECTED, contact_phone=OTHER)
        resp = auth_client(user).patch(f'{self.LIST_URL}{listing.pk}/', {'description': 'Виправлено'}, format='json')
        self.assertEqual(resp.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.PENDING)

    def test_hide_without_verified_phone_still_allowed(self):
        user = make_user()
        listing = make_local_listing(user, contact_phone=OTHER)
        resp = auth_client(user).patch(f'{self.LIST_URL}{listing.pk}/', {'status': 'hidden'}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_patch_anonymous_401_and_stranger_403(self):
        listing = make_local_listing(_verified_user(), contact_phone=OTHER)
        url = f'{self.LIST_URL}{listing.pk}/'
        self.assertEqual(APIClient().patch(url, {'description': 'x'}, format='json').status_code, 401)
        self.assertEqual(auth_client(make_user()).patch(url, {'description': 'x'}, format='json').status_code, 403)


@override_settings(PHONE_VERIFICATION_REQUIRED=True)
class TestPhoneShownOnlyIfConfirmed(APITestCase):
    def setUp(self):
        cache.clear()

    def contact(self, listing, user=None):
        client = auth_client(user) if user else APIClient()
        return client.get(f'/api/v1/local/listings/{listing.pk}/contact/')

    def test_mismatched_stored_phone_shows_verified(self):
        owner = _verified_user()
        listing = make_local_listing(owner, contact_phone=OTHER)
        resp = self.contact(listing, make_user())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'contact_phone': VERIFIED})
        self.assertEqual(ContactView.objects.filter(listing=listing).count(), 1)  # журнал показов сохранён

    def test_unconfirmed_owner_phone_hidden(self):
        listing = make_local_listing(make_user(), contact_phone=OTHER)
        resp = self.contact(listing, make_user())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {'contact_phone': None})

    def test_public_detail_and_list_never_expose_phone(self):
        listing = make_local_listing(_verified_user(), contact_phone=OTHER)
        detail = APIClient().get(f'/api/v1/local/listings/{listing.pk}/')
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.json()['contact_phone'])
        listing_page = APIClient().get('/api/v1/local/listings/')
        self.assertEqual(listing_page.status_code, 200)
        self.assertNotIn('contact_phone', listing_page.json()['results'][0])

    def test_owner_cabinet_hides_unconfirmed_phone(self):
        owner = make_user()
        listing = make_local_listing(owner, contact_phone=OTHER)
        resp = auth_client(owner).get(f'/api/v1/local/my-listings/{listing.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.json()['contact_phone'])

    def test_contact_anonymous_401(self):
        listing = make_local_listing(_verified_user(), contact_phone=OTHER)
        self.assertEqual(self.contact(listing).status_code, 401)

    def test_non_active_listing_404(self):
        listing = make_local_listing(_verified_user(), status=LocalListing.Status.PENDING)
        self.assertEqual(self.contact(listing, make_user()).status_code, 404)

    @override_settings(PHONE_VERIFICATION_REQUIRED=False)
    def test_flag_off_keeps_stored_phone(self):
        listing = make_local_listing(make_user(), contact_phone=OTHER)
        self.assertEqual(self.contact(listing, make_user()).json(), {'contact_phone': OTHER})

    def test_admin_seeded_listing_keeps_seed_phone(self):
        listing = make_local_listing(make_staff(superuser=True), contact_phone=OTHER)
        self.assertEqual(self.contact(listing, make_user()).json(), {'contact_phone': OTHER})


@override_settings(PHONE_VERIFICATION_REQUIRED=True)
class TestUnlinkResetsPhone(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = _verified_user(telegram_id=TG)
        self.listing = make_local_listing(self.user, contact_phone=VERIFIED)

    def test_bot_unlink_resets_verification_and_hides_phone(self):
        from telegram_bot.handlers import cmd_unlink

        self.addCleanup(Update.event_type.fget.cache_clear)
        message = SimpleNamespace(from_user=SimpleNamespace(id=TG), answer=AsyncMock())
        with patch('telegram_bot.handlers.aget_text', AsyncMock(return_value='ok')):
            async_to_sync(cmd_unlink)(message)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.telegram_id)
        self.assertIsNone(self.user.verified_phone)
        self.assertIsNone(self.user.phone_verified_at)
        resp = auth_client(make_user()).get(f'/api/v1/local/listings/{self.listing.pk}/contact/')
        self.assertEqual(resp.json(), {'contact_phone': None})
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.contact_phone, VERIFIED)  # данные не удалены
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)

    def test_site_unlink_resets_verification(self):
        resp = auth_client(self.user).delete('/api/v1/telegram/link/')
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_phone)
        self.assertIsNone(self.user.phone_verified_at)

    def test_unlink_of_other_telegram_id_keeps_verification(self):
        from telegram_bot.models import unlink_telegram
        self.assertFalse(unlink_telegram(self.user.pk, only_telegram_id=TG + 1))
        self.user.refresh_from_db()
        self.assertEqual(self.user.verified_phone, VERIFIED)
        self.assertEqual(self.user.telegram_id, TG)
