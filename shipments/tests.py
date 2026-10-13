"""
Тести доступу до контейнерів.

Раніше обидві публічні в'ю були без permission_classes і віддавали анониму
список контейнерів разом з VIN автомобілів усередині. Тестів на них не було
взагалі — жоден прогін цього не ловив.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from tests.factories import make_admin_role, make_broker, make_moderator, make_staff, make_user
from vehicles.models import Vehicle

from .models import Shipment

LIST_URL = '/api/v1/shipments/'


class TestShipmentAccess(APITestCase):
    def setUp(self):
        self.watcher = make_user('watcher@test.com')
        self.stranger = make_user('stranger_ship@test.com')
        self.staff = make_staff('staff_ship@test.com')  # is_staff без роли admin
        self.admin = make_admin_role('admin_ship@test.com')

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

    def test_admin_sees_all_shipments(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(LIST_URL)
        self.assertEqual(resp.data['count'], 1)

    def test_admin_reads_any_detail(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_200_OK)

    def test_bare_is_staff_sees_nothing(self):
        # is_staff без роли admin — только доступ в Django Admin.
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(self.client.get(LIST_URL).data['count'], 0)
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_404_NOT_FOUND)

    # ── broker / moderator с is_staff=True: чужие контейнеры не видят ─────────

    def test_broker_sees_empty_list(self):
        self.client.force_authenticate(user=make_broker())
        self.assertEqual(self.client.get(LIST_URL).data['count'], 0)

    def test_broker_cannot_read_foreign_detail(self):
        self.client.force_authenticate(user=make_broker())
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_404_NOT_FOUND)

    def test_broker_in_watchers_sees_own_shipment(self):
        broker = make_broker()
        self.shipment.watchers.add(broker)
        self.client.force_authenticate(user=broker)
        self.assertEqual(self.client.get(LIST_URL).data['count'], 1)
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_200_OK)

    def test_moderator_sees_empty_list(self):
        self.client.force_authenticate(user=make_moderator())
        self.assertEqual(self.client.get(LIST_URL).data['count'], 0)

    def test_moderator_cannot_read_foreign_detail(self):
        self.client.force_authenticate(user=make_moderator())
        self.assertEqual(self.client.get(self._detail_url()).status_code, status.HTTP_404_NOT_FOUND)
