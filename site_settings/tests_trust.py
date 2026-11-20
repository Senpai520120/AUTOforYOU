"""10.8: поля блока «Довіра» (about_text, lead_response_hours, lead_next_steps) в публичном API."""
from django.core.cache import cache
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_user

from .models import PUBLIC_CACHE_KEY, SiteSettings
from .serializers import PublicSiteSettingsSerializer

URL = '/api/v1/site-settings/'
TRUST_FIELDS = {'about_text', 'lead_response_hours', 'lead_next_steps'}


class TrustFieldsApiTests(CleanCacheTestCase):
    def test_fields_empty_by_default(self):
        r = APIClient().get(URL)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['about_text'], '')
        self.assertIsNone(data['lead_response_hours'])
        self.assertEqual(data['lead_next_steps'], '')

    def test_values_returned(self):
        s = SiteSettings.load()
        s.about_text = 'Текст про нас'
        s.lead_response_hours = 4
        s.lead_next_steps = 'Крок один\nКрок два'
        s.save()
        data = APIClient().get(URL).json()
        self.assertEqual(data['about_text'], 'Текст про нас')
        self.assertEqual(data['lead_response_hours'], 4)
        self.assertEqual(data['lead_next_steps'], 'Крок один\nКрок два')

    def test_trust_fields_in_serializer_whitelist(self):
        self.assertTrue(TRUST_FIELDS <= set(PublicSiteSettingsSerializer.Meta.fields))
        self.assertTrue(TRUST_FIELDS <= set(APIClient().get(URL).json()))

    def test_response_keys_equal_serializer_whitelist(self):
        self.assertEqual(set(APIClient().get(URL).json()), set(PublicSiteSettingsSerializer.Meta.fields))
        self.assertNotIn('updated_at', APIClient().get(URL).json())

    def test_anonymous_cannot_write(self):
        self.assertEqual(APIClient().patch(URL, {'about_text': 'x'}, format='json').status_code, 405)
        self.assertEqual(SiteSettings.load().about_text, '')

    def test_regular_user_cannot_write(self):
        client = auth_client(make_user())
        self.assertEqual(client.put(URL, {'about_text': 'x'}, format='json').status_code, 405)
        self.assertEqual(SiteSettings.load().about_text, '')

    def test_cache_invalidated_after_about_text_save(self):
        self.assertEqual(APIClient().get(URL).json()['about_text'], '')  # прогрев кэша
        self.assertIsNotNone(cache.get(PUBLIC_CACHE_KEY))
        s = SiteSettings.load()
        s.about_text = 'Новий текст'
        s.save()
        self.assertEqual(APIClient().get(URL).json()['about_text'], 'Новий текст')

    def test_response_hours_zero_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            SiteSettings(lead_response_hours=0).full_clean()
        self.assertIn('lead_response_hours', ctx.exception.message_dict)

    def test_response_hours_empty_allowed(self):
        SiteSettings(lead_response_hours=None).full_clean()


class ListingCheckTipsApiTests(CleanCacheTestCase):
    """10.29: советы «як перевірити авто» - текст владельца, публичное только чтение."""

    def test_empty_by_default(self):
        self.assertEqual(APIClient().get(URL).json()['listing_check_tips'], '')

    def test_value_returned(self):
        s = SiteSettings.load()
        s.listing_check_tips = 'Порада один\nПорада два'
        s.save()
        self.assertEqual(APIClient().get(URL).json()['listing_check_tips'], 'Порада один\nПорада два')

    def test_in_serializer_whitelist(self):
        self.assertIn('listing_check_tips', PublicSiteSettingsSerializer.Meta.fields)

    def test_anonymous_cannot_write(self):
        self.assertEqual(APIClient().patch(URL, {'listing_check_tips': 'x'}, format='json').status_code, 405)
        self.assertEqual(SiteSettings.load().listing_check_tips, '')


class ListingModerationHoursApiTests(CleanCacheTestCase):
    """10.25: срок модерации - необязательное поле владельца; пусто = срок не показывается."""

    def test_empty_by_default(self):
        self.assertIsNone(APIClient().get(URL).json()['listing_moderation_hours'])

    def test_value_returned(self):
        s = SiteSettings.load()
        s.listing_moderation_hours = 24
        s.save()
        self.assertEqual(APIClient().get(URL).json()['listing_moderation_hours'], 24)

    def test_zero_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            SiteSettings(listing_moderation_hours=0).full_clean()
        self.assertIn('listing_moderation_hours', ctx.exception.message_dict)

    def test_anonymous_cannot_write(self):
        self.assertEqual(APIClient().patch(URL, {'listing_moderation_hours': 1}, format='json').status_code, 405)
        self.assertIsNone(SiteSettings.load().listing_moderation_hours)
