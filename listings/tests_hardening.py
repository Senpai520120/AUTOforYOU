"""Задача 2.8: закрытие создания лотов (04-S1), валидация фильтров (04-Q1)."""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from listings.models import Listing
from pricing.models import Calculation
from tests.factories import (
    make_admin_role,
    make_broker,
    make_dealer,
    make_listing,
    make_user,
    make_vehicle,
)

CREATE_URL = '/api/v1/listings/create/'


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def calc_for(user=None):
    return Calculation.objects.create(user=user, inputs_snapshot={}, rates_snapshot={}, breakdown={},
                                      total_usd=Decimal('1'), total_uah=Decimal('1'))


class ListingCreateTests(TestCase):
    def setUp(self):
        self.vehicle = make_vehicle()

    def payload(self, **kw):
        return {'vehicle': self.vehicle.pk, 'price': '10000', 'currency': 'USD', 'channel': 'retail', **kw}

    def post(self, user, **kw):
        return client_for(user).post(CREATE_URL, self.payload(**kw), format='json')

    def test_anonymous_401(self):
        self.assertEqual(self.post(None).status_code, 401)

    def test_buyer_403(self):
        self.assertEqual(self.post(make_user()).status_code, 403)

    def test_dealer_403(self):
        self.assertEqual(self.post(make_dealer()).status_code, 403)

    def test_broker_201(self):
        self.assertEqual(self.post(make_broker()).status_code, 201)

    def test_admin_201(self):
        self.assertEqual(self.post(make_admin_role()).status_code, 201)

    def test_foreign_calculation_400(self):
        resp = self.post(make_broker(), calculation=calc_for(make_user()).pk)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('calculation', resp.json())

    def test_own_calculation_201(self):
        broker = make_broker()
        self.assertEqual(self.post(broker, calculation=calc_for(broker).pk).status_code, 201)

    def test_admin_any_calculation_201(self):
        self.assertEqual(self.post(make_admin_role(), calculation=calc_for(make_user()).pk).status_code, 201)

    def test_duplicate_vehicle_channel_400(self):
        make_listing(self.vehicle, make_user(), channel='retail')
        resp = self.post(make_broker())
        self.assertEqual(resp.status_code, 400)
        self.assertIn('vehicle', resp.json())

    def test_lots_off_404_even_for_admin(self):
        with override_settings(LOTS_ENABLED=False):
            self.assertEqual(self.post(make_admin_role()).status_code, 404)
        self.assertFalse(Listing.objects.exists())


class MaxPriceFilterTests(TestCase):
    def setUp(self):
        make_listing(make_vehicle(), make_user(), price=10000)

    def get(self, url, user=None):
        return client_for(user).get(url)

    def test_catalog_bad_values_400(self):
        for value in ('abc', '-1', '1' * 20):
            with self.subTest(value=value):
                resp = self.get(f'/api/v1/listings/?max_price={value}')
                self.assertEqual(resp.status_code, 400)
                self.assertIn('max_price', resp.json())

    def test_catalog_valid_200(self):
        resp = self.get('/api/v1/listings/?max_price=15000')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['count'], 1)

    def test_catalog_filters(self):
        self.assertEqual(self.get('/api/v1/listings/?max_price=5000').json()['count'], 0)

    def test_b2b_bad_value_400(self):
        self.assertEqual(self.get('/api/v1/b2b/board/?max_price=abc', make_dealer()).status_code, 400)

    def test_b2b_valid_200(self):
        self.assertEqual(self.get('/api/v1/b2b/board/?max_price=15000', make_dealer()).status_code, 200)
