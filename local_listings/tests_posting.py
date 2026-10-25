"""Подача C2C-объявлений и флаги (задача 6.7): CanPostLocalListing, матрица флагов x ролей, цена в одной валюте."""
import io
from decimal import Decimal

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import URLPattern
from django.utils import timezone
from PIL import Image as PILImage
from rest_framework import status
from rest_framework.request import Request
from rest_framework.test import APIClient

from local_listings import urls as local_urls
from local_listings.models import LocalListing, price_to_usd
from local_listings.permissions import POSTING_CLOSED_DETAIL, CanPostLocalListing
from local_listings.tests import _listing_payload
from pricing.models import ExchangeRate
from tests.factories import auth_client, make_admin_role, make_local_listing, make_region_city, make_staff, make_user
from tests.test_uploads import use_temp_media

CLOSED = dict(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=False)
OPEN = dict(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=True)
OFF = dict(C2C_ENABLED=False, C2C_PUBLIC_POSTING_ENABLED=True)
LIST_URL = '/api/v1/local/listings/'


def _png():
    buf = io.BytesIO()
    PILImage.new('RGB', (40, 30), (10, 120, 200)).save(buf, format='JPEG')
    return SimpleUploadedFile('p.jpg', buf.getvalue(), content_type='image/jpeg')


class _Roles(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region, cls.city = make_region_city()
        cls.buyer = make_user()
        cls.staff = make_staff()
        cls.admin_role = make_admin_role()

    def setUp(self):
        use_temp_media(self)

    def payload(self, **extra):
        return _listing_payload(self.region, self.city, **extra)


class TestPostingMatrix(_Roles):
    """C2C_ENABLED x C2C_PUBLIC_POSTING_ENABLED x роль (аноним, buyer, staff, роль admin)."""

    def test_create_when_posting_closed(self):
        with override_settings(**CLOSED):
            self.assertEqual(APIClient().post(LIST_URL, self.payload(), format='json').status_code, 401)
            resp = auth_client(self.buyer).post(LIST_URL, self.payload(), format='json')
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(resp.json(), {'detail': POSTING_CLOSED_DETAIL})
            self.assertFalse(LocalListing.objects.exists())
            self.assertEqual(auth_client(self.staff).post(LIST_URL, self.payload(), format='json').status_code, 201)
            self.assertEqual(
                auth_client(self.admin_role).post(LIST_URL, self.payload(), format='json').status_code, 201)

    def test_create_when_posting_open(self):
        with override_settings(**OPEN):
            resp = auth_client(self.buyer).post(LIST_URL, self.payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_everything_404_when_section_off(self):
        listing = make_local_listing(self.buyer)
        with override_settings(**OFF):
            for who in (None, self.buyer, self.staff):
                client = APIClient() if who is None else auth_client(who)
                for method, url in (('get', LIST_URL), ('post', LIST_URL), ('get', f'{LIST_URL}{listing.pk}/'),
                                    ('patch', f'{LIST_URL}{listing.pk}/'), ('post', f'{LIST_URL}{listing.pk}/images/')):
                    with self.subTest(who=who, method=method, url=url):
                        self.assertEqual(getattr(client, method)(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_catalog_and_card_readable_by_all_when_posting_closed(self):
        listing = make_local_listing(self.buyer)
        with override_settings(**CLOSED):
            for who in (None, self.buyer, self.staff):
                client = APIClient() if who is None else auth_client(who)
                with self.subTest(who=who):
                    self.assertEqual(client.get(LIST_URL).status_code, status.HTTP_200_OK)
                    self.assertEqual(client.get(f'{LIST_URL}{listing.pk}/').status_code, status.HTTP_200_OK)

    def test_owner_cannot_edit_or_delete_own_when_posting_closed_but_staff_can(self):
        listing = make_local_listing(self.buyer)
        url = f'{LIST_URL}{listing.pk}/'
        with override_settings(**CLOSED):
            self.assertEqual(auth_client(self.buyer).patch(url, {'description': 'x'}, format='json').status_code, 403)
            self.assertEqual(auth_client(self.buyer).delete(url).status_code, 403)
            own = make_local_listing(self.staff)  # правка чужого - отдельное право moderate_locallisting, не про подачу
            resp = auth_client(self.staff).patch(f'{LIST_URL}{own.pk}/', {'description': 'new'}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_photo_upload_and_delete_when_posting_closed(self):
        listing = make_local_listing(self.staff)
        url = f'{LIST_URL}{listing.pk}/images/'
        with override_settings(**CLOSED):
            self.assertEqual(APIClient().post(url).status_code, 401)
            resp = auth_client(self.buyer).post(url, {'images': _png()}, format='multipart')
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
            resp = auth_client(self.staff).post(url, {'images': _png()}, format='multipart')
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
            img_id = resp.json()[0]['id']
            img_url = f'{url}{img_id}/'
            self.assertEqual(auth_client(self.buyer).delete(img_url).status_code, 403)
            self.assertEqual(auth_client(self.staff).delete(img_url).status_code, 204)

    def test_photo_upload_when_posting_open_owner_201(self):
        listing = make_local_listing(self.buyer)
        with override_settings(**OPEN):
            resp = auth_client(self.buyer).post(f'{LIST_URL}{listing.pk}/images/', {'images': _png()}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_vin_prefill_closed_for_buyer_and_anon_when_posting_closed(self):
        url = '/api/v1/local/vin-prefill/SHORT/'
        with override_settings(**CLOSED):
            self.assertEqual(APIClient().get(url).status_code, 401)
            resp = auth_client(self.buyer).get(url)
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(resp.json(), {'detail': POSTING_CLOSED_DETAIL})
        with override_settings(**OPEN):
            self.assertEqual(APIClient().get(url).status_code, 400)  # короткий VIN: логика view, без сети


class TestContact(_Roles):
    def test_anonymous_401_authenticated_200_inactive_404(self):
        active = make_local_listing(self.buyer, contact_phone='+380501112233')
        pending = make_local_listing(self.buyer, status=LocalListing.Status.PENDING, contact_phone='+380501112244')
        with override_settings(**CLOSED):
            url = f'{LIST_URL}{active.pk}/contact/'
            self.assertEqual(APIClient().get(url).status_code, 401)
            resp = auth_client(make_user()).get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json(), {'contact_phone': '+380501112233'})
            self.assertEqual(auth_client(make_user()).get(f'{LIST_URL}{pending.pk}/contact/').status_code, 404)

    def test_contact_has_no_posting_permission(self):
        from local_listings.views import LocalListingContactView
        self.assertNotIn(CanPostLocalListing, LocalListingContactView.permission_classes)


class TestEveryWriteEndpointHasPostingPermission(TestCase):
    """Новый write-эндпоинт без CanPostLocalListing валит тест. Не-write и promote перечислены явно."""

    NOT_POSTING = {
        'local-listing-contact', 'local-listing-promote', 'local-my-listings', 'local-tariffs',
        'local-regions', 'local-cities', 'local-vin-prefill',  # vin-prefill проверяет posting_allowed внутри get()
    }
    WRITE_VIEWS = {
        'local-listing-list': 'post', 'local-listing-detail': 'patch', 'local-listing-images': 'post',
        'local-listing-image-detail': 'delete',
    }

    def _permission_classes(self, pattern, method):
        view_cls = pattern.callback.cls
        view = view_cls()
        view.request = Request(getattr(RequestFactory(), method)('/'))
        return [type(p) for p in view.get_permissions()]

    def test_all_write_views_use_the_permission(self):
        names = set()
        for pattern in local_urls.urlpatterns:
            assert isinstance(pattern, URLPattern)
            names.add(pattern.name)
            if pattern.name in self.NOT_POSTING:
                continue
            with self.subTest(name=pattern.name):
                self.assertIn(pattern.name, self.WRITE_VIEWS)
                self.assertIn(CanPostLocalListing, self._permission_classes(pattern, self.WRITE_VIEWS[pattern.name]))
        self.assertEqual(names, self.NOT_POSTING | set(self.WRITE_VIEWS))

    def test_get_on_list_view_has_no_posting_permission(self):
        pattern = next(p for p in local_urls.urlpatterns if p.name == 'local-listing-list')
        self.assertNotIn(CanPostLocalListing, self._permission_classes(pattern, 'get'))


class TestPricesInOneCurrency(TestCase):
    """05-Q3: фильтр и сортировка по цене - по сумме в USD (курс на момент сохранения), без конвертации на лету."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user()

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        ExchangeRate.objects.create(
            from_currency='UAH', to_currency='USD', rate=Decimal('0.025'), date=timezone.localdate())
        ExchangeRate.objects.create(
            from_currency='EUR', to_currency='USD', rate=Decimal('1.10'), date=timezone.localdate())
        cache.clear()
        # 400000 UAH = 10000 USD; 12000 USD; 9000 EUR = 9900 USD
        self.uah = make_local_listing(self.owner, price='400000', currency='UAH')
        self.usd = make_local_listing(self.owner, price='12000', currency='USD')
        self.eur = make_local_listing(self.owner, price='9000', currency='EUR')

    def _ids(self, query):
        resp = APIClient().get(f'{LIST_URL}?{query}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [item['id'] for item in resp.json()['results']]

    def test_price_usd_is_normalized_on_save(self):
        self.uah.refresh_from_db()
        self.eur.refresh_from_db()
        self.assertEqual(self.uah.price_usd, Decimal('10000.00'))
        self.assertEqual(self.eur.price_usd, Decimal('9900.00'))

    def test_sort_by_price_is_by_usd_amount(self):
        self.assertEqual(self._ids('ordering=price'), [self.eur.pk, self.uah.pk, self.usd.pk])
        self.assertEqual(self._ids('ordering=-price'), [self.usd.pk, self.uah.pk, self.eur.pk])

    def test_range_filter_is_by_usd_amount(self):
        self.assertCountEqual(self._ids('price_min=9950&price_max=11000'), [self.uah.pk])
        self.assertCountEqual(self._ids('price_min=11000'), [self.usd.pk])

    def test_listing_without_rate_is_excluded_from_price_filter_and_sorted_last(self):
        ExchangeRate.objects.all().delete()
        cache.clear()
        norate = make_local_listing(self.owner, price='1', currency='UAH')
        self.assertIsNone(LocalListing.objects.get(pk=norate.pk).price_usd)
        self.assertNotIn(norate.pk, self._ids('price_max=100000'))
        self.assertEqual(self._ids('ordering=price')[-1], norate.pk)

    def test_resave_with_update_fields_refreshes_usd(self):
        self.uah.price = Decimal('800000')
        self.uah.save(update_fields=['price'])
        self.uah.refresh_from_db()
        self.assertEqual(self.uah.price_usd, Decimal('20000.00'))

    def test_inverse_rate_is_used_when_only_usd_to_x_exists(self):
        ExchangeRate.objects.all().delete()
        ExchangeRate.objects.create(
            from_currency='USD', to_currency='UAH', rate=Decimal('40'), date=timezone.localdate())
        cache.clear()
        self.assertEqual(price_to_usd(Decimal('400000'), 'UAH'), Decimal('10000.00'))


class TestNumericFilterValidation(TestCase):
    """05-Q4: нечисловые price_*/year_* - 400 (раньше молча пропускались или давали 500)."""

    def test_non_numeric_values_give_400_with_field_name(self):
        for param in ('price_min', 'price_max', 'year_min', 'year_max'):
            for bad in ('abc', '1e', 'NaN', 'Infinity'):
                with self.subTest(param=param, bad=bad):
                    resp = APIClient().get(LIST_URL, {param: bad})
                    self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                    self.assertIn(param, resp.json())

    def test_out_of_range_values_give_400(self):
        """Завеликі числа - 400, а не DataError (numeric overflow) на PostgreSQL."""
        for param, bad in (('price_min', '1e999999'), ('price_max', '1' + '0' * 30),
                           ('year_min', '9' * 30), ('year_max', '-1000000')):
            with self.subTest(param=param, bad=bad):
                resp = APIClient().get(LIST_URL, {param: bad})
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(param, resp.json())

    def test_year_must_be_integer(self):
        self.assertEqual(APIClient().get(LIST_URL, {'year_min': '2019.5'}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_numbers_still_work(self):
        resp = APIClient().get(LIST_URL, {'price_min': '100.50', 'year_min': '2010'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
