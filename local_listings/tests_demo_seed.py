"""seed_demo_listings: защита флагом, идемпотентность, --clear только для [DEMO]."""
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from tests.factories import make_local_listing, make_region_city, make_user
from tests.test_uploads import image_bytes, use_temp_media

from .management.commands.seed_demo_listings import DEMO_CARS, DEMO_EMAIL, DEMO_PREFIX
from .models import LocalListing, LocalListingImage


class DemoSeedTests(TestCase):
    def setUp(self):
        self.media = use_temp_media(self)
        make_region_city()
        photos = tempfile.TemporaryDirectory()
        self.addCleanup(photos.cleanup)
        self.photos = Path(photos.name)
        for n in (1, 2):
            (self.photos / f'{DEMO_CARS[0][0]}-{n}.jpg').write_bytes(image_bytes())
        (self.photos / 'CREDITS.txt').write_text(
            'file\tlicense\tsource\n'
            f'{DEMO_CARS[0][0]}-1.jpg\tCC BY-SA 4.0\thttps://commons.wikimedia.org/wiki/File:A.jpg\n',
            encoding='utf-8',
        )

    def run_cmd(self, *args, allowed=True):
        out = StringIO()
        env = {'DEMO_SEED_ALLOWED': 'true'} if allowed else {'DEMO_SEED_ALLOWED': ''}
        with mock.patch.dict('os.environ', env):
            call_command('seed_demo_listings', '--photos-dir', str(self.photos), *args, stdout=out)
        return out.getvalue()

    def test_without_flag_command_error(self):
        with self.assertRaisesMessage(CommandError, 'DEMO_SEED_ALLOWED'):
            self.run_cmd(allowed=False)
        self.assertEqual(LocalListing.objects.count(), 0)

    def test_creates_listings_with_photos(self):
        self.assertEqual(self.run_cmd().strip(), f'создано: {len(DEMO_CARS)}, было: 0, фото: 2')
        listing = LocalListing.objects.get(make='Toyota')
        self.assertTrue(listing.description.startswith(DEMO_PREFIX))
        self.assertIn('commons.wikimedia.org', listing.description)
        self.assertEqual(listing.status, LocalListing.Status.ACTIVE)
        self.assertIsNotNone(listing.moderated_at)
        self.assertEqual(listing.owner.email, DEMO_EMAIL)
        self.assertEqual(listing.contact_phone, listing.owner.verified_phone)
        images = list(listing.images.all())
        self.assertEqual(len(images), 2)
        self.assertEqual(sum(i.is_primary for i in images), 1)
        self.assertTrue(all(i.image and i.thumbnail for i in images))

    def test_repeat_does_not_duplicate(self):
        self.run_cmd()
        out = self.run_cmd()
        self.assertEqual(out.strip(), f'создано: 0, было: {len(DEMO_CARS)}, фото: 0')
        self.assertEqual(LocalListing.objects.count(), len(DEMO_CARS))
        self.assertEqual(LocalListingImage.objects.count(), 2)

    def test_clear_removes_only_demo(self):
        other = make_local_listing(make_user(email='real@example.com'), description='Звичайне оголошення')
        self.run_cmd()
        self.assertEqual(len(list(Path(self.media).rglob('*.jpg'))), 4)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.run_cmd('--clear').strip(), f'удалено: {len(DEMO_CARS)}')
        self.assertEqual(list(LocalListing.objects.values_list('pk', flat=True)), [other.pk])
        self.assertEqual(LocalListingImage.objects.count(), 0)
        self.assertEqual(list(Path(self.media).rglob('*.jpg')), [])
