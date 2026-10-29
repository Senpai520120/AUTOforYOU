"""
Тести доступу до контейнерів.

Раніше обидві публічні в'ю були без permission_classes і віддавали анониму
список контейнерів разом з VIN автомобілів усередині. Тестів на них не було
взагалі — жоден прогін цього не ловив.
"""
import io
import os

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import override_settings
from PIL import Image as PILImage
from rest_framework import status
from rest_framework.test import APITestCase

from core.uploads import ImageUploadError
from tests.factories import make_admin_role, make_broker, make_moderator, make_staff, make_user
from tests.test_uploads import admin_form_data, image_bytes, use_temp_media
from vehicles.models import Vehicle

from .models import Shipment, TrackingEvent

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


# ─── Фото трекинга: очистка и приватность (задача 1.10, 23-D55, 04-S4, 12-S7) ──

PHOTO_NAME = r'^tracking_photos/[0-9a-f]{32}\.jpg$'


def _photo(name='port.jpg', data=None):
    return SimpleUploadedFile(name, data or image_bytes(gps=True), content_type='image/jpeg')


class TestTrackingPhotoSanitized(APITestCase):
    def setUp(self):
        self.media_root = use_temp_media(self)
        self.shipment = Shipment.objects.create(container_no='MSCU0000101')

    def _assert_clean_private(self, event):
        self.assertRegex(event.photo.name, PHOTO_NAME)
        storage = event.photo.storage
        self.assertTrue(storage.exists(event.photo.name))
        self.assertFalse(os.path.exists(os.path.join(self.media_root, event.photo.name)))
        with storage.open(event.photo.name, 'rb') as fh, PILImage.open(fh) as img:
            self.assertEqual(dict(img.getexif()), {})

    def test_advance_status_photo_sanitized_and_private(self):
        event = self.shipment.advance_status(Shipment.Status.LOADING, photo=_photo())
        self._assert_clean_private(event)

    def test_created_with_uploaded_file(self):
        event = TrackingEvent.objects.create(shipment=self.shipment, status='loading', photo=_photo())
        self._assert_clean_private(event)

    def test_advance_status_rejects_html(self):
        with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'), transaction.atomic():
            self.shipment.advance_status(Shipment.Status.LOADING, photo=_photo('x.jpg', b'<html></html>'))
        self.assertFalse(TrackingEvent.objects.exists())


class TestTrackingEventAdminUpload(APITestCase):
    """Точка 4: inline в Shipment и отдельная форма TrackingEvent."""

    def setUp(self):
        use_temp_media(self)
        self.shipment = Shipment.objects.create(container_no='MSCU0000102')
        self.client.force_login(make_staff(superuser=True))

    def _post(self, url, prefix, upload, extra=None):
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = admin_form_data(page.context['adminform'].form, page.context.get('inline_admin_formsets', []))
        data[f'{prefix}photo'] = upload
        data.update(extra or {})
        return self.client.post(url, data)

    def test_inline_html_gives_field_error(self):
        url = f'/admin/shipments/shipment/{self.shipment.pk}/change/'
        r = self._post(url, 'events-0-', _photo('x.jpg', b'<html></html>'), {'events-0-status': 'loading'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['inline_admin_formsets'][0].formset.errors[0]['photo'])
        self.assertFalse(TrackingEvent.objects.exists())

    def test_event_form_html_gives_field_error(self):
        r = self._post('/admin/shipments/trackingevent/add/', '', _photo('x.jpg', b'<svg></svg>'),
                       {'shipment': self.shipment.pk, 'status': 'loading'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['adminform'].form.errors['photo'])

    def test_event_form_valid_photo_saved_private(self):
        r = self._post('/admin/shipments/trackingevent/add/', '', _photo(),
                       {'shipment': self.shipment.pk, 'status': 'loading'})
        self.assertEqual(r.status_code, 302)
        event = TrackingEvent.objects.get()
        self.assertRegex(event.photo.name, PHOTO_NAME)

    def test_admin_links_use_protected_url(self):
        event = TrackingEvent.objects.create(shipment=self.shipment, status='loading', photo=_photo())
        protected = event.get_photo_url()
        changelist = self.client.get('/admin/shipments/trackingevent/')
        self.assertContains(changelist, f'src="{protected}"')
        change = self.client.get(f'/admin/shipments/trackingevent/{event.pk}/change/')
        self.assertContains(change, f'href="{protected}"')
        self.assertNotContains(change, '/protected-media/')
        # Миниатюра в админке грузится сессией Django.
        self.assertEqual(self.client.get(protected).status_code, status.HTTP_200_OK)


class TestTrackingPhotoAccess(APITestCase):
    def setUp(self):
        use_temp_media(self)
        self.watcher = make_user('watcher_photo@test.com')
        self.stranger = make_user('stranger_photo@test.com')
        self.admin = make_admin_role('admin_photo@test.com')
        self.bare_staff = make_staff('bare_staff_photo@test.com')
        self.shipment = Shipment.objects.create(container_no='MSCU0000103')
        self.shipment.watchers.add(self.watcher)
        self.event = self.shipment.advance_status(Shipment.Status.LOADING, photo=_photo())
        self.url = f'{LIST_URL}{self.shipment.pk}/events/{self.event.pk}/photo/'

    def _get(self, user=None, url=None):
        if user is not None:
            self.client.force_authenticate(user)
        return self.client.get(url or self.url)

    def test_anonymous_401(self):
        self.assertEqual(self._get().status_code, status.HTTP_401_UNAUTHORIZED)

    def test_stranger_404(self):
        self.assertEqual(self._get(self.stranger).status_code, status.HTTP_404_NOT_FOUND)

    def test_bare_staff_without_permission_404(self):
        self.assertEqual(self._get(self.bare_staff).status_code, status.HTTP_404_NOT_FOUND)

    def test_watcher_200_with_image(self):
        r = self._get(self.watcher)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r['Content-Type'], 'image/jpeg')
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
        body = b''.join(r.streaming_content)
        with PILImage.open(io.BytesIO(body)) as img:
            self.assertEqual(dict(img.getexif()), {})

    def test_admin_role_200(self):
        self.assertEqual(self._get(self.admin).status_code, status.HTTP_200_OK)

    def test_staff_with_view_permission_200(self):
        staff = make_staff('viewer_photo@test.com')
        staff.user_permissions.add(Permission.objects.get(codename='view_trackingevent'))
        self.assertEqual(self._get(staff).status_code, status.HTTP_200_OK)

    def test_superuser_200(self):
        su = make_staff('su_photo@test.com', superuser=True)
        self.assertEqual(self._get(su).status_code, status.HTTP_200_OK)

    def test_wrong_shipment_in_url_404(self):
        other = Shipment.objects.create(container_no='MSCU0000104')
        other.watchers.add(self.watcher)
        url = f'{LIST_URL}{other.pk}/events/{self.event.pk}/photo/'
        self.assertEqual(self._get(self.watcher, url).status_code, status.HTTP_404_NOT_FOUND)

    def test_event_without_photo_404(self):
        event = self.shipment.advance_status(Shipment.Status.IN_OCEAN)
        url = f'{LIST_URL}{self.shipment.pk}/events/{event.pk}/photo/'
        self.assertEqual(self._get(self.watcher, url).status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(PRIVATE_MEDIA_USE_X_ACCEL=True)
    def test_x_accel_redirect(self):
        r = self._get(self.watcher)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r['X-Accel-Redirect'], f'/protected-media/{self.event.photo.name}')
        self.assertEqual(r.content, b'')

    def test_detail_has_protected_url_not_media(self):
        r = self._get(self.watcher, f'{LIST_URL}{self.shipment.pk}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        photo = next(e['photo'] for e in r.data['events'] if e['id'] == self.event.pk)
        self.assertEqual(photo, self.url)
        self.assertNotIn('/media/', r.content.decode())
        self.assertNotIn('tracking_photos', r.content.decode())
