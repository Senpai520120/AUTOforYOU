"""Пилот Telegram-каналов (задача 9.57): поле source_channel - формат, нормализация, публичная отдача, права записи."""
from django.contrib.admin.sites import site as admin_site
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from local_listings.models import LocalListing
from local_listings.serializers import (
    LocalListingCreateSerializer,
    LocalListingListSerializer,
    LocalListingUpdateSerializer,
)
from tests.factories import make_local_listing, make_region_city, make_staff, make_user

OPEN = dict(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=True)
GOOD = ['afy_news', 'A1b2c', 'a' * 32, 'Channel_2026']
BAD = ['abcd', 'a' * 33, '1abcde', 'ab cde', 'ab-cde', 'javascript:alert(1)', 'x</script>',
       'https://t.me/abcde', 'абвгде', 'abcde.fi', 'abc\nde', '_abcde']


class ChannelValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region, cls.city = make_region_city()
        cls.owner = make_user()

    def listing(self, channel):
        return LocalListing(
            owner=self.owner, make='Toyota', model='Camry', year=2020, mileage_km=1, fuel_type='petrol',
            transmission='auto', body_type='sedan', price='1', currency='UAH', region=self.region, city=self.city,
            source_channel=channel)

    def test_good_names_pass(self):
        for name in GOOD:
            with self.subTest(name=name):
                self.listing(name).full_clean(exclude=['owner'])

    def test_bad_names_rejected(self):
        for name in BAD:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError) as ctx:
                    self.listing(name).full_clean(exclude=['owner'])
                self.assertIn('source_channel', ctx.exception.message_dict)

    def test_validator_rejects_trailing_newline(self):
        # `$` в Python-regex пропускает завершающий перевод строки; формат обязан его отвергать.
        from local_listings.models import validate_telegram_channel
        with self.assertRaises(ValidationError):
            validate_telegram_channel('afy_news' + chr(10))

    def test_empty_channel_is_allowed(self):
        self.listing('').full_clean(exclude=['owner'])

    def test_at_sign_and_spaces_are_normalized(self):
        obj = self.listing('  @afy_news ')
        obj.full_clean(exclude=['owner'])
        self.assertEqual(obj.source_channel, 'afy_news')

    def test_double_at_is_not_a_valid_name(self):
        with self.assertRaises(ValidationError):
            self.listing('@@afy_news').full_clean(exclude=['owner'])


@override_settings(**OPEN)
class ChannelPublicApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region, cls.city = make_region_city()
        cls.owner = make_user()
        cls.with_channel = make_local_listing(
            cls.owner, region=cls.region, city=cls.city, source_channel='afy_news', contact_phone='+380509998877')
        cls.without = make_local_listing(cls.owner, region=cls.region, city=cls.city)

    def test_list_exposes_channel_and_no_phone(self):
        resp = APIClient().get('/api/v1/local/listings/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        by_id = {r['id']: r for r in resp.json()['results']}
        self.assertEqual(by_id[self.with_channel.pk]['source_channel'], 'afy_news')
        self.assertEqual(by_id[self.without.pk]['source_channel'], '')
        self.assertNotIn('380509998877', resp.content.decode())
        self.assertNotIn('contact_phone', by_id[self.with_channel.pk])

    def test_detail_exposes_channel_without_phone(self):
        resp = APIClient().get(f'/api/v1/local/listings/{self.with_channel.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['source_channel'], 'afy_news')
        self.assertIsNone(resp.json()['contact_phone'])

    def test_channel_is_read_only_everywhere_in_public_api(self):
        self.assertTrue(LocalListingListSerializer().fields['source_channel'].read_only)
        self.assertNotIn('source_channel', LocalListingCreateSerializer().fields)
        self.assertNotIn('source_channel', LocalListingUpdateSerializer().fields)

    def test_owner_cannot_set_channel_through_update(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        resp = client.patch(f'/api/v1/local/listings/{self.without.pk}/', {'source_channel': 'evil_channel'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.without.refresh_from_db()
        self.assertEqual(self.without.source_channel, '')


class ChannelModeratorTests(TestCase):
    def test_moderator_cannot_edit_channel(self):
        from tests.factories import make_moderator
        admin = admin_site._registry[LocalListing]
        request = type('R', (), {'user': make_moderator()})()
        self.assertIn('source_channel', admin.get_readonly_fields(request))


class ChannelAdminTests(TestCase):
    def test_superuser_form_has_the_field_and_it_is_editable(self):
        admin = admin_site._registry[LocalListing]
        user = make_staff(superuser=True)
        request = type('R', (), {'user': user})()
        self.assertIn('source_channel', admin.get_form(request).base_fields)
        self.assertNotIn('source_channel', admin.get_readonly_fields(request))
