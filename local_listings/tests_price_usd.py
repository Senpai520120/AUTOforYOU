"""10.24: публичный список и деталь отдают price_usd (только чтение)."""
from decimal import Decimal

from rest_framework.test import APIClient, APITestCase

from tests.factories import make_local_listing, make_user

from .models import LocalListing


class TestPriceUsdInList(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user()
        cls.listing = make_local_listing(cls.owner, currency='UAH', price=Decimal('400000'))
        LocalListing.objects.filter(pk=cls.listing.pk).update(price_usd=Decimal('9500.00'))

    def test_list_has_price_usd(self):
        resp = APIClient().get('/api/v1/local/listings/')
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.json()['results'] if r['id'] == self.listing.pk)
        self.assertEqual(row['price_usd'], '9500.00')
        self.assertEqual(row['currency'], 'UAH')

    def test_detail_has_price_usd(self):
        resp = APIClient().get(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['price_usd'], '9500.00')
