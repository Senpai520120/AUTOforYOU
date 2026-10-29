"""Тесты management-команд e2e_seed / e2e_cleanup (задача 0.4)."""
import os
import shutil
import tempfile
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from listings.models import Listing
from local_listings.models import City, LocalListing, Region
from messaging.models import Conversation
from shipments.models import Shipment

User = get_user_model()

# Значение только для тестов; в коде команд пароля по умолчанию нет.
ENV_OK = {'E2E_SEED_ALLOWED': 'true', 'E2E_PASSWORD': 'unit-test-pass-1'}


def _run(name, env):
    out = StringIO()
    with mock.patch.dict(os.environ, env):
        call_command(name, stdout=out, stderr=StringIO())
    return out.getvalue()


def _counts():
    return {
        'users': User.objects.count(),
        'local': LocalListing.objects.count(),
        'listings': Listing.objects.count(),
        'shipments': Shipment.objects.count(),
        'conversations': Conversation.objects.count(),
    }


class E2ESeedTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)

    def test_without_flag_raises_and_creates_nothing(self):
        env = {'E2E_PASSWORD': 'x-pass'}
        with mock.patch.dict(os.environ, env):
            os.environ.pop('E2E_SEED_ALLOWED', None)
            with self.assertRaises(CommandError):
                call_command('e2e_seed', stdout=StringIO())
        self.assertEqual(User.objects.count(), 0)

    def test_flag_false_raises(self):
        with mock.patch.dict(os.environ, {'E2E_SEED_ALLOWED': 'false', 'E2E_PASSWORD': 'x'}):
            with self.assertRaises(CommandError):
                call_command('e2e_seed', stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command('e2e_cleanup', stdout=StringIO())

    def test_without_password_raises(self):
        with mock.patch.dict(os.environ, {'E2E_SEED_ALLOWED': 'true'}):
            os.environ.pop('E2E_PASSWORD', None)
            with self.assertRaises(CommandError):
                call_command('e2e_seed', stdout=StringIO())
        with mock.patch.dict(os.environ, {'E2E_SEED_ALLOWED': 'true', 'E2E_PASSWORD': ''}):
            with self.assertRaises(CommandError):
                call_command('e2e_seed', stdout=StringIO())
        self.assertEqual(User.objects.count(), 0)

    def test_seed_is_idempotent_and_correct(self):
        _run('e2e_seed', ENV_OK)
        first = _counts()
        _run('e2e_seed', ENV_OK)
        self.assertEqual(first, _counts())

        self.assertEqual(first['users'], 6)
        self.assertEqual(first['local'], 2)
        self.assertEqual(first['listings'], 2)
        self.assertEqual(first['shipments'], 1)
        self.assertEqual(first['conversations'], 1)
        for user in User.objects.all():
            self.assertTrue(user.email.endswith('@e2e.test'))
            self.assertTrue(user.check_password(ENV_OK['E2E_PASSWORD']))
            self.assertTrue(user.is_email_verified)
        self.assertTrue(User.objects.get(email='dealer@e2e.test').is_verified_dealer)
        self.assertTrue(User.objects.get(email='staff@e2e.test').is_staff)
        self.assertEqual(
            set(LocalListing.objects.values_list('status', flat=True)), {'active', 'pending'},
        )
        for ll in LocalListing.objects.all():
            self.assertTrue(ll.description.startswith('[E2E]'))
            self.assertEqual(ll.images.count(), 1)
        self.assertEqual(
            set(Listing.objects.values_list('channel', flat=True)), {'retail', 'wholesale'},
        )
        buyer = User.objects.get(email='buyer@e2e.test')
        self.assertEqual(Shipment.objects.get().watchers.get(), buyer)
        # Страницы моделей (2.16): опубликована та, у которой считается расчёт; черновик остаётся черновиком.
        from landings.models import ModelLandingPage
        self.assertTrue(ModelLandingPage.objects.get(slug='e2e-toyota-camry').is_published)
        self.assertFalse(ModelLandingPage.objects.get(slug='e2e-draft').is_published)

    def test_cleanup_removes_only_e2e(self):
        real = User.objects.create_user(email='real@example.com', password='p')
        region = Region.objects.create(name='R', slug='r')
        city = City.objects.create(region=region, name='C', slug='c')
        real_listing = LocalListing.objects.create(
            owner=real, make='Audi', model='A4', year=2015, mileage_km=1, fuel_type='petrol',
            transmission='auto', body_type='sedan', price=1, region=region, city=city,
            description='обычное объявление',
        )
        _run('e2e_seed', ENV_OK)
        self.assertEqual(User.objects.count(), 7)

        out = _run('e2e_cleanup', ENV_OK)
        self.assertIn('удалено', out)
        self.assertEqual(list(User.objects.values_list('email', flat=True)), ['real@example.com'])
        self.assertTrue(LocalListing.objects.filter(pk=real_listing.pk).exists())
        self.assertEqual(LocalListing.objects.count(), 1)
        self.assertEqual(Listing.objects.count(), 0)
        self.assertEqual(Shipment.objects.count(), 0)
        self.assertEqual(Conversation.objects.count(), 0)
        from landings.models import ModelLandingPage
        self.assertEqual(ModelLandingPage.objects.count(), 0)
        # справочники остаются
        self.assertTrue(Region.objects.filter(pk=region.pk).exists())
