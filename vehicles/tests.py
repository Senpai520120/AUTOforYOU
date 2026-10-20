"""Фото автомобиля (VehicleImage) и команда sanitize_existing_images (задача 1.10, 23-D55)."""
import os
from io import StringIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase
from PIL import Image

from shipments.models import Shipment, TrackingEvent
from tests.factories import make_staff, make_vehicle
from tests.test_uploads import GPS_IFD, admin_form_data, image_bytes, use_temp_media

from .models import VehicleImage

UUID_PATH = r'^vehicle_photos/[0-9a-f]{32}\.jpg$'


def _exif(storage, name):
    with storage.open(name, 'rb') as fh, Image.open(fh) as img:
        return dict(img.getexif())


class TestVehicleImageSanitized(TestCase):
    def setUp(self):
        use_temp_media(self)
        self.vehicle = make_vehicle()

    def test_uploaded_file_saved_without_exif_and_uuid_name(self):
        # Так файл приходит из админки: SimpleUploadedFile → objects.create → pre_save.
        upload = SimpleUploadedFile('my-garage.jpg', image_bytes(gps=True), content_type='image/jpeg')
        img = VehicleImage.objects.create(vehicle=self.vehicle, image=upload)
        self.assertRegex(img.image.name, UUID_PATH)
        self.assertEqual(_exif(img.image.storage, img.image.name), {})

    def test_direct_fieldfile_save_is_sanitized(self):
        # Путь upload_lot_photos/e2e_seed: instance.image.save(name, content) минует pre_save.
        img = VehicleImage(vehicle=self.vehicle)
        img.image.save('lot.jpg', ContentFile(image_bytes(gps=True)), save=True)
        self.assertRegex(img.image.name, UUID_PATH)
        self.assertEqual(_exif(img.image.storage, img.image.name), {})

    def test_non_image_raises(self):
        from core.uploads import ImageUploadError

        upload = SimpleUploadedFile('x.jpg', b'<html></html>', content_type='image/jpeg')
        with self.assertRaisesMessage(ImageUploadError, 'не є зображенням'), transaction.atomic():
            VehicleImage.objects.create(vehicle=self.vehicle, image=upload)
        self.assertFalse(VehicleImage.objects.exists())


class TestVehicleAdminInlineUpload(TestCase):
    """Точка 3: inline фото в админке Vehicle — ошибка поля, а не 500."""

    def setUp(self):
        use_temp_media(self)
        self.vehicle = make_vehicle()
        self.client.force_login(make_staff(superuser=True))
        self.url = f'/admin/vehicles/vehicle/{self.vehicle.pk}/change/'

    def _post(self, upload):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        data = admin_form_data(page.context['adminform'].form, page.context['inline_admin_formsets'])
        data['images-0-image'] = upload
        return self.client.post(self.url, data)

    def test_html_file_gives_field_error(self):
        r = self._post(SimpleUploadedFile('x.jpg', b'<html><script>1</script></html>', content_type='image/jpeg'))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['inline_admin_formsets'][0].formset.errors[0]['image'])
        self.assertFalse(VehicleImage.objects.exists())

    def test_valid_file_saved_clean(self):
        r = self._post(SimpleUploadedFile('a.jpg', image_bytes(gps=True), content_type='image/jpeg'))
        self.assertEqual(r.status_code, 302)
        img = VehicleImage.objects.get()
        self.assertRegex(img.image.name, UUID_PATH)
        self.assertEqual(_exif(img.image.storage, img.image.name), {})


class TestSanitizeExistingImages(TestCase):
    def setUp(self):
        self.media_root = use_temp_media(self)
        self.vehicle = make_vehicle()

    def _legacy_vehicle_image(self, data, name='vehicle_photos/old_lot_1.jpg'):
        # Файл до 1.10: исходное имя и EXIF, строка в БД — путь (поле его не трогает).
        stored = default_storage.save(name, ContentFile(data))
        return VehicleImage.objects.create(vehicle=self.vehicle, image=stored)

    def _run(self, *args):
        out = StringIO()
        call_command('sanitize_existing_images', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_by_default_changes_nothing(self):
        img = self._legacy_vehicle_image(image_bytes(gps=True))
        out = self._run()
        self.assertIn('[план]', out)
        img.refresh_from_db()
        self.assertEqual(img.image.name, 'vehicle_photos/old_lot_1.jpg')
        self.assertIn(GPS_IFD, _exif(default_storage, img.image.name))

    def test_explicit_dry_run_flag_changes_nothing(self):
        img = self._legacy_vehicle_image(image_bytes(gps=True))
        self._run('--apply', '--dry-run')
        img.refresh_from_db()
        self.assertEqual(img.image.name, 'vehicle_photos/old_lot_1.jpg')

    def test_apply_renames_and_strips_exif(self):
        img = self._legacy_vehicle_image(image_bytes(gps=True))
        self._run('--apply')
        img.refresh_from_db()
        self.assertRegex(img.image.name, UUID_PATH)
        self.assertEqual(_exif(default_storage, img.image.name), {})
        self.assertFalse(default_storage.exists('vehicle_photos/old_lot_1.jpg'))

    def test_apply_is_idempotent(self):
        self._legacy_vehicle_image(image_bytes())
        self._run('--apply')
        name = VehicleImage.objects.get().image.name
        out = self._run('--apply')
        self.assertIn('уже чистых 1', out)
        self.assertEqual(VehicleImage.objects.get().image.name, name)

    def test_invalid_reported_not_deleted_without_flag(self):
        img = self._legacy_vehicle_image(b'<html></html>', 'vehicle_photos/evil.jpg')
        out = self._run('--apply')
        self.assertIn('[битый]', out)
        img.refresh_from_db()
        self.assertEqual(img.image.name, 'vehicle_photos/evil.jpg')
        self.assertTrue(default_storage.exists('vehicle_photos/evil.jpg'))

    def test_delete_invalid(self):
        img = self._legacy_vehicle_image(b'<html></html>', 'vehicle_photos/evil.jpg')
        self._run('--apply', '--delete-invalid')
        img.refresh_from_db()
        self.assertEqual(img.image.name, '')
        self.assertFalse(default_storage.exists('vehicle_photos/evil.jpg'))

    def test_missing_file_reported_without_crash(self):
        VehicleImage.objects.create(vehicle=self.vehicle, image='vehicle_photos/gone.jpg')
        out = self._run('--apply')
        self.assertIn('[нет файла]', out)

    def test_tracking_photo_moved_from_public_media_to_private(self):
        shipment = Shipment.objects.create(container_no='MSCU7654321')
        stored = default_storage.save('tracking_photos/port.jpg', ContentFile(image_bytes(gps=True)))
        event = TrackingEvent.objects.create(shipment=shipment, status=shipment.status, photo=stored)
        self._run('--apply')
        event.refresh_from_db()
        self.assertRegex(event.photo.name, r'^tracking_photos/[0-9a-f]{32}\.jpg$')
        private = TrackingEvent._meta.get_field('photo').storage
        self.assertTrue(private.exists(event.photo.name))
        self.assertEqual(_exif(private, event.photo.name), {})
        # В публичном media/ файла больше нет.
        self.assertFalse(default_storage.exists('tracking_photos/port.jpg'))
        self.assertFalse(os.path.exists(os.path.join(self.media_root, event.photo.name)))



# ─── 04-S2 / 13-S5 (2.8): VIN и лот видны только там, где авто видно в каталоге ─────────

class VehicleVisibilityTests(TestCase):
    def setUp(self):
        from listings.models import Listing
        from tests.factories import make_listing, make_user
        seller = make_user()
        self.retail = make_vehicle(vin='RETAILVIN00000001')
        self.wholesale = make_vehicle(vin='WHOLESALEVIN00001')
        self.no_listing = make_vehicle(vin='NOLISTINGVIN00001')
        self.in_container = make_vehicle(vin='CONTAINERVIN00001')
        make_listing(self.retail, seller, channel=Listing.Channel.RETAIL)
        make_listing(self.wholesale, seller, channel=Listing.Channel.WHOLESALE)
        Shipment.objects.create(container_no='MSCU1234567').vehicles.add(self.in_container)

    def vins(self, user=None, query=''):
        from rest_framework.test import APIClient
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        resp = client.get(f'/api/v1/vehicles/{query}')
        self.assertEqual(resp.status_code, 200)
        return {v['vin'] for v in resp.json()['results']}

    def detail(self, vehicle, user=None):
        from rest_framework.test import APIClient
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client.get(f'/api/v1/vehicles/{vehicle.pk}/').status_code

    def test_anonymous_sees_only_retail(self):
        self.assertEqual(self.vins(), {'RETAILVIN00000001'})

    def test_buyer_sees_only_retail(self):
        from tests.factories import make_user
        self.assertEqual(self.vins(make_user()), {'RETAILVIN00000001'})

    def test_broker_and_moderator_no_wholesale(self):
        from tests.factories import make_broker, make_moderator
        for user in (make_broker(), make_moderator()):
            with self.subTest(role=user.role):
                self.assertEqual(self.vins(user), {'RETAILVIN00000001'})

    def test_dealer_sees_wholesale(self):
        from tests.factories import make_dealer
        self.assertEqual(self.vins(make_dealer()), {'RETAILVIN00000001', 'WHOLESALEVIN00001'})

    def test_dealer_without_b2b_no_wholesale(self):
        from django.test import override_settings

        from tests.factories import make_dealer
        with override_settings(B2B_ENABLED=False):
            self.assertEqual(self.vins(make_dealer()), {'RETAILVIN00000001'})

    def test_admin_sees_all(self):
        from tests.factories import make_admin_role
        self.assertEqual(len(self.vins(make_admin_role())), 4)

    def test_detail_404_for_hidden(self):
        for vehicle in (self.wholesale, self.no_listing, self.in_container):
            with self.subTest(vin=vehicle.vin):
                self.assertEqual(self.detail(vehicle), 404)
        self.assertEqual(self.detail(self.retail), 200)

    def test_search_wholesale_vin_empty(self):
        self.assertEqual(self.vins(query='?search=WHOLESALEVIN00001'), set())
