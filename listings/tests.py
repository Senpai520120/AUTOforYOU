"""
Тесты B2B-гейтинга на уровне detail-вьюхи листинга.
Проверяет, что прямой доступ по ID к wholesale-листингу возвращает 404 для неверифицированных.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
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


# ── Измерение N+1: каталог листингов ─────────────────────────────────────────

class TestListingListQueryCount(APITestCase):
    """
    Проверяем, что список листингов не даёт N+1 запросов.
    select_related('vehicle', 'seller') + prefetch_related('vehicle__images')
    должны уложить весь каталог в ≤ 4 запроса.
    """

    def setUp(self):
        self.seller = _make_user('seller_qc@test.com')
        # Создаём 5 листингов с разными автомобилями
        for i in range(5):
            v = _make_vehicle(f'QCVIN0000000{i:04d}')
            _make_listing(v, self.seller, channel='retail')

    def test_listing_list_query_count(self):
        # 3 запроса: COUNT (пагинация) + Listing JOIN Vehicle+Seller + prefetch VehicleImage
        # JWT stateless — не даёт отдельного DB-запроса
        with self.assertNumQueries(3):
            resp = self.client.get('/api/v1/listings/')
            _ = resp.data

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data.get('results', resp.data)
        self.assertEqual(len(results), 5)

    def test_listing_list_scales_flat(self):
        """15 листингов — всё равно ровно 3 запроса (нет N+1)."""
        for i in range(10):
            v = _make_vehicle(f'SCALEVIN{i:08d}')
            _make_listing(v, self.seller, channel='retail')

        with self.assertNumQueries(3):
            resp = self.client.get('/api/v1/listings/')
            _ = resp.data

        results = resp.data.get('results', resp.data)
        self.assertGreaterEqual(len(results), 10)


# ─── Ограничения на уровне БД ─────────────────────────────────────────────────

class TestListingChoiceConstraints(TestCase):
    """
    Django проверяет choices только при full_clean(). .save() и .update()
    пишут что угодно — в базе уже лежал status='active', которого нет среди
    вариантов, и карточка в каталоге показывала сырое значение вместо
    перевода. Ограничения в БД закрывают все пути записи.
    """

    def setUp(self):
        self.user = User.objects.create_user(email='constraint@test.com', password='pass')
        self.vehicle = Vehicle.objects.create(
            vin='WBAVA37547NL12345', make='BMW', model='X5', year=2019,
            engine_cc=3000, fuel_type='diesel', mileage_km=80000,
        )

    def _create(self, **kw):
        defaults = dict(vehicle=self.vehicle, seller=self.user, price='20000.00')
        defaults.update(kw)
        return Listing.objects.create(**defaults)

    def test_valid_status_accepted(self):
        listing = self._create(status='in_stock')
        self.assertEqual(listing.status, 'in_stock')

    def test_invalid_status_rejected_on_create(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create(status='active')

    def test_invalid_status_rejected_on_update(self):
        # update() обходит и full_clean(), и сигналы — раньше это был
        # самый простой способ записать что угодно.
        listing = self._create()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Listing.objects.filter(pk=listing.pk).update(status='active')

    def test_invalid_channel_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create(channel='secret')

    def test_invalid_currency_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create(currency='BTC')
