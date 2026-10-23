"""Проверка общих фабрик (задача 0.6)."""
from django.test import TestCase

from local_listings.models import LocalListing
from tests.factories import auth_client, make_local_listing, make_user


class FactoriesTest(TestCase):
    def test_make_user_gives_unique_emails(self):
        a, b = make_user(), make_user()
        self.assertNotEqual(a.email, b.email)
        self.assertTrue(a.is_email_verified)
        self.assertFalse(make_user(verified=False).is_email_verified)

    def test_auth_client_passes_profile(self):
        user = make_user()
        resp = auth_client(user).get('/api/v1/auth/profile/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['email'], user.email)

    def test_active_local_listing_visible_in_public_list(self):
        listing = make_local_listing(make_user(), status=LocalListing.Status.ACTIVE)
        resp = auth_client(make_user()).get('/api/v1/local/listings/')
        self.assertEqual(resp.status_code, 200)
        rows = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        self.assertIn(listing.pk, [r['id'] for r in rows])
