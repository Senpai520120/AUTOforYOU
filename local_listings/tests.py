from unittest.mock import patch

from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from integrations.models import VinReport
from users.models import CustomUser
from .models import Region, City, LocalListing, LocalListingImage


def _token(user):
    return str(RefreshToken.for_user(user).access_token)


def _auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {_token(user)}')


def _make_user(email='u@test.com', **kw):
    return CustomUser.objects.create_user(email=email, password='pass', **kw)


def _make_region(name='Тестова область'):
    return Region.objects.get_or_create(name=name, defaults={'slug': 'test-region'})[0]


def _make_city(region=None, name='Тестове місто'):
    if region is None:
        region = _make_region()
    return City.objects.get_or_create(region=region, slug='test-city', defaults={'name': name})[0]


def _listing_payload(region, city, **extra):
    return {
        'make': 'Toyota', 'model': 'Camry', 'year': 2020,
        'mileage_km': 50000, 'engine_cc': 2500,
        'fuel_type': 'petrol', 'transmission': 'auto',
        'body_type': 'sedan', 'condition': 'used',
        'price': '500000', 'currency': 'UAH', 'price_type': 'fixed',
        'region': region.pk, 'city': city.pk,
        'description': 'Тест', 'contact_phone': '+380501234567',
        **extra,
    }


class TestLocalListingCreate(APITestCase):
    def setUp(self):
        self.user = _make_user('owner@test.com')
        self.region = _make_region()
        self.city = _make_city(self.region)
        _auth(self.client, self.user)

    def test_create_authenticated(self):
        payload = _listing_payload(self.region, self.city)
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data['make'], 'Toyota')
        self.assertEqual(r.data['status'], 'active')

    def test_create_anonymous_401(self):
        self.client.credentials()
        payload = _listing_payload(self.region, self.city)
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_phone_not_in_list_response(self):
        """contact_phone НЕ повертається у публічному списку."""
        _listing_payload_data = _listing_payload(self.region, self.city)
        self.client.post('/api/v1/local/listings/', _listing_payload_data, format='json')
        self.client.credentials()
        r = self.client.get('/api/v1/local/listings/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        results = r.data.get('results', r.data)
        if isinstance(results, list) and results:
            self.assertNotIn('contact_phone', results[0])


class TestLocalListingLimit(APITestCase):
    def setUp(self):
        self.user = _make_user('limit@test.com')
        self.region = _make_region('Лімітна область')
        self.city = _make_city(self.region, 'Лімітне місто')
        _auth(self.client, self.user)

    def test_exceeds_limit_returns_error(self):
        max_active = getattr(settings, 'LOCAL_LISTING_MAX_ACTIVE', 10)
        for i in range(max_active):
            LocalListing.objects.create(
                owner=self.user, make='Kia', model='Sportage', year=2021,
                mileage_km=10000, fuel_type='petrol', transmission='auto',
                body_type='suv', price='400000', currency='UAH',
                price_type='fixed', region=self.region, city=self.city,
                status=LocalListing.Status.ACTIVE,
            )
        payload = _listing_payload(self.region, self.city, make='Honda')
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TestLocalListingOwnership(APITestCase):
    def setUp(self):
        self.owner = _make_user('own@test.com')
        self.other = _make_user('other@test.com')
        self.region = _make_region('Права область')
        self.city = _make_city(self.region, 'Права місто')
        self.listing = LocalListing.objects.create(
            owner=self.owner, make='BMW', model='X5', year=2019,
            mileage_km=80000, fuel_type='diesel', transmission='auto',
            body_type='suv', price='1200000', currency='UAH',
            price_type='negotiable', region=self.region, city=self.city,
            status=LocalListing.Status.ACTIVE,
        )

    def test_owner_can_patch(self):
        _auth(self.client, self.owner)
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'price': '1100000'}, format='json'
        )
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_other_user_cannot_patch(self):
        _auth(self.client, self.other)
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'price': '1000000'}, format='json'
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_user_cannot_delete(self):
        _auth(self.client, self.other)
        r = self.client.delete(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_delete(self):
        _auth(self.client, self.owner)
        r = self.client.delete(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)


class TestLocalListingFilters(APITestCase):
    def setUp(self):
        self.user = _make_user('filt@test.com')
        self.r1 = Region.objects.create(name='Київська область', slug='kyivska')
        self.r2 = Region.objects.create(name='Одеська область', slug='odeska')
        self.c1 = City.objects.create(region=self.r1, name='Київ', slug='kyiv')
        self.c2 = City.objects.create(region=self.r2, name='Одеса', slug='odesa')

        def _make(region, city, fuel, price, year):
            return LocalListing.objects.create(
                owner=self.user, make='Ford', model='Focus', year=year,
                mileage_km=30000, fuel_type=fuel, transmission='manual',
                body_type='hatchback', price=price, currency='UAH',
                price_type='fixed', region=region, city=city,
                status=LocalListing.Status.ACTIVE,
            )

        self.l1 = _make(self.r1, self.c1, 'petrol', '300000', 2018)
        self.l2 = _make(self.r2, self.c2, 'diesel', '500000', 2020)
        self.l3 = _make(self.r1, self.c1, 'electric', '800000', 2022)

    def test_filter_by_region(self):
        r = self.client.get(f'/api/v1/local/listings/?region={self.r1.pk}')
        self.assertEqual(r.status_code, 200)
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l1.pk, ids)
        self.assertIn(self.l3.pk, ids)
        self.assertNotIn(self.l2.pk, ids)

    def test_filter_by_fuel_type(self):
        r = self.client.get('/api/v1/local/listings/?fuel_type=diesel')
        self.assertEqual(r.status_code, 200)
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l2.pk, ids)
        self.assertNotIn(self.l1.pk, ids)

    def test_filter_by_price_range(self):
        r = self.client.get('/api/v1/local/listings/?price_min=400000&price_max=600000')
        self.assertEqual(r.status_code, 200)
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l2.pk, ids)
        self.assertNotIn(self.l1.pk, ids)
        self.assertNotIn(self.l3.pk, ids)

    def test_filter_by_year_range(self):
        r = self.client.get('/api/v1/local/listings/?year_min=2019&year_max=2021')
        self.assertEqual(r.status_code, 200)
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l2.pk, ids)
        self.assertNotIn(self.l1.pk, ids)
        self.assertNotIn(self.l3.pk, ids)

    def test_filter_inactive_not_shown(self):
        hidden = LocalListing.objects.create(
            owner=self.user, make='Opel', model='Astra', year=2017,
            mileage_km=90000, fuel_type='petrol', transmission='manual',
            body_type='hatchback', price='200000', currency='UAH',
            price_type='fixed', region=self.r1, city=self.c1,
            status=LocalListing.Status.HIDDEN,
        )
        r = self.client.get('/api/v1/local/listings/')
        ids = {item['id'] for item in r.data['results']}
        self.assertNotIn(hidden.pk, ids)


class TestVinPrefill(APITestCase):
    def test_vin_prefill_from_nhtsa(self):
        mock_data = {
            'demo': False, 'provider': 'nhtsa_vpic', 'vin': '1HGCM82633A004352',
            'make': 'Honda', 'model': 'Accord', 'year': 2003,
            'engine_cc': 2354, 'fuel_type': 'petrol', 'body_class': 'Sedan',
        }
        with patch('local_listings.views.NHTSAVinDecodeProvider') as MockProvider:
            MockProvider.return_value.decode.return_value = mock_data
            r = self.client.get('/api/v1/local/vin-prefill/1HGCM82633A004352/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['make'], 'Honda')
        self.assertFalse(r.data['cached'])

    def test_vin_prefill_from_cache(self):
        vin = '1HGCM82633A004352'
        cached_data = {
            'demo': False, 'provider': 'nhtsa_vpic', 'vin': vin,
            'make': 'Honda', 'model': 'Accord', 'year': 2003,
        }
        VinReport.objects.create(vin=vin, provider='nhtsa_vpic', report_data=cached_data, demo=False)
        with patch('local_listings.views.NHTSAVinDecodeProvider') as MockProvider:
            r = self.client.get(f'/api/v1/local/vin-prefill/{vin}/')
            MockProvider.assert_not_called()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['cached'])
        self.assertEqual(r.data['make'], 'Honda')

    def test_vin_too_short_returns_400(self):
        r = self.client.get('/api/v1/local/vin-prefill/SHORT/')
        self.assertEqual(r.status_code, 400)


class TestRegionsAPI(APITestCase):
    def test_regions_list(self):
        from django.core.management import call_command
        call_command('seed_regions', verbosity=0)
        r = self.client.get('/api/v1/local/regions/')
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.data), 25)

    def test_cities_by_region(self):
        region = Region.objects.create(name='Тест-регіон', slug='test-reg-api')
        City.objects.create(region=region, name='Тест-місто', slug='test-city-api')
        r = self.client.get(f'/api/v1/local/regions/{region.pk}/cities/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['name'], 'Тест-місто')
