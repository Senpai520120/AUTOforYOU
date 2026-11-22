"""Задача 10.30: удаление фото rejected/sold объявлений."""
from datetime import timedelta
from io import StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from tests.factories import auth_client, make_local_listing, make_user
from tests.test_uploads import image_bytes, use_temp_media

from .models import LocalListing, LocalListingImage
from .tasks import purge_closed_listing_photos

S = LocalListing.Status


class PurgeBase(TestCase):
    def setUp(self):
        self.media = use_temp_media(self)
        self.owner = make_user(email='seller@example.com')

    def listing_with_photo(self, status, days_old=40):
        listing = make_local_listing(self.owner, status=status)
        img = LocalListingImage(listing=listing)
        img.image.save('p.jpg', ContentFile(image_bytes()), save=False)
        img.thumbnail.save('t.jpg', ContentFile(image_bytes()), save=False)
        img.save()
        LocalListing.objects.filter(pk=listing.pk).update(updated_at=timezone.now() - timedelta(days=days_old))
        listing.refresh_from_db()
        return listing, img

    def files(self):
        from pathlib import Path
        return [p for p in Path(self.media).rglob('*') if p.is_file()]


@override_settings(LOCAL_LISTING_PHOTO_PURGE_DAYS=30)
class PurgeTaskTests(PurgeBase):
    def test_old_rejected_and_sold_photos_deleted_with_files(self):
        for status in (S.REJECTED, S.SOLD):
            self.listing_with_photo(status)
        self.assertEqual(len(self.files()), 4)
        with self.captureOnCommitCallbacks(execute=True):
            result = purge_closed_listing_photos()
        self.assertEqual(result, 'listings=2 photos=2')
        self.assertEqual(LocalListingImage.objects.count(), 0)
        self.assertEqual(self.files(), [])

    def test_recent_rejected_kept(self):
        self.listing_with_photo(S.REJECTED, days_old=5)
        purge_closed_listing_photos()
        self.assertEqual(LocalListingImage.objects.count(), 1)

    def test_active_pending_hidden_expired_untouched(self):
        for status in (S.ACTIVE, S.PENDING, S.HIDDEN, S.EXPIRED):
            self.listing_with_photo(status)
        with self.captureOnCommitCallbacks(execute=True):
            purge_closed_listing_photos()
        self.assertEqual(LocalListingImage.objects.count(), 4)
        self.assertEqual(len(self.files()), 8)

    def test_repeat_is_idempotent(self):
        self.listing_with_photo(S.REJECTED)
        with self.captureOnCommitCallbacks(execute=True):
            purge_closed_listing_photos()
        self.assertEqual(purge_closed_listing_photos(), 'listings=0 photos=0')

    def test_beat_schedule_has_task(self):
        from django.conf import settings
        self.assertEqual(
            settings.CELERY_BEAT_SCHEDULE['purge-closed-listing-photos-daily']['task'],
            'local_listings.tasks.purge_closed_listing_photos',
        )


@override_settings(LOCAL_LISTING_PHOTO_PURGE_DAYS=30)
class PurgeCommandTests(PurgeBase):
    def run_cmd(self, *args):
        out = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command('purge_listing_photos', *args, stdout=out)
        return out.getvalue()

    def test_default_is_dry_run(self):
        self.listing_with_photo(S.REJECTED)
        out = self.run_cmd()
        self.assertIn('оголошень 1, фото 1', out)
        self.assertEqual(LocalListingImage.objects.count(), 1)
        self.assertEqual(len(self.files()), 2)

    def test_apply_deletes_and_repeat_finds_nothing(self):
        self.listing_with_photo(S.SOLD)
        self.assertIn('Видалено: оголошень 1, фото 1', self.run_cmd('--apply'))
        self.assertEqual(LocalListingImage.objects.count(), 0)
        self.assertEqual(self.files(), [])
        self.assertIn('оголошень 0, фото 0', self.run_cmd('--apply'))

    def test_apply_skips_active(self):
        self.listing_with_photo(S.ACTIVE)
        self.run_cmd('--apply')
        self.assertEqual(LocalListingImage.objects.count(), 1)

    def test_output_has_no_personal_data(self):
        self.listing_with_photo(S.REJECTED)
        self.assertNotIn('seller@example.com', self.run_cmd('--apply'))


@override_settings(LOCAL_LISTING_PHOTO_PURGE_DAYS=30, LOCAL_LISTING_MIN_PHOTOS=1)
class ResubmitAfterPurgeTests(PurgeBase):
    def test_rejected_without_photos_cannot_return_to_moderation(self):
        listing = make_local_listing(self.owner, status=S.REJECTED)
        resp = auth_client(self.owner).patch(
            f'/api/v1/local/listings/{listing.pk}/', {'description': 'Нове'}, format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Завантажте фото заново', str(resp.json()))
        listing.refresh_from_db()
        self.assertEqual(listing.status, S.REJECTED)
