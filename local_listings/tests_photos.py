"""Задача 8.4: ресайз, миниатюры, минимум фото, удаление файлов, regenerate_listing_photos."""
import io
import os
from io import StringIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from core.uploads import make_thumbnail, sanitize_image
from tests.factories import auth_client, make_local_listing, make_moderator, make_user
from tests.test_uploads import image_bytes, use_temp_media

from .models import LocalListing, LocalListingImage
from .services import ListingNotReadyError, approve_listing

EXIF_MARKER = b'Exif\x00\x00'


def size_of(data_or_file):
    if hasattr(data_or_file, 'open'):
        with data_or_file.open('rb') as fh:
            return Image.open(io.BytesIO(fh.read())).size
    return Image.open(io.BytesIO(data_or_file)).size


def files_in(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file())


class TestResizeService(APITestCase):
    def test_large_jpeg_is_shrunk_keeping_ratio(self):
        out = sanitize_image(io.BytesIO(image_bytes(size=(4000, 3000))), max_side=800)
        self.assertEqual(size_of(out.read()), (800, 600))

    def test_small_image_not_enlarged(self):
        out = sanitize_image(io.BytesIO(image_bytes(size=(300, 200))), max_side=800)
        self.assertEqual(size_of(out.read()), (300, 200))

    def test_format_preserved_and_png_keeps_alpha(self):
        for fmt, ext in (('JPEG', 'jpg'), ('PNG', 'png'), ('WEBP', 'webp')):
            with self.subTest(fmt=fmt):
                out = sanitize_image(io.BytesIO(image_bytes(fmt, size=(1200, 900))), max_side=600)
                self.assertTrue(out.name.endswith(f'.{ext}'))
                self.assertEqual(Image.open(io.BytesIO(out.read())).format, fmt)
        png = make_thumbnail(io.BytesIO(image_bytes('PNG', size=(900, 900), mode='RGBA')), max_side=100)
        self.assertEqual(Image.open(io.BytesIO(png.read())).mode, 'RGBA')

    def test_orientation_applied_before_resize(self):
        # 6 = поворот на 90°: 2000x1000 после поворота - 1000x2000, max_side по высоте
        out = sanitize_image(io.BytesIO(image_bytes(size=(2000, 1000), orientation=6)), max_side=500)
        self.assertEqual(size_of(out.read()), (250, 500))

    def test_without_max_side_no_resize(self):
        out = sanitize_image(io.BytesIO(image_bytes(size=(2500, 1000))))
        self.assertEqual(size_of(out.read()), (2500, 1000))


@override_settings(LOCAL_LISTING_PHOTO_MAX_SIDE=800, LOCAL_LISTING_THUMB_MAX_SIDE=120, LOCAL_LISTING_MIN_PHOTOS=1)
class TestUploadPipeline(APITestCase):
    def setUp(self):
        self.media = use_temp_media(self)
        self.owner = make_user()
        self.listing = make_local_listing(self.owner)
        self.client = auth_client(self.owner)
        self.url = f'/api/v1/local/listings/{self.listing.pk}/images/'

    def upload(self, *blobs):
        files = [SimpleUploadedFile(f'my-home-{i}.jpg', b, content_type='image/jpeg') for i, b in enumerate(blobs)]
        return self.client.post(self.url, {'images': files}, format='multipart')

    def test_resized_original_and_thumbnail_without_exif(self):
        resp = self.upload(image_bytes(size=(3000, 2000), gps=True))
        self.assertEqual(resp.status_code, 201)
        img = LocalListingImage.objects.get()
        self.assertEqual(size_of(img.image), (800, 533))
        self.assertLessEqual(max(size_of(img.thumbnail)), 120)
        self.assertRegex(img.thumbnail.name, r'^local_listings/thumbs/[0-9a-f]{32}\.jpg$')
        for f in (img.image, img.thumbnail):
            with f.open('rb') as fh:
                self.assertNotIn(EXIF_MARKER, fh.read())
        self.assertRegex(resp.json()[0]['thumbnail'], r'/media/local_listings/thumbs/[0-9a-f]{32}\.jpg$')

    def test_three_files_three_thumbnails(self):
        self.assertEqual(self.upload(*[image_bytes(size=(900, 900))] * 3).status_code, 201)
        self.assertEqual(LocalListingImage.objects.exclude(thumbnail='').count(), 3)

    def test_one_broken_file_nothing_written(self):
        resp = self.upload(image_bytes(), b'not an image', image_bytes())
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(LocalListingImage.objects.exists())
        self.assertEqual(files_in(self.media), [])

    def test_serializer_thumbnail_null_for_old_photo(self):
        LocalListingImage.objects.create(listing=self.listing, image=ContentFile(image_bytes(), name='x.jpg'))
        data = APIClient().get(f'/api/v1/local/listings/{self.listing.pk}/').json()
        self.assertIsNone(data['images'][0]['thumbnail'])

    def test_delete_photo_removes_both_files(self):
        self.upload(image_bytes(), image_bytes())
        img = LocalListingImage.objects.first()
        names = [img.image.name, img.thumbnail.name]
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.delete(f'{self.url}{img.pk}/')
        self.assertEqual(resp.status_code, 204)
        for name in names:
            self.assertFalse(os.path.exists(os.path.join(self.media, name)))

    def test_listing_cascade_removes_files_and_missing_file_ok(self):
        self.upload(image_bytes())
        img = LocalListingImage.objects.get()
        os.remove(img.thumbnail.path)  # файл уже пропал - удаление не падает
        with self.captureOnCommitCallbacks(execute=True):
            LocalListing.objects.filter(pk=self.listing.pk).delete()
        self.assertEqual(files_in(self.media), [])


@override_settings(LOCAL_LISTING_MIN_PHOTOS=1)
class TestMinPhotos(APITestCase):
    def setUp(self):
        self.media = use_temp_media(self)
        self.owner = make_user()
        self.moderator = make_moderator()
        self.listing = make_local_listing(self.owner, status=LocalListing.Status.PENDING)

    def add_photo(self, listing=None):
        return LocalListingImage.objects.create(
            listing=listing or self.listing, image=ContentFile(image_bytes(), name='p.jpg'))

    def test_approve_without_photos_raises_and_keeps_status(self):
        with self.assertRaisesMessage(ListingNotReadyError, 'Недостатньо фото: потрібно щонайменше 1.'):
            approve_listing(self.listing, self.moderator)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.PENDING)

    def test_approve_with_photo(self):
        self.add_photo()
        approve_listing(self.listing, self.moderator)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)

    @override_settings(LOCAL_LISTING_MIN_PHOTOS=0)
    def test_min_zero_approves_without_photos(self):
        approve_listing(self.listing, self.moderator)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)

    def test_admin_action_shows_message_and_does_not_approve(self):
        client = Client()
        client.force_login(self.moderator)
        resp = client.post('/admin/local_listings/locallisting/', {
            'action': 'approve_listings', '_selected_action': [self.listing.pk],
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Недостатньо фото: потрібно щонайменше 1.')
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.PENDING)

    def test_admin_enough_photos_filter(self):
        other = make_local_listing(self.owner, status=LocalListing.Status.PENDING)
        self.add_photo(other)
        client = Client()
        client.force_login(self.moderator)
        resp = client.get('/admin/local_listings/locallisting/', {'enough_photos': 'yes'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([o.pk for o in resp.context['cl'].result_list], [other.pk])

    def test_delete_last_photo_is_400_then_ok_with_two(self):
        img = self.add_photo()
        client = auth_client(self.owner)
        url = f'/api/v1/local/listings/{self.listing.pk}/images/{img.pk}/'
        resp = client.delete(url)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['detail'], 'Не можна видалити: потрібно щонайменше 1 фото.')
        self.add_photo()
        self.assertEqual(client.delete(url).status_code, 204)

    @override_settings(LOCAL_LISTING_MIN_PHOTOS=0)
    def test_delete_last_photo_ok_when_min_zero(self):
        img = self.add_photo()
        resp = auth_client(self.owner).delete(f'/api/v1/local/listings/{self.listing.pk}/images/{img.pk}/')
        self.assertEqual(resp.status_code, 204)

    def test_config_and_owner_photos_count(self):
        self.assertEqual(APIClient().get('/api/v1/local/config/').json()['min_photos'], 1)
        self.add_photo()
        data = auth_client(self.owner).get(f'/api/v1/local/my-listings/{self.listing.pk}/').json()
        self.assertEqual(data['photos_count'], 1)
        public = APIClient().get('/api/v1/local/listings/').json()
        rows = public['results'] if isinstance(public, dict) else public
        for row in rows:
            self.assertNotIn('photos_count', row)


@override_settings(LOCAL_LISTING_PHOTO_MAX_SIDE=500, LOCAL_LISTING_THUMB_MAX_SIDE=100)
class TestRegenerateCommand(APITestCase):
    def setUp(self):
        self.media = use_temp_media(self)
        self.listing = make_local_listing(make_user())

    def old_photo(self, size=(1600, 1200)):
        # как фото до 8.4: оригинал без ресайза, без миниатюры
        content = sanitize_image(io.BytesIO(image_bytes(size=size)))
        return LocalListingImage.objects.create(listing=self.listing, image=content)

    def run_cmd(self, *args):
        out = StringIO()
        call_command('regenerate_listing_photos', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        img = self.old_photo()
        self.run_cmd('--dry-run', '--resize-originals')
        img.refresh_from_db()
        self.assertFalse(img.thumbnail)
        self.assertEqual(size_of(img.image), (1600, 1200))

    def test_creates_thumbnails_idempotent(self):
        img = self.old_photo()
        self.run_cmd()
        img.refresh_from_db()
        first = img.thumbnail.name
        self.assertLessEqual(max(size_of(img.thumbnail)), 100)
        out = self.run_cmd()
        img.refresh_from_db()
        self.assertEqual(img.thumbnail.name, first)
        self.assertIn('мініатюр 0', out)

    def test_resize_originals_replaces_and_deletes_old(self):
        img = self.old_photo()
        old_path = img.image.path
        self.run_cmd('--resize-originals')
        img.refresh_from_db()
        self.assertEqual(max(size_of(img.image)), 500)
        self.assertFalse(os.path.exists(old_path))

    def test_broken_file_reported_not_deleted(self):
        img = self.old_photo()
        with open(img.image.path, 'wb') as fh:
            fh.write(b'broken')
        out = self.run_cmd()
        self.assertIn(f'#{img.pk}', out)
        self.assertTrue(os.path.exists(img.image.path))
