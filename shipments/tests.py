"""
Тести доступу до контейнерів.

Раніше обидві публічні в'ю були без permission_classes і віддавали анониму
список контейнерів разом з VIN автомобілів усередині. Тестів на них не було
взагалі — жоден прогін цього не ловив.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from vehicles.models import Vehicle

from .models import Shipment

User = get_user_model()

LIST_URL = '/api/v1/shipments/'


def _make_user(email, **kw):
    return User.objects.create_user(email=email, password='pass1234', **kw)


class TestShipmentAccess(APITestCase):
    def setUp(self):
        self.watcher = _make_user('watcher@test.com')
        self.stranger = _make_user('stranger_ship@test.com')
        self.staff = _make_user('staff_ship@test.com', is_staff=True)

        self.vehicle = Vehicle.objects.create(
            vin='1HGBH41JXMN109186', make='Toyota', model='Camry', year=2020,
            engine_cc=2000, fuel_type='petrol', mileage_km=10000,
        )
        self.shipment = Shipment.objects.create(container_no='MSCU1234567', vessel='Ever Given')
        self.shipment.vehicles.add(self.vehicle)
        self.shipment.watchers.add(self.watcher)

    def _detail_url(self):
        return f'{LIST_URL}{self.shipment.pk}/'

    # ── Аноним ────────────────────────────────────────────────────────────────

    def test_anonymous_cannot_list(self):
        self.assertEqual(self.client.get(LIST_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymous_cannot_read_detail(self):
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_401_UNAUTHORIZED)

    # ── Сторонній авторизований ───────────────────────────────────────────────

    def test_stranger_sees_empty_list(self):
        self.client.force_authenticate(user=self.stranger)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 0)

    def test_stranger_cannot_read_detail(self):
        self.client.force_authenticate(user=self.stranger)
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_404_NOT_FOUND)

    # ── Той, хто відстежує ────────────────────────────────────────────────────

    def test_watcher_sees_own_shipment(self):
        self.client.force_authenticate(user=self.watcher)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['container_no'], 'MSCU1234567')

    def test_watcher_reads_detail(self):
        self.client.force_authenticate(user=self.watcher)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ── VIN ───────────────────────────────────────────────────────────────────

    def test_vin_not_exposed_to_stranger(self):
        # Ключова перевірка: саме через VIN у вкладеному VehicleSerializer
        # публічний ендпоінт і був проблемою.
        self.client.force_authenticate(user=self.stranger)
        resp = self.client.get(self._detail_url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn('1HGBH41JXMN109186', str(resp.data))

    def test_vin_visible_to_watcher(self):
        self.client.force_authenticate(user=self.watcher)
        resp = self.client.get(self._detail_url())
        self.assertIn('1HGBH41JXMN109186', str(resp.data))

    # ── Адміністратор ─────────────────────────────────────────────────────────

    def test_staff_sees_all_shipments(self):
        self.client.force_authenticate(user=self.staff)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.data['count'], 1)

    def test_staff_reads_any_detail(self):
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_200_OK)
