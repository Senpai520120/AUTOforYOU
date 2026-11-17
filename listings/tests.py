"""
Тесты B2B-гейтинга на уровне detail-вьюхи листинга.
Проверяет, что прямой доступ по ID к wholesale-листингу возвращает 404 для неверифицированных.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from listings.models import Listing
from tests.factories import (
    make_admin_role,
    make_broker,
    make_dealer,
    make_listing,
    make_moderator,
    make_staff,
    make_user,
    make_vehicle,
)
from vehicles.models import Vehicle


class TestWholesaleListGating(APITestCase):
    """Список /listings/: wholesale видят только дилер и admin; is_staff без роли не даёт."""

    URL = '/api/v1/listings/'

    def setUp(self):
        seller = make_user('seller_list@test.com')
        self.retail = make_listing(make_vehicle(vin='LISTVIN000000001'), seller, channel='retail')
        self.wholesale = make_listing(make_vehicle(vin='LISTVIN000000002'), seller, channel='wholesale')

    def _ids(self, user):
        self.client.force_authenticate(user)
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return {item['id'] for item in resp.data['results']}

    def test_broker_sees_retail_only(self):
        self.assertEqual(self._ids(make_broker()), {self.retail.id})

    def test_moderator_sees_retail_only(self):
        self.assertEqual(self._ids(make_moderator()), {self.retail.id})

    def test_admin_role_sees_all(self):
        self.assertEqual(self._ids(make_admin_role()), {self.retail.id, self.wholesale.id})

    def test_dealer_sees_all(self):
        self.assertEqual(self._ids(make_dealer()), {self.retail.id, self.wholesale.id})


class TestB2BBoardByRole(APITestCase):
    URL = '/api/v1/b2b/board/'

    def test_anon_gets_401(self):
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_broker_with_is_staff_gets_403(self):
        self.client.force_authenticate(make_broker())
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_with_is_staff_gets_403(self):
        self.client.force_authenticate(make_moderator())
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_role_gets_200(self):
        self.client.force_authenticate(make_admin_role())
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_200_OK)

    def test_dealer_gets_200(self):
        self.client.force_authenticate(make_dealer())
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_200_OK)


class TestWholesaleListingDetailGating(APITestCase):
    """
    Прямой доступ по GET /api/v1/listings/<id>/ должен возвращать 404,
    если листинг wholesale, а пользователь не верифицированный дилер/админ.
    """

    def setUp(self):
        self.seller = make_user('seller@test.com')
        self.vehicle = make_vehicle()
        self.wholesale = make_listing(self.vehicle, self.seller, channel='wholesale')

    def _url(self):
        return f'/api/v1/listings/{self.wholesale.id}/'

    def test_anon_gets_404_on_wholesale_detail(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_user_gets_404_on_wholesale_detail(self):
        user = make_user('buyer@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_verified_dealer_can_access_wholesale_detail(self):
        dealer = make_dealer()
        self.client.force_authenticate(dealer)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['id'], self.wholesale.id)

    def test_admin_can_access_wholesale_detail(self):
        admin = make_staff(superuser=True)
        self.client.force_authenticate(admin)
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_broker_with_is_staff_gets_404_on_wholesale_detail(self):
        broker = make_broker()
        self.assertTrue(broker.is_staff)
        self.client.force_authenticate(broker)
        self.assertEqual(self.client.get(self._url()).status_code, status.HTTP_404_NOT_FOUND)

    def test_moderator_with_is_staff_gets_404_on_wholesale_detail(self):
        moderator = make_moderator()
        self.assertTrue(moderator.is_staff)
        self.client.force_authenticate(moderator)
        self.assertEqual(self.client.get(self._url()).status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_role_can_access_wholesale_detail(self):
        self.client.force_authenticate(make_admin_role())
        self.assertEqual(self.client.get(self._url()).status_code, status.HTTP_200_OK)

    def test_retail_listing_accessible_to_all(self):
        v2 = make_vehicle(vin='TESTVINHD000002')
        retail = make_listing(v2, self.seller, channel='retail')
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
        self.seller = make_user('seller_qc@test.com')
        # Создаём 5 листингов с разными автомобилями
        for i in range(5):
            v = make_vehicle(vin=f'QCVIN0000000{i:04d}')
            make_listing(v, self.seller, channel='retail')

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
            v = make_vehicle(vin=f'SCALEVIN{i:08d}')
            make_listing(v, self.seller, channel='retail')

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
        self.user = make_user()
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


# ─── Создание объявлений и валидация фильтров (задача 2.8) ───────────────────

def _make_calc(user=None):
    from pricing.models import Calculation
    return Calculation.objects.create(
        user=user, inputs_snapshot={}, rates_snapshot={}, breakdown={},
        total_usd='1000.00', total_uah='40000.00',
    )


class TestListingCreate(APITestCase):
    """04-S1, 13-S12, 02-S5: создавать объявления могут только broker и admin."""

    URL = '/api/v1/listings/create/'

    def setUp(self):
        self.vehicle = make_vehicle()

    def _payload(self, **kw):
        data = {'vehicle': self.vehicle.pk, 'price': '15000.00', 'currency': 'USD', 'channel': 'retail'}
        data.update(kw)
        return data

    def _post(self, user, **kw):
        if user is not None:
            self.client.force_authenticate(user)
        return self.client.post(self.URL, self._payload(**kw), format='json')

    def test_anon_gets_401(self):
        self.assertEqual(self._post(None).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_buyer_gets_403(self):
        self.assertEqual(self._post(make_user()).status_code, status.HTTP_403_FORBIDDEN)

    def test_verified_dealer_gets_403(self):
        self.assertEqual(self._post(make_dealer()).status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_gets_403(self):
        self.assertEqual(self._post(make_moderator()).status_code, status.HTTP_403_FORBIDDEN)

    def test_broker_creates_listing_with_self_as_seller(self):
        broker = make_broker()
        resp = self._post(broker)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Listing.objects.get().seller, broker)

    def test_admin_creates_listing(self):
        self.assertEqual(self._post(make_admin_role()).status_code, status.HTTP_201_CREATED)

    def test_broker_with_foreign_calculation_gets_400(self):
        foreign = _make_calc(make_user())
        resp = self._post(make_broker(), calculation=foreign.pk)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('calculation', resp.data)

    def test_broker_with_anonymous_calculation_gets_400(self):
        resp = self._post(make_broker(), calculation=_make_calc(None).pk)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_broker_with_own_calculation_gets_201(self):
        broker = make_broker()
        resp = self._post(broker, calculation=_make_calc(broker).pk)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_admin_may_attach_foreign_calculation(self):
        resp = self._post(make_admin_role(), calculation=_make_calc(make_user()).pk)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_duplicate_vehicle_and_channel_gets_400(self):
        make_listing(self.vehicle, make_user(), channel='retail')
        resp = self._post(make_broker())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Listing.objects.count(), 1)

    def test_same_vehicle_other_channel_allowed(self):
        make_listing(self.vehicle, make_user(), channel='retail')
        self.assertEqual(self._post(make_broker(), channel='wholesale').status_code, status.HTTP_201_CREATED)

    def test_broker_retail_on_vehicle_with_wholesale_gets_400(self):
        make_listing(self.vehicle, make_user(), channel='wholesale')
        resp = self._post(make_broker())
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('vehicle', resp.data)
        self.assertEqual(Listing.objects.count(), 1)

    def test_admin_retail_on_vehicle_with_wholesale_gets_201(self):
        make_listing(self.vehicle, make_user(), channel='wholesale')
        self.assertEqual(self._post(make_admin_role()).status_code, status.HTTP_201_CREATED)

    def test_broker_retail_on_vehicle_without_listings_gets_201(self):
        self.assertEqual(self._post(make_broker()).status_code, status.HTTP_201_CREATED)

    def test_broker_cannot_set_express_buyout(self):
        resp = self._post(make_broker(), channel='wholesale', is_express_buyout=True)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Listing.objects.exists())

    def test_admin_may_set_express_buyout(self):
        resp = self._post(make_admin_role(), channel='wholesale', is_express_buyout=True)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class TestCatalogFilterValidation(APITestCase):
    """04-Q1, 04-Q8: неверные фильтры дают 400 с ошибкой поля, не 500 и не пустой список."""

    def setUp(self):
        seller = make_user()
        self.cheap = make_listing(make_vehicle(), seller, price=10000)
        self.pricey = make_listing(make_vehicle(), seller, price=20000)
        self.w_cheap = make_listing(make_vehicle(), seller, channel='wholesale', price=10000)
        self.w_pricey = make_listing(make_vehicle(), seller, channel='wholesale', price=20000)

    def _get(self, url, **params):
        return self.client.get(url, params)

    def test_non_numeric_max_price_gets_400(self):
        resp = self._get('/api/v1/listings/', max_price='abc')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('max_price', resp.data)

    def test_negative_max_price_gets_400(self):
        self.assertEqual(self._get('/api/v1/listings/', max_price='-1').status_code, status.HTTP_400_BAD_REQUEST)

    def test_huge_max_price_gets_400(self):
        resp = self._get('/api/v1/listings/', max_price='9' * 30)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_max_price_filters(self):
        resp = self._get('/api/v1/listings/', max_price='15000')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual({i['id'] for i in resp.data['results']}, {self.cheap.id})

    def test_unknown_status_gets_400(self):
        resp = self._get('/api/v1/listings/', status='foo')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', resp.data)

    def test_unknown_channel_currency_fuel_get_400(self):
        for name in ('channel', 'currency', 'fuel_type'):
            with self.subTest(name=name):
                resp = self._get('/api/v1/listings/', **{name: 'foo'})
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_b2b_board_rejects_bad_max_price(self):
        self.client.force_authenticate(make_dealer())
        for value in ('abc', '-1'):
            with self.subTest(value=value):
                resp = self._get('/api/v1/b2b/board/', max_price=value)
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_b2b_board_filters_by_valid_max_price(self):
        self.client.force_authenticate(make_dealer())
        resp = self._get('/api/v1/b2b/board/', max_price='15000')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual({i['id'] for i in resp.data['results']}, {self.w_cheap.id})


@override_settings(B2B_ENABLED=False)
class TestWholesaleHiddenWhenB2BDisabled(APITestCase):
    """B2B_ENABLED=false: оптовые объявления не отдаются никому, даже дилеру и admin."""

    def setUp(self):
        seller = make_user()
        self.retail = make_listing(make_vehicle(), seller, channel='retail')
        self.wholesale = make_listing(make_vehicle(), seller, channel='wholesale')

    def test_dealer_list_has_retail_only(self):
        self.client.force_authenticate(make_dealer())
        resp = self.client.get('/api/v1/listings/')
        self.assertEqual({i['id'] for i in resp.data['results']}, {self.retail.id})

    def test_admin_detail_of_wholesale_is_404(self):
        self.client.force_authenticate(make_admin_role())
        resp = self.client.get(f'/api/v1/listings/{self.wholesale.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
