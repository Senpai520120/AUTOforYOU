from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import TelegramLinkToken

User = get_user_model()


# ─── TelegramLinkToken model ─────────────────────────────────────────────────

class TelegramLinkTokenModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='token@test.com', password='pass')

    def _make(self, **kw):
        defaults = {'user': self.user, 'expires_at': timezone.now() + timedelta(minutes=30)}
        defaults.update(kw)
        return TelegramLinkToken.objects.create(**defaults)

    def test_valid_token(self):
        self.assertTrue(self._make().is_valid())

    def test_expired_token(self):
        t = self._make(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(t.is_valid())

    def test_used_token(self):
        self.assertFalse(self._make(used=True).is_valid())


# ─── Link-token API ───────────────────────────────────────────────────────────

class TelegramLinkApiTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='api@test.com', password='pass')
        self.client = APIClient()

    def test_unauth_returns_401(self):
        r = self.client.get('/api/v1/telegram/link-token/')
        self.assertEqual(r.status_code, 401)

    def test_authenticated_returns_token(self):
        self.client.force_authenticate(self.user)
        r = self.client.get('/api/v1/telegram/link-token/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('token', r.data)
        self.assertIn('expires_at', r.data)
        self.assertTrue(TelegramLinkToken.objects.filter(user=self.user).exists())


# ─── Deep-link: привязка аккаунта ────────────────────────────────────────────

class TelegramLinkFlowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='link@test.com', password='pass')

    def _make_token(self, **kw):
        defaults = {'user': self.user, 'expires_at': timezone.now() + timedelta(minutes=10)}
        defaults.update(kw)
        return TelegramLinkToken.objects.create(**defaults)

    def test_valid_token_links_user(self):
        token_obj = self._make_token()
        # Simulate what the /start deeplink handler does
        self.user.telegram_id = 999001
        self.user.save()
        token_obj.used = True
        token_obj.save()

        self.user.refresh_from_db()
        token_obj.refresh_from_db()
        self.assertEqual(self.user.telegram_id, 999001)
        self.assertTrue(token_obj.used)
        self.assertFalse(token_obj.is_valid())

    def test_expired_token_is_invalid(self):
        token_obj = self._make_token(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertFalse(token_obj.is_valid())

    def test_used_token_is_invalid(self):
        token_obj = self._make_token(used=True)
        self.assertFalse(token_obj.is_valid())

    def test_token_marks_used_after_link(self):
        token_obj = self._make_token()
        self.assertTrue(token_obj.is_valid())
        token_obj.used = True
        token_obj.save()
        token_obj.refresh_from_db()
        self.assertTrue(token_obj.used)


# ─── send_notification task ───────────────────────────────────────────────────

class SendNotificationTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='notify@test.com', password='pass')

    def test_no_token_returns_no_send(self):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN=''):
            result = send_notification(self.user.pk, 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'no token')

    def test_unlinked_user_skipped(self):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN='fake-token'):
            result = send_notification(self.user.pk, 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'not linked')

    def test_nonexistent_user_handled(self):
        from integrations.tasks import send_notification
        with self.settings(TELEGRAM_BOT_TOKEN='fake-token'):
            result = send_notification(999999, 'Hello')
        self.assertFalse(result['sent'])
        self.assertEqual(result['reason'], 'user not found')

    def test_linked_user_sends(self):
        from integrations.tasks import send_notification
        self.user.telegram_id = 123456789
        self.user.save()

        with self.settings(TELEGRAM_BOT_TOKEN='fake-token'):
            with patch('asyncio.run', return_value=True):
                result = send_notification(self.user.pk, 'Hello')
        self.assertTrue(result['sent'])


# ─── post_listing_to_channel task ────────────────────────────────────────────

class PostListingToChannelTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='seller@test.com', password='pass')

    def test_no_token_skips(self):
        from telegram_bot.tasks import post_listing_to_channel
        with self.settings(TELEGRAM_BOT_TOKEN=''):
            result = post_listing_to_channel(1)
        self.assertFalse(result['posted'])
        self.assertEqual(result['reason'], 'no token')

    def test_listing_not_found(self):
        from telegram_bot.tasks import post_listing_to_channel
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHANNEL_ID='@ch'):
            result = post_listing_to_channel(999999)
        self.assertFalse(result['posted'])
        self.assertEqual(result['reason'], 'listing not found')

    def test_no_channel_id_skips(self):
        from telegram_bot.tasks import post_listing_to_channel
        from vehicles.models import Vehicle
        from listings.models import Listing

        v = Vehicle.objects.create(
            vin='1HGBH41JXMN109186', make='Toyota', model='Camry', year=2020,
            engine_cc=2000, fuel_type='petrol', mileage_km=10000,
        )
        listing = Listing.objects.create(
            vehicle=v, seller=self.user, price='15000.00', channel='retail',
        )
        with self.settings(TELEGRAM_BOT_TOKEN='fake', TELEGRAM_CHANNEL_ID='', TELEGRAM_B2B_CHANNEL_ID=''):
            result = post_listing_to_channel(listing.pk)
        self.assertFalse(result['posted'])
        self.assertEqual(result['reason'], 'no channel_id')


# ─── Autopost signal ─────────────────────────────────────────────────────────

class ListingAutopostSignalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='signal@test.com', password='pass')

    def _make_vehicle(self):
        from vehicles.models import Vehicle
        return Vehicle.objects.create(
            vin='JT2BF22K1W0066065', make='Honda', model='Civic', year=2019,
            engine_cc=1500, fuel_type='petrol', mileage_km=30000,
        )

    def test_new_retail_listing_schedules_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            Listing.objects.create(
                vehicle=v, seller=self.user, price='12000.00', channel='retail',
            )
            mock_delay.assert_called_once()

    def test_new_express_buyout_wholesale_schedules_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            Listing.objects.create(
                vehicle=v, seller=self.user, price='8000.00',
                channel='wholesale', is_express_buyout=True,
            )
            mock_delay.assert_called_once()

    def test_regular_wholesale_does_not_schedule_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            Listing.objects.create(
                vehicle=v, seller=self.user, price='8000.00', channel='wholesale',
            )
            mock_delay.assert_not_called()

    def test_listing_update_does_not_schedule_task(self):
        from listings.models import Listing
        v = self._make_vehicle()
        listing = Listing.objects.create(
            vehicle=v, seller=self.user, price='12000.00', channel='retail',
        )
        with patch('telegram_bot.tasks.post_listing_to_channel.delay') as mock_delay:
            listing.price = '13000.00'
            listing.save()
            mock_delay.assert_not_called()
