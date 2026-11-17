"""Задача 8.6 (часть 1, бэкенд): тип продавца с сервера, блок и страница продавца, история цены, баннер."""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase

from deals.models import Deal, Review
from tests.factories import auth_client, make_dealer, make_local_listing, make_region_city, make_user

from .models import ListingPriceHistory, LocalListing

URL = '/api/v1/local/listings/'


def payload(region, city, **kw):
    data = {
        'make': 'Skoda', 'model': 'Fabia', 'year': 2015, 'mileage_km': 100000, 'price': '5000',
        'currency': 'USD', 'fuel_type': 'petrol', 'transmission': 'manual', 'body_type': 'hatchback',
        'condition': 'used', 'region': region.pk, 'city': city.pk, 'description': 'Тест',
        'contact_phone': '+380501234567', 'agreed_to_rules': True, 'legal_confirmed': True,
    }
    data.update(kw)
    return data


def all_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_strings(v)
    elif obj is not None:
        yield str(obj)


class TestSellerTypeFromServer(APITestCase):
    def setUp(self):
        self.region, self.city = make_region_city()

    def test_unverified_dealer_claim_is_ignored(self):
        resp = auth_client(make_user()).post(URL, payload(self.region, self.city, seller_type='dealer'), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(LocalListing.objects.get().seller_type, 'private')

    def test_verified_dealer_gets_dealer(self):
        resp = auth_client(make_dealer()).post(URL, payload(self.region, self.city), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(LocalListing.objects.get().seller_type, 'dealer')

    def test_patch_seller_type_ignored(self):
        user = make_user()
        listing = make_local_listing(user)
        resp = auth_client(user).patch(f'{URL}{listing.pk}/', {'seller_type': 'dealer', 'mileage_km': 77}, format='json')
        self.assertEqual(resp.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual(listing.mileage_km, 77)
        self.assertEqual(listing.seller_type, 'private')

    def test_revoked_dealer_not_shown_as_dealer(self):
        dealer = make_dealer()
        listing = make_local_listing(dealer, seller_type='dealer')
        self.assertEqual(APIClient().get(f'{URL}{listing.pk}/').json()['seller_type'], 'dealer')
        type(dealer).objects.filter(pk=dealer.pk).update(is_verified_dealer=False)
        self.assertEqual(APIClient().get(f'{URL}{listing.pk}/').json()['seller_type'], 'private')
        rows = APIClient().get(URL).json()['results']
        self.assertEqual({r['seller_type'] for r in rows if r['id'] == listing.pk}, {'private'})


class TestSellerBlockAndPage(APITestCase):
    def setUp(self):
        self.seller = make_user(email='hidden.mail@example.com', first_name='Олександр', last_name='Петренко')
        self.active = make_local_listing(self.seller, contact_phone='+380671112233')
        make_local_listing(self.seller, status=LocalListing.Status.PENDING)
        make_local_listing(self.seller, status=LocalListing.Status.EXPIRED)

    def assert_no_private_data(self, data):
        text = ' '.join(all_strings(data))
        for secret in ('hidden.mail', 'example.com', '671112233', 'Петренко'):
            self.assertNotIn(secret, text)

    def test_detail_block(self):
        data = APIClient().get(f'{URL}{self.active.pk}/').json()
        self.assertEqual(data['seller_id'], self.seller.pk)
        self.assertEqual(data['seller_active_listings_count'], 1)
        self.assertRegex(data['seller_member_since'], r'^\d{4}-\d{2}$')
        self.assert_no_private_data(data)

    def test_seller_page(self):
        buyer = make_user(first_name='Ірина', last_name='Коваль')
        deal = Deal.objects.create(listing=self.active, seller=self.seller, buyer=buyer, status=Deal.Status.CONFIRMED)
        Review.objects.create(deal=deal, author=buyer, target=self.seller, rating=5, text='Чесний продавець')
        resp = APIClient().get(f'/api/v1/local/sellers/{self.seller.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['display_name'], 'Олександр П.')
        self.assertEqual(data['active_listings_count'], 1)
        self.assertEqual(data['deal_count'], 1)
        self.assertEqual(data['avg_rating'], 5)
        self.assertEqual([r['id'] for r in data['listings']['results']], [self.active.pk])
        self.assertEqual(data['reviews'][0]['author_name'], 'Ірина К.')
        self.assert_no_private_data(data)

    def test_seller_page_404_cases_identical(self):
        missing = APIClient().get('/api/v1/local/sellers/999999/')
        self.assertEqual(missing.status_code, 404)
        nobody = make_user()
        empty = APIClient().get(f'/api/v1/local/sellers/{nobody.pk}/')
        type(self.seller).objects.filter(pk=self.seller.pk).update(is_active=False)
        inactive = APIClient().get(f'/api/v1/local/sellers/{self.seller.pk}/')
        for resp in (empty, inactive):
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(resp.json(), missing.json())  # по телу не отличить причину

    def test_review_with_contacts_is_hidden(self):
        buyer = make_user(first_name='Ірина')
        deal = Deal.objects.create(listing=self.active, seller=self.seller, buyer=buyer, status=Deal.Status.CONFIRMED)
        Review.objects.create(deal=deal, author=buyer, target=self.seller, rating=4, text='Дзвоніть 0671234567')
        data = APIClient().get(f'/api/v1/local/sellers/{self.seller.pk}/').json()
        self.assertEqual(data['reviews'][0]['text'], '')
        self.assertEqual(data['reviews'][0]['rating'], 4)
        self.assertNotIn('0671234567', str(data))

    def test_seller_page_deleted_user_404(self):
        from django.utils import timezone
        type(self.seller).objects.filter(pk=self.seller.pk).update(deleted_at=timezone.now())
        self.assertEqual(APIClient().get(f'/api/v1/local/sellers/{self.seller.pk}/').status_code, 404)

    def test_seller_page_queries_do_not_grow(self):
        url = f'/api/v1/local/sellers/{self.seller.pk}/'
        with CaptureQueriesContext(connection) as small:
            APIClient().get(url)
        for _ in range(5):
            make_local_listing(self.seller)
        with CaptureQueriesContext(connection) as big:
            APIClient().get(url)
        self.assertEqual(len(big), len(small))


class TestPriceHistory(APITestCase):
    def setUp(self):
        self.region, self.city = make_region_city()
        self.user = make_user()
        self.client = auth_client(self.user)

    def test_created_then_only_on_real_change(self):
        self.client.post(URL, payload(self.region, self.city), format='json')
        listing = LocalListing.objects.get()
        self.assertEqual(ListingPriceHistory.objects.filter(listing=listing).count(), 1)
        url = f'{URL}{listing.pk}/'
        self.client.patch(url, {'price': '5000.00'}, format='json')  # та же цена другой строкой
        self.assertEqual(ListingPriceHistory.objects.filter(listing=listing).count(), 1)
        self.client.patch(url, {'price': '4500'}, format='json')
        self.client.patch(url, {'currency': 'EUR'}, format='json')
        self.client.patch(url, {'mileage_km': 1}, format='json')
        rows = list(ListingPriceHistory.objects.filter(listing=listing).order_by('pk').values_list('price', 'currency'))
        self.assertEqual(rows, [(Decimal('5000.00'), 'USD'), (Decimal('4500.00'), 'USD'), (Decimal('4500.00'), 'EUR')])

    def test_not_in_public_api(self):
        self.client.post(URL, payload(self.region, self.city), format='json')
        listing = LocalListing.objects.get()
        data = APIClient().get(f'{URL}{listing.pk}/').json()
        self.assertNotIn('price_history', data)


class TestPrepaymentBanner(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # публичные настройки кэшируются

    def test_public_settings_expose_text(self):
        data = APIClient().get('/api/v1/site-settings/').json()
        self.assertIn('передоплату', data['prepayment_warning_text'])

    def test_empty_text_hides_banner(self):
        from site_settings.models import SiteSettings
        obj = SiteSettings.load()
        obj.prepayment_warning_text = ''
        obj.save()  # save() сбрасывает кэш публичных настроек
        self.assertEqual(APIClient().get('/api/v1/site-settings/').json()['prepayment_warning_text'], '')


class TestDealerDataMigration(APITestCase):
    """0015: «дилер» у неверифицированного владельца -> private, у верифицированного остаётся."""

    def test_fix_self_declared_dealers(self):
        from importlib import import_module

        from django.apps import apps

        migration = import_module('local_listings.migrations.0015_trust_pricehistory')
        fake = make_local_listing(make_user(), seller_type='dealer')
        real = make_local_listing(make_dealer(), seller_type='dealer')
        migration.fix_self_declared_dealers(apps, None)
        fake.refresh_from_db()
        real.refresh_from_db()
        self.assertEqual(fake.seller_type, 'private')
        self.assertEqual(real.seller_type, 'dealer')
