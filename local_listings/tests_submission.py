"""Задача 8.5 (бэкенд): длина описания, антиспам (email, границы слов), лимит подачи, «не в розшуку»."""
from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from tests.factories import auth_client, make_local_listing, make_region_city, make_staff, make_user

from .antispam import detect_contacts
from .models import LocalListing

URL = '/api/v1/local/listings/'


def payload(region, city, **kw):
    data = {
        'make': 'Skoda', 'model': 'Fabia', 'year': 2015, 'mileage_km': 100000, 'price': '5000',
        'currency': 'USD', 'fuel_type': 'petrol', 'transmission': 'manual', 'body_type': 'hatchback',
        'condition': 'used', 'region': region.pk, 'city': city.pk, 'description': 'Гарний стан',
        'contact_phone': '+380501234567', 'agreed_to_rules': True, 'legal_confirmed': True,
    }
    data.update(kw)
    return data


def rates(**changes):
    return mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', {**SimpleRateThrottle.THROTTLE_RATES, **changes})


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.region, self.city = make_region_city()
        self.user = make_user()
        self.client = auth_client(self.user)

    def post(self, client=None, **kw):
        return (client or self.client).post(URL, payload(self.region, self.city, **kw), format='json')


class TestDescriptionLength(Base):
    @override_settings(LOCAL_LISTING_DESCRIPTION_MAX=20)
    def test_create_limit(self):
        self.assertEqual(self.post(description='я' * 20).status_code, 201)
        resp = self.post(description='я' * 21)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('description', resp.json())

    @override_settings(LOCAL_LISTING_DESCRIPTION_MAX=20)
    def test_patch_limit(self):
        listing = make_local_listing(self.user)
        url = f'{URL}{listing.pk}/'
        self.assertEqual(self.client.patch(url, {'description': 'я' * 21}, format='json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'description': 'я' * 20}, format='json').status_code, 200)

    @override_settings(LOCAL_LISTING_DESCRIPTION_MAX=777)
    def test_config_exposes_max(self):
        self.assertEqual(APIClient().get('/api/v1/local/config/').json()['description_max'], 777)


class TestAntispam(Base):
    def test_detection_cases(self):
        caught = {
            'ivan@mail.ua': 'email', 'пишіть ivan.petrenko@gmail.com': 'email',
            'tg: @seller': 'messenger', 'Viber 0991234567': 'messenger', 't.me/someone': 'messenger',
        }
        for text, kind in caught.items():
            with self.subTest(text=text):
                self.assertIn(kind, detect_contacts(text))
        self.assertNotIn('url', detect_contacts('ivan@mail.ua'))  # email не дублируется ссылкой
        clean = [
            'потужний мотор, 2.0 TDI', 'ватсапп-група не потрібна', 'Рік 2015, пробіг 180000 км, ціна 8500',
            'обʼєм 1998 см3', 'телеграмний стиль не про нас', 'stg: нормальний стан',
        ]
        for text in clean:
            with self.subTest(text=text):
                self.assertEqual(detect_contacts(text), [])

    @override_settings(ANTISPAM_MODE='hard')
    def test_hard_mode_email_is_400_with_type(self):
        resp = self.post(description='Пишіть на ivan@mail.ua')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('(email)', str(resp.json()['description']))
        self.assertFalse(LocalListing.objects.exists())

    @override_settings(ANTISPAM_MODE='soft')
    def test_soft_mode_flags(self):
        self.assertEqual(self.post(description='Пишіть на ivan@mail.ua').status_code, 201)
        self.assertTrue(LocalListing.objects.get().has_contact_in_text)

    @override_settings(ANTISPAM_MODE='off')
    def test_off_mode_ignores(self):
        self.assertEqual(self.post(description='Пишіть на ivan@mail.ua').status_code, 201)
        self.assertFalse(LocalListing.objects.get().has_contact_in_text)


class TestCreateThrottle(Base):
    @override_settings(LOCAL_LISTING_MAX_ACTIVE=0)
    def test_hourly_limit_third_is_429_with_retry_after(self):
        with rates(listing_create='2/hour'):
            for _ in range(2):
                self.assertEqual(self.post().status_code, 201)
            resp = self.post()
            self.assertEqual(resp.status_code, 429)
            self.assertEqual(resp.json()['detail'], 'Забагато нових оголошень. Спробуйте пізніше')
            self.assertIn('Retry-After', resp)
            self.assertEqual(APIClient().get(URL).status_code, 200)  # каталог не ограничен
            other = auth_client(make_user())
            self.assertEqual(self.post(client=other).status_code, 201)  # лимит на пользователя

    @override_settings(LOCAL_LISTING_MAX_ACTIVE=0)
    def test_daily_limit(self):
        with rates(listing_create='100/hour', listing_create_daily='3/day'):
            for _ in range(3):
                self.assertEqual(self.post().status_code, 201)
            self.assertEqual(self.post().status_code, 429)

    @override_settings(LOCAL_LISTING_MAX_ACTIVE=0)
    def test_staff_not_limited(self):
        staff = auth_client(make_staff())
        with rates(listing_create='1/hour'):
            for _ in range(3):
                self.assertEqual(self.post(client=staff).status_code, 201)


class TestLegalConfirmed(Base):
    def test_missing_or_false_is_400(self):
        for value in (None, False):
            with self.subTest(value=value):
                data = payload(self.region, self.city)
                if value is None:
                    data.pop('legal_confirmed')
                else:
                    data['legal_confirmed'] = value
                resp = self.client.post(URL, data, format='json')
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.json()['legal_confirmed'],
                                 ['Підтвердіть, що авто не в розшуку, не в заставі, документи в наявності.'])
        self.assertFalse(LocalListing.objects.exists())

    def test_true_is_saved_with_time(self):
        self.assertEqual(self.post().status_code, 201)
        listing = LocalListing.objects.get()
        self.assertTrue(listing.legal_confirmed)
        self.assertIsNotNone(listing.legal_confirmed_at)

    def test_patch_does_not_require_it(self):
        listing = make_local_listing(self.user)
        resp = self.client.patch(f'{URL}{listing.pk}/', {'mileage_km': 1}, format='json')
        self.assertEqual(resp.status_code, 200)

    def test_old_listing_without_confirmation_still_in_catalog(self):
        listing = make_local_listing(make_user())
        self.assertFalse(listing.legal_confirmed)
        ids = [row['id'] for row in APIClient().get(URL).json()['results']]
        self.assertIn(listing.pk, ids)
