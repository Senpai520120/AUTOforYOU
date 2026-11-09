"""Задача 4.10 (часть 2): подача объявления только с телефоном, подтверждённым через Telegram."""
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from tests.factories import auth_client, make_region_city, make_staff, make_user

from .models import LocalListing


@override_settings(PHONE_VERIFICATION_REQUIRED=True)
class TestPhoneRequiredForPosting(APITestCase):
    URL = '/api/v1/local/listings/'

    def setUp(self):
        self.region, self.city = make_region_city()

    def payload(self):
        return {
            'make': 'Skoda', 'model': 'Fabia', 'year': 2015, 'mileage_km': 100000, 'price': '5000',
            'currency': 'USD', 'fuel_type': 'petrol', 'transmission': 'manual', 'body_type': 'hatchback',
            'condition': 'used', 'region': self.region.pk, 'city': self.city.pk, 'description': 'Тест',
            'contact_phone': '+380501234567', 'agreed_to_rules': True,
        }

    def test_unverified_is_403_with_code_and_nothing_created(self):
        resp = auth_client(make_user()).post(self.URL, self.payload(), format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['code'], 'phone_not_verified')
        self.assertEqual(resp.json()['detail'], 'Підтвердіть телефон через Telegram, щоб подати оголошення.')
        self.assertFalse(LocalListing.objects.exists())

    def test_verified_can_post(self):
        user = make_user(verified_phone='+380671234567', phone_verified_at=timezone.now())
        resp = auth_client(user).post(self.URL, self.payload(), format='json')
        self.assertEqual(resp.status_code, 201)

    def test_staff_without_verification_can_post(self):
        resp = auth_client(make_staff()).post(self.URL, self.payload(), format='json')
        self.assertEqual(resp.status_code, 201)

    def test_anonymous_is_401(self):
        self.assertEqual(APIClient().post(self.URL, self.payload(), format='json').status_code, 401)

    def test_list_stays_public(self):
        self.assertEqual(APIClient().get(self.URL).status_code, 200)

    @override_settings(PHONE_VERIFICATION_REQUIRED=False)
    def test_flag_off_allows_unverified(self):
        resp = auth_client(make_user()).post(self.URL, self.payload(), format='json')
        self.assertEqual(resp.status_code, 201)
