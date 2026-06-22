"""
Тесты B2B-гейтинга на уровне detail-вьюхи листинга.
Проверяет, что прямой доступ по ID к wholesale-листингу возвращает 404 для неверифицированных.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from listings.models import Listing
from vehicles.models import Vehicle

User = get_user_model()


def _make_user(email='user@test.com', **kwargs):
    return User.objects.create_user(email=email, password='testpass123', **kwargs)


def _make_vehicle(vin='TESTVINHD000001'):
    return Vehicle.objects.create(
        make='Ford', model='F-150', year=2021, vin=vin,
        fuel_type='petrol', engine_cc=3500, mileage_km=20000,
    )


def _make_listing(vehicle, seller, channel='retail'):
    return Listing.objects.create(
        vehicle=vehicle, seller=seller, price=15000, currency='USD', channel=channel,
    )


class TestWholesaleListingDetailGating(APITestCase):
    """
    Прямой доступ по GET /api/v1/listings/<id>/ должен возвращать 404,
    если листинг wholesale, а пользователь не верифицированный дилер/админ.
    """

    def setUp(self):
        self.seller = _make_user('seller@test.com')
        self.vehicle = _make_vehicle()
        self.wholesale = _make_listing(self.vehicle, self.seller, channel='wholesale')

    def _url(self):
        return f'/api/v1/listings/{self.wholesale.id}/'

    def test_anon_gets_404_on_wholesale_detail(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_user_gets_404_on_wholesale_detail(self):
        user = _make_user('buyer@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_verified_dealer_can_access_wholesale_detail(self):
        dealer = _make_user('dealer@test.com', is_verified_dealer=True, role='dealer')
        self.client.force_authenticate(dealer)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['id'], self.wholesale.id)

    def test_admin_can_access_wholesale_detail(self):
        admin = User.objects.create_superuser(email='adm@test.com', password='pass')
        self.client.force_authenticate(admin)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_retail_listing_accessible_to_all(self):
        v2 = _make_vehicle('TESTVINHD000002')
        retail = _make_listing(v2, self.seller, channel='retail')
        resp = self.client.get(f'/api/v1/listings/{retail.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
