import io
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.utils import timezone
from PIL import Image as PILImage
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from integrations.models import VinReport
from local_listings.models import PromotionTariff
from local_listings.tasks import expire_listings, warn_expiring_listings
from payments.models import Payment
from users.models import CustomUser

from .models import City, LocalListing, LocalListingImage, Region
from .services import approve_listing, reject_listing

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _token(user):
    return str(RefreshToken.for_user(user).access_token)


def _auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {_token(user)}')


def _make_user(email='u@test.com', **kw):
    return CustomUser.objects.create_user(email=email, password='pass', **kw)


def _make_admin(email='admin@test.com'):
    u = CustomUser.objects.create_user(email=email, password='pass')
    u.is_staff = True
    u.is_superuser = True
    u.save()
    return u


def _make_region(name='Тестова область'):
    return Region.objects.get_or_create(name=name, defaults={'slug': 'test-region'})[0]


def _make_city(region=None, name='Тестове місто'):
    if region is None:
        region = _make_region()
    return City.objects.get_or_create(region=region, slug='test-city', defaults={'name': name})[0]


def _listing_payload(region, city, **extra):
    base = {
        'make': 'Toyota', 'model': 'Camry', 'year': 2020,
        'mileage_km': 50000, 'engine_cc': 2500,
        'fuel_type': 'petrol', 'transmission': 'auto',
        'body_type': 'sedan', 'condition': 'used',
        'price': '500000', 'currency': 'UAH', 'price_type': 'fixed',
        'region': region.pk, 'city': city.pk,
        'description': 'Тест', 'contact_phone': '+380501234567',
        'agreed_to_rules': True,
    }
    base.update(extra)
    return base


def _make_listing(owner, region, city, status_val=LocalListing.Status.ACTIVE, **kw):
    defaults = dict(
        make='Toyota', model='Camry', year=2020, mileage_km=50000,
        fuel_type='petrol', transmission='auto', body_type='sedan',
        price='500000', currency='UAH', price_type='fixed',
        region=region, city=city, status=status_val, agreed_to_rules=True,
    )
    defaults.update(kw)
    return LocalListing.objects.create(owner=owner, **defaults)


# ─── Тест: нова подача → pending ──────────────────────────────────────────────

class TestLocalListingCreate(APITestCase):
    def setUp(self):
        self.user = _make_user('owner@test.com')
        self.region = _make_region()
        self.city = _make_city(self.region)
        _auth(self.client, self.user)

    def test_create_sets_pending(self):
        payload = _listing_payload(self.region, self.city)
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data['status'], 'pending')

    def test_pending_not_in_public_catalog(self):
        payload = _listing_payload(self.region, self.city)
        self.client.post('/api/v1/local/listings/', payload, format='json')
        self.client.credentials()
        r = self.client.get('/api/v1/local/listings/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 0)

    def test_create_anonymous_401(self):
        self.client.credentials()
        r = self.client.post('/api/v1/local/listings/', _listing_payload(self.region, self.city), format='json')
        self.assertEqual(r.status_code, 401)

    def test_create_without_agreed_to_rules_400(self):
        payload = _listing_payload(self.region, self.city, agreed_to_rules=False)
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, 400)

    def test_phone_not_in_list_response(self):
        payload = _listing_payload(self.region, self.city)
        self.client.post('/api/v1/local/listings/', payload, format='json')
        self.client.credentials()
        r = self.client.get('/api/v1/local/listings/')
        results = r.data.get('results', [])
        if results:
            self.assertNotIn('contact_phone', results[0])


# ─── Тест: модерація (approve / reject) ───────────────────────────────────────

class TestModerationService(APITestCase):
    def setUp(self):
        self.owner = _make_user('owner2@test.com')
        self.admin = _make_admin()
        self.region = _make_region('Модерація-область')
        self.city = _make_city(self.region, 'Модерація-місто')
        self.listing = _make_listing(
            self.owner, self.region, self.city,
            status_val=LocalListing.Status.PENDING,
        )

    def test_approve_listing_makes_active(self):
        approve_listing(self.listing, self.admin)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)
        self.assertEqual(self.listing.moderated_by, self.admin)
        self.assertIsNotNone(self.listing.moderated_at)

    def test_approved_listing_appears_in_catalog(self):
        approve_listing(self.listing, self.admin)
        r = self.client.get('/api/v1/local/listings/')
        self.assertEqual(r.data['count'], 1)

    def test_reject_listing(self):
        reject_listing(self.listing, self.admin, reason='Невірне фото')
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.REJECTED)
        self.assertEqual(self.listing.rejection_reason, 'Невірне фото')

    def test_rejection_reason_visible_to_owner(self):
        reject_listing(self.listing, self.admin, reason='Тест')
        _auth(self.client, self.owner)
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['rejection_reason'], 'Тест')

    def test_rejected_listing_hidden_from_stranger(self):
        # Раніше стороннiй бачив саме оголошення, а маскувалася тільки причина
        # відхилення. Тепер не-ACTIVE оголошення недоступне цілком.
        reject_listing(self.listing, self.admin, reason='Таємна причина')
        stranger = _make_user('stranger@test.com')
        _auth(self.client, stranger)
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(r.status_code, 404)

    def test_rejected_listing_not_in_public_catalog(self):
        reject_listing(self.listing, self.admin, reason='X')
        r = self.client.get('/api/v1/local/listings/')
        self.assertEqual(r.data['count'], 0)


# ─── Тест: ремодерація при редагуванні ────────────────────────────────────────

class TestRemoderation(APITestCase):
    def setUp(self):
        self.owner = _make_user('remod@test.com')
        self.admin = _make_admin('adm2@test.com')
        self.region = _make_region('Ремод-область')
        self.city = _make_city(self.region, 'Ремод-місто')
        self.listing = _make_listing(
            self.owner, self.region, self.city,
            status_val=LocalListing.Status.ACTIVE,
        )
        _auth(self.client, self.owner)

    def test_substantive_edit_active_returns_pending(self):
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'price': '600000'},  # price is substantive
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.PENDING)

    def test_non_substantive_edit_stays_active(self):
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'contact_phone': '+380991112233'},  # not substantive
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)

    def test_edit_rejected_returns_pending(self):
        self.listing.status = LocalListing.Status.REJECTED
        self.listing.rejection_reason = 'Стара причина'
        self.listing.save()
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'contact_phone': '+380501110000'},  # even non-substantive
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.PENDING)
        self.assertEqual(self.listing.rejection_reason, '')


# ─── Тест: ліміт оголошень ────────────────────────────────────────────────────

class TestLocalListingLimit(APITestCase):
    def setUp(self):
        self.user = _make_user('limit@test.com')
        self.region = _make_region('Лімітна область')
        self.city = _make_city(self.region, 'Лімітне місто')
        _auth(self.client, self.user)

    def test_exceeds_limit_returns_error(self):
        max_active = getattr(settings, 'LOCAL_LISTING_MAX_ACTIVE', 10)
        # fill with ACTIVE
        for i in range(max_active):
            LocalListing.objects.create(
                owner=self.user, make='Kia', model='Sportage', year=2021,
                mileage_km=10000, fuel_type='petrol', transmission='auto',
                body_type='suv', price='400000', currency='UAH',
                price_type='fixed', region=self.region, city=self.city,
                status=LocalListing.Status.ACTIVE, agreed_to_rules=True,
            )
        payload = _listing_payload(self.region, self.city, make='Honda')
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, 400)

    def test_pending_counts_toward_limit(self):
        max_active = getattr(settings, 'LOCAL_LISTING_MAX_ACTIVE', 10)
        # fill with PENDING
        for i in range(max_active):
            LocalListing.objects.create(
                owner=self.user, make='Kia', model='Sportage', year=2021,
                mileage_km=10000, fuel_type='petrol', transmission='auto',
                body_type='suv', price='400000', currency='UAH',
                price_type='fixed', region=self.region, city=self.city,
                status=LocalListing.Status.PENDING, agreed_to_rules=True,
            )
        payload = _listing_payload(self.region, self.city, make='Honda')
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertEqual(r.status_code, 400)


# ─── Тест: права власника ─────────────────────────────────────────────────────

class TestLocalListingOwnership(APITestCase):
    def setUp(self):
        self.owner = _make_user('own@test.com')
        self.other = _make_user('other@test.com')
        self.region = _make_region('Права область')
        self.city = _make_city(self.region, 'Права місто')
        self.listing = _make_listing(
            self.owner, self.region, self.city,
            status_val=LocalListing.Status.ACTIVE,
        )

    def test_owner_can_patch(self):
        _auth(self.client, self.owner)
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'contact_phone': '+380990000000'}, format='json',
        )
        self.assertEqual(r.status_code, 200)

    def test_other_user_cannot_patch(self):
        _auth(self.client, self.other)
        r = self.client.patch(
            f'/api/v1/local/listings/{self.listing.pk}/',
            {'contact_phone': '+380990000001'}, format='json',
        )
        self.assertEqual(r.status_code, 403)

    def test_other_user_cannot_delete(self):
        _auth(self.client, self.other)
        r = self.client.delete(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(r.status_code, 403)

    def test_owner_can_delete(self):
        _auth(self.client, self.owner)
        r = self.client.delete(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(r.status_code, 204)

    def test_stranger_cannot_see_pending(self):
        self.listing.status = LocalListing.Status.PENDING
        self.listing.save()
        _auth(self.client, self.other)
        r = self.client.get('/api/v1/local/listings/')
        self.assertEqual(r.data['count'], 0)


# ─── Тест: мої оголошення (кабінет) ──────────────────────────────────────────

class TestMyListings(APITestCase):
    def setUp(self):
        self.owner = _make_user('my@test.com')
        self.admin = _make_admin('adm3@test.com')
        self.region = _make_region('Мої область')
        self.city = _make_city(self.region, 'Мої місто')

    def test_my_listings_shows_all_statuses(self):
        _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.ACTIVE)
        _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.PENDING)
        _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.REJECTED)
        _auth(self.client, self.owner)
        r = self.client.get('/api/v1/local/my-listings/')
        self.assertEqual(r.status_code, 200)
        statuses = {item['status'] for item in r.data['results']}
        self.assertIn('active', statuses)
        self.assertIn('pending', statuses)
        self.assertIn('rejected', statuses)

    def test_my_listings_requires_auth(self):
        r = self.client.get('/api/v1/local/my-listings/')
        self.assertEqual(r.status_code, 401)

    def test_my_listings_only_own(self):
        other = _make_user('notmy@test.com')
        _make_listing(other, self.region, self.city)
        _auth(self.client, self.owner)
        r = self.client.get('/api/v1/local/my-listings/')
        self.assertEqual(r.data['count'], 0)


# ─── Тест: фільтри ────────────────────────────────────────────────────────────

class TestLocalListingFilters(APITestCase):
    def setUp(self):
        self.user = _make_user('filt@test.com')
        self.r1 = Region.objects.create(name='Київська область', slug='kyivska')
        self.r2 = Region.objects.create(name='Одеська область', slug='odeska')
        self.c1 = City.objects.create(region=self.r1, name='Київ', slug='kyiv')
        self.c2 = City.objects.create(region=self.r2, name='Одеса', slug='odesa')

        def _mk(region, city, fuel, price, year):
            return LocalListing.objects.create(
                owner=self.user, make='Ford', model='Focus', year=year,
                mileage_km=30000, fuel_type=fuel, transmission='manual',
                body_type='hatchback', price=price, currency='UAH',
                price_type='fixed', region=region, city=city,
                status=LocalListing.Status.ACTIVE, agreed_to_rules=True,
            )

        self.l1 = _mk(self.r1, self.c1, 'petrol', '300000', 2018)
        self.l2 = _mk(self.r2, self.c2, 'diesel', '500000', 2020)
        self.l3 = _mk(self.r1, self.c1, 'electric', '800000', 2022)

    def test_filter_by_region(self):
        r = self.client.get(f'/api/v1/local/listings/?region={self.r1.pk}')
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l1.pk, ids)
        self.assertNotIn(self.l2.pk, ids)

    def test_filter_by_fuel_type(self):
        r = self.client.get('/api/v1/local/listings/?fuel_type=diesel')
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l2.pk, ids)
        self.assertNotIn(self.l1.pk, ids)

    def test_filter_by_price_range(self):
        r = self.client.get('/api/v1/local/listings/?price_min=400000&price_max=600000')
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l2.pk, ids)
        self.assertNotIn(self.l1.pk, ids)

    def test_filter_by_year_range(self):
        r = self.client.get('/api/v1/local/listings/?year_min=2019&year_max=2021')
        ids = {item['id'] for item in r.data['results']}
        self.assertIn(self.l2.pk, ids)
        self.assertNotIn(self.l1.pk, ids)

    def test_filter_pending_not_shown(self):
        hidden = LocalListing.objects.create(
            owner=self.user, make='Opel', model='Astra', year=2017,
            mileage_km=90000, fuel_type='petrol', transmission='manual',
            body_type='hatchback', price='200000', currency='UAH',
            price_type='fixed', region=self.r1, city=self.c1,
            status=LocalListing.Status.PENDING, agreed_to_rules=True,
        )
        r = self.client.get('/api/v1/local/listings/')
        ids = {item['id'] for item in r.data['results']}
        self.assertNotIn(hidden.pk, ids)


# ─── Тест: VIN prefill ────────────────────────────────────────────────────────

class TestVinPrefill(APITestCase):
    def test_vin_prefill_from_nhtsa(self):
        mock_data = {
            'demo': False, 'provider': 'nhtsa_vpic', 'vin': '1HGCM82633A004352',
            'make': 'Honda', 'model': 'Accord', 'year': 2003,
            'engine_cc': 2354, 'fuel_type': 'petrol', 'body_class': 'Sedan',
        }
        with patch('local_listings.views.NHTSAVinDecodeProvider') as MockProv:
            MockProv.return_value.decode.return_value = mock_data
            r = self.client.get('/api/v1/local/vin-prefill/1HGCM82633A004352/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['make'], 'Honda')
        self.assertFalse(r.data['cached'])

    def test_vin_prefill_from_cache(self):
        vin = '1HGCM82633A004352'
        cached = {'demo': False, 'provider': 'nhtsa_vpic', 'vin': vin, 'make': 'Honda', 'model': 'Accord', 'year': 2003}
        VinReport.objects.create(vin=vin, provider='nhtsa_vpic', report_data=cached, demo=False)
        with patch('local_listings.views.NHTSAVinDecodeProvider') as MockProv:
            r = self.client.get(f'/api/v1/local/vin-prefill/{vin}/')
            MockProv.assert_not_called()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['cached'])

    def test_vin_too_short_returns_400(self):
        r = self.client.get('/api/v1/local/vin-prefill/SHORT/')
        self.assertEqual(r.status_code, 400)


# ─── Тест: регіони ────────────────────────────────────────────────────────────

class TestRegionsAPI(APITestCase):
    def test_regions_list(self):
        from django.core.management import call_command
        call_command('seed_regions', verbosity=0)
        r = self.client.get('/api/v1/local/regions/')
        self.assertGreaterEqual(len(r.data), 25)

    def test_cities_by_region(self):
        region = Region.objects.create(name='Тест-регіон', slug='test-reg-api')
        City.objects.create(region=region, name='Тест-місто', slug='test-city-api')
        r = self.client.get(f'/api/v1/local/regions/{region.pk}/cities/')
        self.assertEqual(len(r.data), 1)


# ─── Тест: фото оголошень ─────────────────────────────────────────────────────


def _make_image_file(name='photo.jpg', fmt='JPEG', size=(100, 100), content_type='image/jpeg'):
    buf = io.BytesIO()
    img = PILImage.new('RGB', size, color=(200, 100, 50))
    img.save(buf, format=fmt)
    buf.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, buf.read(), content_type=content_type)


class TestListingImageUpload(APITestCase):
    def setUp(self):
        self.owner = _make_user('owner@img.com')
        self.other = _make_user('other@img.com')
        self.admin = _make_admin('adm@img.com')
        region = _make_region('img-область')
        city = _make_city(region, 'img-місто')
        self.listing = _make_listing(self.owner, region, city)
        self.url = f'/api/v1/local/listings/{self.listing.pk}/images/'

    def _auth(self, user):
        _auth(self.client, user)

    def test_upload_single_image_owner(self):
        self._auth(self.owner)
        r = self.client.post(self.url, {'images': _make_image_file()}, format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.data), 1)
        self.assertTrue(r.data[0]['is_primary'])

    def test_first_image_becomes_primary(self):
        self._auth(self.owner)
        self.client.post(self.url, {'images': _make_image_file('a.jpg')}, format='multipart')
        self.client.post(self.url, {'images': _make_image_file('b.jpg')}, format='multipart')
        imgs = LocalListingImage.objects.filter(listing=self.listing)
        self.assertEqual(imgs.filter(is_primary=True).count(), 1)

    def test_upload_multiple_images(self):
        self._auth(self.owner)
        files = [_make_image_file(f'p{i}.jpg') for i in range(3)]
        r = self.client.post(self.url, {'images': files}, format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(r.data), 3)

    def test_non_owner_gets_403(self):
        self._auth(self.other)
        r = self.client.post(self.url, {'images': _make_image_file()}, format='multipart')
        self.assertEqual(r.status_code, 403)

    def test_unauthenticated_gets_401(self):
        r = self.client.post(self.url, {'images': _make_image_file()}, format='multipart')
        self.assertEqual(r.status_code, 401)

    def test_wrong_content_type_rejected(self):
        self._auth(self.owner)
        bad = _make_image_file('file.gif', fmt='GIF', content_type='image/gif')
        r = self.client.post(self.url, {'images': bad}, format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_no_files_returns_400(self):
        self._auth(self.owner)
        r = self.client.post(self.url, {}, format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_exceeding_limit_rejected(self):
        self._auth(self.owner)
        for i in range(15):
            LocalListingImage.objects.create(listing=self.listing, image=f'fake{i}.jpg')
        r = self.client.post(self.url, {'images': _make_image_file()}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertIn('ліміт', r.data['detail'])

    def test_admin_can_upload(self):
        self._auth(self.admin)
        r = self.client.post(self.url, {'images': _make_image_file()}, format='multipart')
        self.assertEqual(r.status_code, 201)


class TestListingImageDelete(APITestCase):
    def setUp(self):
        self.owner = _make_user('del_owner@img.com')
        self.other = _make_user('del_other@img.com')
        region = _make_region('del-область')
        city = _make_city(region, 'del-місто')
        self.listing = _make_listing(self.owner, region, city)
        self.img1 = LocalListingImage.objects.create(listing=self.listing, image='a.jpg', is_primary=True)
        self.img2 = LocalListingImage.objects.create(listing=self.listing, image='b.jpg', is_primary=False)

    def _url(self, img_id):
        return f'/api/v1/local/listings/{self.listing.pk}/images/{img_id}/'

    def test_delete_non_primary(self):
        _auth(self.client, self.owner)
        r = self.client.delete(self._url(self.img2.pk))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(LocalListingImage.objects.filter(pk=self.img2.pk).exists())

    def test_delete_primary_promotes_next(self):
        _auth(self.client, self.owner)
        self.client.delete(self._url(self.img1.pk))
        self.img2.refresh_from_db()
        self.assertTrue(self.img2.is_primary)

    def test_non_owner_delete_gets_403(self):
        _auth(self.client, self.other)
        r = self.client.delete(self._url(self.img1.pk))
        self.assertEqual(r.status_code, 403)


class TestListingImageSetPrimary(APITestCase):
    def setUp(self):
        self.owner = _make_user('prim_owner@img.com')
        region = _make_region('prim-область')
        city = _make_city(region, 'prim-місто')
        self.listing = _make_listing(self.owner, region, city)
        self.img1 = LocalListingImage.objects.create(listing=self.listing, image='x.jpg', is_primary=True)
        self.img2 = LocalListingImage.objects.create(listing=self.listing, image='y.jpg', is_primary=False)

    def _url(self, img_id):
        return f'/api/v1/local/listings/{self.listing.pk}/images/{img_id}/'

    def test_set_primary(self):
        _auth(self.client, self.owner)
        r = self.client.patch(self._url(self.img2.pk))
        self.assertEqual(r.status_code, 200)
        self.img1.refresh_from_db()
        self.img2.refresh_from_db()
        self.assertFalse(self.img1.is_primary)
        self.assertTrue(self.img2.is_primary)

    def test_non_owner_set_primary_gets_403(self):
        other = _make_user('prim_other@img.com')
        _auth(self.client, other)
        r = self.client.patch(self._url(self.img2.pk))
        self.assertEqual(r.status_code, 403)


# ─── Тести: термін дії та Celery-задачі ──────────────────────────────────────


def _make_tariff(code='test_renew', ttype='renew', price='49.00', days=30):
    return PromotionTariff.objects.get_or_create(
        code=code,
        defaults=dict(name=code, type=ttype, price=price, currency='UAH',
                      duration_days=days, active=True),
    )[0]


class TestExpiresAt(APITestCase):
    def setUp(self):
        self.region = _make_region('exp-обл')
        self.city = _make_city(self.region, 'exp-місто')
        self.owner = _make_user('exp@test.com')

    def test_expires_at_set_on_create(self):
        listing = _make_listing(self.owner, self.region, self.city)
        self.assertIsNotNone(listing.expires_at)
        self.assertGreater(listing.expires_at, timezone.now())

    def test_active_listing_excluded_after_expiry(self):
        listing = _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.ACTIVE)
        listing.expires_at = timezone.now() - timedelta(days=1)
        listing.save(update_fields=['expires_at'])
        # Run expire task
        expire_listings()
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.EXPIRED)

    def test_expired_not_in_catalog(self):
        listing = _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.EXPIRED)
        r = self.client.get('/api/v1/local/listings/')
        ids = [item['id'] for item in r.data['results']]
        self.assertNotIn(listing.id, ids)


class TestExpiryTasks(APITestCase):
    def setUp(self):
        self.region = _make_region('task-обл')
        self.city = _make_city(self.region, 'task-місто')
        self.owner = _make_user('task_owner@test.com')

    def test_warn_expiring_sends_once(self):
        listing = _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.ACTIVE)
        listing.expires_at = timezone.now() + timedelta(days=2)
        listing.expiry_warned = False
        listing.save(update_fields=['expires_at', 'expiry_warned'])

        warn_expiring_listings()
        listing.refresh_from_db()
        self.assertTrue(listing.expiry_warned)

        # Second run — no duplicate (flag already True)
        from notifications.models import Notification
        count_before = Notification.objects.filter(user=self.owner).count()
        warn_expiring_listings()
        count_after = Notification.objects.filter(user=self.owner).count()
        self.assertEqual(count_before, count_after)

    def test_expire_task_idempotent(self):
        listing = _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.ACTIVE)
        listing.expires_at = timezone.now() - timedelta(hours=1)
        listing.save(update_fields=['expires_at'])

        expire_listings()
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.EXPIRED)

        # Second run — stays expired, no error
        expire_listings()
        listing.refresh_from_db()
        self.assertEqual(listing.status, LocalListing.Status.EXPIRED)

    def test_warn_not_sent_for_non_active(self):
        listing = _make_listing(self.owner, self.region, self.city, status_val=LocalListing.Status.PENDING)
        listing.expires_at = timezone.now() + timedelta(days=1)
        listing.expiry_warned = False
        listing.save(update_fields=['expires_at', 'expiry_warned'])

        warn_expiring_listings()
        listing.refresh_from_db()
        self.assertFalse(listing.expiry_warned)


# ─── Тести: promote endpoint + callback ──────────────────────────────────────


class TestPromoteEndpoint(APITestCase):
    def setUp(self):
        self.owner = _make_user('promo_owner@test.com')
        self.other = _make_user('promo_other@test.com')
        region = _make_region('promo-обл')
        city = _make_city(region, 'promo-місто')
        self.listing = _make_listing(self.owner, region, city)
        self.tariff = _make_tariff()
        self.url = f'/api/v1/local/listings/{self.listing.pk}/promote/'

    def test_promote_creates_payment(self):
        _auth(self.client, self.owner)
        r = self.client.post(self.url, {'tariff': self.tariff.code}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertIn('checkout_url', r.data)
        self.assertIn('order_id', r.data)
        self.assertTrue(Payment.objects.filter(
            local_listing=self.listing,
            tariff=self.tariff,
            purpose=Payment.Purpose.LOCAL_LISTING_PROMOTE,
        ).exists())

    def test_promote_non_owner_403(self):
        _auth(self.client, self.other)
        r = self.client.post(self.url, {'tariff': self.tariff.code}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_promote_missing_tariff_400(self):
        _auth(self.client, self.owner)
        r = self.client.post(self.url, {}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_tariffs_list_public(self):
        r = self.client.get('/api/v1/local/tariffs/')
        self.assertEqual(r.status_code, 200)
        # Seeds 4 tariffs
        self.assertGreaterEqual(len(r.data), 4)


class TestCallbackAppliesTariff(APITestCase):
    def setUp(self):

        self.owner = _make_user('cb_owner@test.com')
        region = _make_region('cb-обл')
        city = _make_city(region, 'cb-місто')
        self.listing = _make_listing(self.owner, region, city, status_val=LocalListing.Status.ACTIVE)
        self.listing.expires_at = timezone.now() + timedelta(days=30)
        self.listing.save(update_fields=['expires_at'])

    def _make_callback(self, payment, liqpay_status='sandbox'):
        """Build a valid LiqPay callback payload (test keys)."""
        import base64
        import hashlib
        import json

        from django.conf import settings
        private_key = settings.LIQPAY_PRIVATE_KEY
        payload = {
            'order_id': payment.order_id,
            'status': liqpay_status,
            'payment_id': '12345',
            'amount': str(payment.amount),
            'currency': payment.currency,
        }
        data = base64.b64encode(json.dumps(payload).encode()).decode()
        sig_str = private_key + data + private_key
        signature = base64.b64encode(hashlib.sha1(sig_str.encode()).digest()).decode()
        return {'data': data, 'signature': signature}

    def _create_payment(self, tariff):
        return Payment.objects.create(
            user=self.owner,
            local_listing=self.listing,
            tariff=tariff,
            order_id=f'test-promo-{tariff.code}-cb',
            amount=tariff.price,
            currency=tariff.currency,
            purpose=Payment.Purpose.LOCAL_LISTING_PROMOTE,
        )

    def test_renew_extends_expires_at(self):
        tariff = _make_tariff('cb_renew', 'renew', '49.00', 30)
        payment = self._create_payment(tariff)
        old_expires = self.listing.expires_at
        cb = self._make_callback(payment)
        self.client.post('/api/v1/payments/liqpay/callback/', cb)
        self.listing.refresh_from_db()
        self.assertGreater(self.listing.expires_at, old_expires)

    def test_top_sets_promoted_until(self):
        tariff = _make_tariff('cb_top', 'top', '99.00', 7)
        payment = self._create_payment(tariff)
        cb = self._make_callback(payment)
        self.client.post('/api/v1/payments/liqpay/callback/', cb)
        self.listing.refresh_from_db()
        self.assertIsNotNone(self.listing.promoted_until)
        self.assertGreater(self.listing.promoted_until, timezone.now())

    def test_bump_sets_bumped_at(self):
        tariff = _make_tariff('cb_bump', 'bump', '29.00', 0)
        payment = self._create_payment(tariff)
        cb = self._make_callback(payment)
        self.client.post('/api/v1/payments/liqpay/callback/', cb)
        self.listing.refresh_from_db()
        self.assertIsNotNone(self.listing.bumped_at)

    def test_renew_revives_expired_listing(self):
        self.listing.status = LocalListing.Status.EXPIRED
        self.listing.expires_at = timezone.now() - timedelta(days=1)
        self.listing.save(update_fields=['status', 'expires_at'])
        tariff = _make_tariff('cb_renew2', 'renew', '49.00', 30)
        payment = self._create_payment(tariff)
        cb = self._make_callback(payment)
        self.client.post('/api/v1/payments/liqpay/callback/', cb)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)

    def test_duplicate_callback_idempotent(self):
        tariff = _make_tariff('cb_bump2', 'bump', '29.00', 0)
        payment = self._create_payment(tariff)
        cb = self._make_callback(payment)
        self.client.post('/api/v1/payments/liqpay/callback/', cb)
        self.listing.refresh_from_db()
        first_bumped = self.listing.bumped_at
        # Second call — payment already COMPLETED, callback ignored
        self.client.post('/api/v1/payments/liqpay/callback/', cb)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.bumped_at, first_bumped)


class TestCatalogTopSorting(APITestCase):
    def setUp(self):
        self.region = _make_region('sort-обл')
        self.city = _make_city(self.region, 'sort-місто')
        self.owner = _make_user('sort@test.com')

    def test_top_listing_appears_first(self):
        normal = _make_listing(self.owner, self.region, self.city,
                               status_val=LocalListing.Status.ACTIVE,
                               make='Звичайне')
        top = _make_listing(self.owner, self.region, self.city,
                            status_val=LocalListing.Status.ACTIVE,
                            make='Топове')
        top.promoted_until = timezone.now() + timedelta(days=7)
        top.save(update_fields=['promoted_until'])

        r = self.client.get('/api/v1/local/listings/')
        self.assertEqual(r.status_code, 200)
        ids = [item['id'] for item in r.data['results']]
        self.assertIn(top.id, ids)
        self.assertIn(normal.id, ids)
        self.assertLess(ids.index(top.id), ids.index(normal.id))


# ─── C2C-6: Захист контактів ──────────────────────────────────────────────────

class TestContactEndpoint(APITestCase):
    def setUp(self):
        self.owner = _make_user('cowner@test.com')
        self.buyer = _make_user('cbuyer@test.com')
        self.region = _make_region('Контакт-область')
        self.city = _make_city(self.region, 'Контакт-місто')
        self.listing = _make_listing(
            self.owner, self.region, self.city,
            status_val=LocalListing.Status.ACTIVE,
            contact_phone='+380501234567',
        )

    def test_phone_not_in_list(self):
        r = self.client.get('/api/v1/local/listings/')
        for item in r.data.get('results', []):
            self.assertNotIn('contact_phone', item)

    def test_phone_not_in_detail(self):
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertIsNone(r.data.get('contact_phone'))

    def test_contact_endpoint_anon_401(self):
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/contact/')
        self.assertEqual(r.status_code, 401)

    def test_contact_endpoint_auth_returns_phone(self):
        _auth(self.client, self.buyer)
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/contact/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['contact_phone'], '+380501234567')

    def test_contact_endpoint_owner_returns_own_phone(self):
        _auth(self.client, self.owner)
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/contact/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['contact_phone'], '+380501234567')

    def test_contact_endpoint_nonexistent_404(self):
        _auth(self.client, self.buyer)
        r = self.client.get('/api/v1/local/listings/99999/contact/')
        self.assertEqual(r.status_code, 404)


# ─── C2C-6: Антиспам у оголошеннях ───────────────────────────────────────────

class TestAntispamListing(APITestCase):
    def setUp(self):
        self.user = _make_user('spam@test.com')
        self.region = _make_region('Спам-область')
        self.city = _make_city(self.region, 'Спам-місто')
        _auth(self.client, self.user)

    def _post(self, description):
        payload = _listing_payload(self.region, self.city, description=description)
        return self.client.post('/api/v1/local/listings/', payload, format='json')

    def test_phone_in_description_flags_listing(self):
        r = self._post('Чудова машина, тел. +380501234567 для зв\'язку')
        self.assertEqual(r.status_code, 201)
        pk = r.data['id']
        listing = LocalListing.objects.get(pk=pk)
        self.assertTrue(listing.has_contact_in_text)
        self.assertEqual(listing.status, LocalListing.Status.PENDING)

    def test_url_in_description_flags_listing(self):
        r = self._post('Докладніше на https://olx.ua/listing/123')
        self.assertEqual(r.status_code, 201)
        listing = LocalListing.objects.get(pk=r.data['id'])
        self.assertTrue(listing.has_contact_in_text)

    def test_normal_numbers_do_not_flag(self):
        r = self._post('Рік 2020, пробіг 120000 км, двигун 2500 куб, ціна 450000 грн')
        self.assertEqual(r.status_code, 201)
        listing = LocalListing.objects.get(pk=r.data['id'])
        self.assertFalse(listing.has_contact_in_text)

    def test_year_not_flagged(self):
        r = self._post('Авто 2019 року, стан відмінний')
        self.assertEqual(r.status_code, 201)
        listing = LocalListing.objects.get(pk=r.data['id'])
        self.assertFalse(listing.has_contact_in_text)


# ─── C2C-6: Бан користувача ───────────────────────────────────────────────────

class TestBannedUser(APITestCase):
    def setUp(self):
        self.banned = _make_user('banned@test.com')
        self.region = _make_region('Бан-область')
        self.city = _make_city(self.region, 'Бан-місто')
        self.listing = _make_listing(
            self.banned, self.region, self.city,
            status_val=LocalListing.Status.ACTIVE,
        )
        self.banned.is_banned = True
        self.banned.is_active = False
        self.banned.save(update_fields=['is_banned', 'is_active'])
        LocalListing.objects.filter(
            owner=self.banned,
            status__in=[LocalListing.Status.ACTIVE, LocalListing.Status.PENDING],
        ).update(status=LocalListing.Status.HIDDEN)

    def test_banned_user_cannot_get_jwt(self):
        r = self.client.post('/api/v1/auth/token/', {
            'email': 'banned@test.com', 'password': 'pass'
        }, format='json')
        self.assertIn(r.status_code, [400, 401])

    def test_banned_user_listings_hidden(self):
        r = self.client.get('/api/v1/local/listings/')
        ids = [item['id'] for item in r.data.get('results', [])]
        self.assertNotIn(self.listing.pk, ids)

    def test_banned_user_cannot_create_listing(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(self.banned).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        payload = _listing_payload(self.region, self.city)
        r = self.client.post('/api/v1/local/listings/', payload, format='json')
        self.assertIn(r.status_code, [401, 403])


# ─── Видимість оголошень за статусом (деталь + контакт) ───────────────────────

class TestListingVisibilityByStatus(APITestCase):
    """
    Три в'ю на одну сутність раніше мали три різних правила видимості:
    список фільтрував ACTIVE, contact — ACTIVE+PENDING, а деталь не фільтрувала
    зовсім. Через це адмін-екшен «сховати оголошення» нічого не ховав.
    """

    def setUp(self):
        self.owner = _make_user('vis_owner@test.com')
        self.stranger = _make_user('vis_stranger@test.com')
        self.staff = _make_user('vis_staff@test.com', is_staff=True)
        self.region = Region.objects.create(name='Одеська', slug='odeska')
        self.city = City.objects.create(name='Одеса', slug='odesa', region=self.region)
        self.listing = _make_listing(self.owner, self.region, self.city)

    def _set_status(self, value):
        self.listing.status = value
        self.listing.save(update_fields=['status'])

    def _get_detail(self):
        return self.client.get(f'/api/v1/local/listings/{self.listing.pk}/')

    def test_anonymous_sees_only_active(self):
        for value in ['pending', 'rejected', 'hidden', 'expired', 'draft']:
            with self.subTest(status=value):
                self._set_status(value)
                self.assertEqual(self._get_detail().status_code, 404)

        self._set_status(LocalListing.Status.ACTIVE)
        self.assertEqual(self._get_detail().status_code, 200)

    def test_hidden_listing_unavailable_to_stranger(self):
        # Саме цей сценарій і має закривати адмін-екшен hide_listing.
        self._set_status(LocalListing.Status.HIDDEN)
        _auth(self.client, self.stranger)
        self.assertEqual(self._get_detail().status_code, 404)

    def test_owner_sees_own_listing_in_any_status(self):
        _auth(self.client, self.owner)
        for value in ['pending', 'rejected', 'hidden', 'expired']:
            with self.subTest(status=value):
                self._set_status(value)
                self.assertEqual(self._get_detail().status_code, 200)

    def test_staff_sees_any_listing(self):
        _auth(self.client, self.staff)
        self._set_status(LocalListing.Status.HIDDEN)
        self.assertEqual(self._get_detail().status_code, 200)

    def test_contact_not_exposed_before_moderation(self):
        # Телефон не має віддаватися, доки оголошення не пройшло модерацію.
        self._set_status(LocalListing.Status.PENDING)
        _auth(self.client, self.stranger)
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/contact/')
        self.assertEqual(r.status_code, 404)

    def test_contact_available_for_active(self):
        self._set_status(LocalListing.Status.ACTIVE)
        _auth(self.client, self.stranger)
        r = self.client.get(f'/api/v1/local/listings/{self.listing.pk}/contact/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('contact_phone', r.data)
