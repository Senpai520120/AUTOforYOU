"""Задача 4.5a: показ телефона гостю после капчи, журнал ContactView, лимиты, аномалии, очистка, админка.

Turnstile мокается (httpx.post), сеть не трогается. По умолчанию в тестах CAPTCHA_PROVIDER=off.
"""
import hashlib
import hmac
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from core.launch import ERROR, INFO, OK, WARNING, check_phone_log_salt
from notifications.models import Notification
from tests.factories import auth_client, make_local_listing, make_moderator, make_staff, make_user

from .models import ContactView, LocalListing
from .tasks import cleanup_contact_views
from .throttles import GuestContactThrottle, ip_hash

SALT = 'test-phone-log-salt'
PHONE = '+380501234567'
TURNSTILE = dict(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='sk', TURNSTILE_SITE_KEY='pk')


def _rates(**changes):
    """DRF читает ставки один раз при импорте (SimpleRateThrottle.THROTTLE_RATES) - подменяем атрибут."""
    rates = dict(SimpleRateThrottle.THROTTLE_RATES)
    rates.update(changes)
    return mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates)


def _turnstile(success=True):
    response = mock.Mock()
    response.json.return_value = {'success': success}
    return mock.patch('httpx.post', return_value=response)


class ContactBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_user()
        self.listing = make_local_listing(self.owner, contact_phone=PHONE)

    def url(self, listing=None):
        return f'/api/v1/local/listings/{(listing or self.listing).pk}/contact/'

    def guest_post(self, listing=None, ip='203.0.113.7', body=None, **extra):
        return APIClient().post(self.url(listing), body if body is not None else {'captcha_token': 't'},
                                format='json', REMOTE_ADDR=ip, **extra)


@override_settings(PHONE_LOG_IP_SALT=SALT, **TURNSTILE)
class TestGuestPhone(ContactBase):

    def test_guest_with_valid_captcha_gets_phone_and_log(self):
        with _turnstile(True):
            resp = self.guest_post()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json(), {'contact_phone': PHONE})
        view = ContactView.objects.get()
        self.assertTrue(view.is_guest)
        self.assertIsNone(view.user_id)
        self.assertEqual(view.listing_id, self.listing.pk)

    def test_guest_without_token_is_400_no_phone_no_log(self):
        with _turnstile(True):
            resp = self.guest_post(body={})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['code'], 'captcha_failed')
        self.assertNotIn(PHONE, resp.content.decode())
        self.assertFalse(ContactView.objects.exists())

    def test_guest_invalid_token_is_400(self):
        with _turnstile(False):
            resp = self.guest_post()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn(PHONE, resp.content.decode())
        self.assertFalse(ContactView.objects.exists())

    @override_settings(CAPTCHA_PROVIDER='honeypot', TURNSTILE_SECRET_KEY='')
    def test_honeypot_filled_is_refused(self):
        resp = self.guest_post(body={'website': 'http://spam', 'captcha_token': 'x'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn(PHONE, resp.content.decode())
        self.assertFalse(ContactView.objects.exists())

    def test_non_active_is_404_without_log(self):
        for st in LocalListing.Status:
            if st == LocalListing.Status.ACTIVE:
                continue
            LocalListing.objects.filter(pk=self.listing.pk).update(status=st)
            with self.subTest(status=st), _turnstile(True):
                resp = self.guest_post()
                self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
                self.assertNotIn(PHONE, resp.content.decode())
        self.assertFalse(ContactView.objects.exists())

    def test_anonymous_get_still_401(self):
        self.assertEqual(APIClient().get(self.url()).status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(PHONE_LOG_IP_SALT='')
    def test_empty_salt_is_503_without_phone_and_log(self):
        with _turnstile(True):
            resp = self.guest_post()
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn(PHONE, resp.content.decode())
        self.assertFalse(ContactView.objects.exists())

    @_rates(contact_guest='2/day')
    def test_guest_daily_limit_third_is_429(self):
        with _turnstile(True):
            for _ in range(2):
                self.assertEqual(self.guest_post().status_code, status.HTTP_200_OK)
            resp = self.guest_post()
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(resp.json()['detail'], 'Ліміт переглядів телефонів на сьогодні вичерпано')
        self.assertIn('Retry-After', resp)
        self.assertNotIn(PHONE, resp.content.decode())
        self.assertEqual(ContactView.objects.count(), 2)

    @_rates(contact_guest='1/day')
    def test_limits_are_per_ip(self):
        with _turnstile(True):
            self.assertEqual(self.guest_post(ip='203.0.113.1').status_code, status.HTTP_200_OK)
            self.assertEqual(self.guest_post(ip='203.0.113.2').status_code, status.HTTP_200_OK)
            self.assertEqual(self.guest_post(ip='203.0.113.1').status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @_rates(contact_guest='1/day')
    def test_captcha_failure_does_not_consume_guest_limit(self):
        with _turnstile(False):
            self.assertEqual(self.guest_post().status_code, status.HTTP_400_BAD_REQUEST)
        with _turnstile(True):
            self.assertEqual(self.guest_post().status_code, status.HTTP_200_OK)

    @_rates(contact_guest='1/day')
    @mock.patch('rest_framework.throttling.api_settings.NUM_PROXIES', 1)
    def test_spoofed_x_forwarded_for_does_not_bypass_limit(self):
        with _turnstile(True):
            first = self.guest_post(ip='10.0.0.1', HTTP_X_FORWARDED_FOR='1.1.1.1, 198.51.100.9')
            self.assertEqual(first.status_code, status.HTTP_200_OK)
            again = self.guest_post(ip='10.0.0.1', HTTP_X_FORWARDED_FOR='2.2.2.2, 198.51.100.9')
        self.assertEqual(again.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @_rates(contact_guest='1/day')
    @mock.patch('rest_framework.throttling.api_settings.NUM_PROXIES', 0)
    def test_x_forwarded_for_ignored_without_proxies(self):
        with _turnstile(True):
            self.assertEqual(self.guest_post(HTTP_X_FORWARDED_FOR='1.1.1.1').status_code, status.HTTP_200_OK)
            again = self.guest_post(HTTP_X_FORWARDED_FOR='2.2.2.2')
        self.assertEqual(again.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @_rates(contact_guest='1/day')
    def test_over_limit_does_not_check_captcha(self):
        with _turnstile(True):
            self.assertEqual(self.guest_post().status_code, status.HTTP_200_OK)
        with _turnstile(True) as verify:
            self.assertEqual(self.guest_post().status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        verify.assert_not_called()

    @_rates(contact_guest='1/day')
    def test_parallel_requests_cannot_share_one_slot(self):
        """Ревью 4.5a: два запроса прошли проверку раньше, чем любой показал номер - второму слота нет."""
        request = mock.Mock(META={'REMOTE_ADDR': '203.0.113.9'}, user=mock.Mock(is_authenticated=False))
        first, second = GuestContactThrottle(), GuestContactThrottle()
        self.assertTrue(first.allow_request(request, None))
        self.assertFalse(second.allow_request(request, None))
        first.release()
        self.assertTrue(GuestContactThrottle().allow_request(request, None))

    def test_404_does_not_consume_guest_limit(self):
        LocalListing.objects.filter(pk=self.listing.pk).update(status=LocalListing.Status.PENDING)
        with _rates(contact_guest='1/day'), _turnstile(True):
            self.assertEqual(self.guest_post().status_code, status.HTTP_404_NOT_FOUND)
            LocalListing.objects.filter(pk=self.listing.pk).update(status=LocalListing.Status.ACTIVE)
            self.assertEqual(self.guest_post().status_code, status.HTTP_200_OK)

    @override_settings(CAPTCHA_PROVIDER='off')
    def test_captcha_off_is_503_for_guest(self):
        resp = self.guest_post()
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertNotIn(PHONE, resp.content.decode())
        self.assertFalse(ContactView.objects.exists())

    def test_anon_throttle_key_has_no_ip(self):
        from .throttles import GuestAnonThrottle
        ip = '203.0.113.56'
        request = mock.Mock(META={'REMOTE_ADDR': ip}, user=mock.Mock(is_authenticated=False))
        key = GuestAnonThrottle().get_cache_key(request, None)
        self.assertNotIn(ip, key)
        self.assertIn(ip_hash(ip), key)

    def test_ip_stored_only_as_salted_hash(self):
        ip = '203.0.113.77'
        with _turnstile(True):
            self.guest_post(ip=ip)
        view = ContactView.objects.get()
        expected = hmac.new(SALT.encode(), ip.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(view.ip_hash, expected)
        self.assertRegex(view.ip_hash, r'^[0-9a-f]{64}$')
        for field in ContactView._meta.concrete_fields:
            self.assertNotIn(ip, str(getattr(view, field.attname)))
        with override_settings(PHONE_LOG_IP_SALT='other-salt'):
            self.assertNotEqual(ip_hash(ip), expected)
        self.assertNotEqual(ip_hash('203.0.113.78'), expected)

    def test_cache_key_has_no_ip(self):
        ip = '203.0.113.55'
        request = mock.Mock(META={'REMOTE_ADDR': ip}, user=mock.Mock(is_authenticated=False))
        key = GuestContactThrottle().get_cache_key(request, None)
        self.assertNotIn(ip, key)
        self.assertIn(ip_hash(ip), key)

    def test_guest_log_has_no_dedup(self):
        with _turnstile(True):
            self.guest_post()
            self.guest_post()
        self.assertEqual(ContactView.objects.filter(is_guest=True).count(), 2)

    def test_authenticated_post_needs_no_captcha_and_has_no_ip_hash(self):
        buyer = make_user()
        resp = auth_client(buyer).post(self.url(), {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        view = ContactView.objects.get()
        self.assertEqual(view.user_id, buyer.pk)
        self.assertEqual(view.ip_hash, '')
        self.assertFalse(view.is_guest)

    @override_settings(C2C_ENABLED=False)
    def test_c2c_disabled_is_404(self):
        with _turnstile(True):
            self.assertEqual(self.guest_post().status_code, status.HTTP_404_NOT_FOUND)


class TestAuthenticatedPhone(ContactBase):

    def test_view_logged_and_deduplicated_within_hour(self):
        buyer = make_user()
        client = auth_client(buyer)
        for _ in range(2):
            self.assertEqual(client.get(self.url()).status_code, status.HTTP_200_OK)
        self.assertEqual(ContactView.objects.filter(user=buyer, listing=self.listing).count(), 1)
        ContactView.objects.update(created_at=timezone.now() - timedelta(hours=2))
        client.get(self.url())
        self.assertEqual(ContactView.objects.filter(user=buyer, listing=self.listing).count(), 2)

    def test_log_has_no_phone_field(self):
        names = {f.name for f in ContactView._meta.get_fields()}
        self.assertFalse({n for n in names if 'phone' in n or 'agent' in n or n == 'ip'})

    def test_non_active_404_without_log(self):
        LocalListing.objects.filter(pk=self.listing.pk).update(status=LocalListing.Status.PENDING)
        self.assertEqual(auth_client(make_user()).get(self.url()).status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(ContactView.objects.exists())

    @_rates(contact='2/hour')
    def test_hourly_limit(self):
        client = auth_client(make_user())
        listings = [make_local_listing(self.owner) for _ in range(3)]
        for listing in listings[:2]:
            self.assertEqual(client.get(self.url(listing)).status_code, status.HTTP_200_OK)
        self.assertEqual(client.get(self.url(listings[2])).status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @_rates(contact='100/hour', contact_daily='3/day')
    def test_daily_limit_with_text(self):
        client = auth_client(make_user())
        listings = [make_local_listing(self.owner) for _ in range(4)]
        for listing in listings[:3]:
            self.assertEqual(client.get(self.url(listing)).status_code, status.HTTP_200_OK)
        resp = client.get(self.url(listings[3]))
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(resp.json()['detail'], 'Ліміт переглядів телефонів на сьогодні вичерпано')


@override_settings(PHONE_LOG_IP_SALT=SALT, CONTACT_VIEW_ALERT_THRESHOLD=3, **TURNSTILE)
class TestContactAnomaly(ContactBase):

    def setUp(self):
        super().setUp()
        self.moderator = make_moderator()
        self.staff = make_staff()
        self.listings = [self.listing] + [make_local_listing(self.owner, contact_phone=PHONE) for _ in range(3)]

    def anomalies(self, user):
        return Notification.objects.filter(user=user, type='contact_anomaly')

    def test_user_threshold_one_notification_per_day_without_phones(self):
        buyer = make_user('collector@example.com')
        client = auth_client(buyer)
        with mock.patch('integrations.tasks.send_notification.delay') as telegram,                 self.captureOnCommitCallbacks(execute=True):
            for listing in self.listings:
                self.assertEqual(client.get(self.url(listing)).status_code, status.HTTP_200_OK)
        telegram.assert_not_called()  # только in-app, без Telegram
        note = self.anomalies(self.moderator).get()
        self.assertIn(f'#{buyer.pk}', note.text)
        self.assertIn('co…@example.com', note.text)
        self.assertNotIn('collector@', note.text)
        self.assertNotIn(PHONE, note.title + note.text)
        self.assertIn(f'user__id__exact={buyer.pk}', note.link)
        self.assertFalse(self.anomalies(self.staff).exists())  # staff без права модерации

    def test_below_threshold_no_notification(self):
        client = auth_client(make_user())
        for listing in self.listings[:2]:
            client.get(self.url(listing))
        self.assertFalse(Notification.objects.filter(type='contact_anomaly').exists())

    def test_guest_anomaly_by_ip_hash_without_ip(self):
        ip = '198.51.100.23'
        with _turnstile(True):
            for listing in self.listings[:3]:
                self.assertEqual(self.guest_post(listing, ip=ip).status_code, status.HTTP_200_OK)
        note = self.anomalies(self.moderator).get()
        self.assertIn(ip_hash(ip)[:8], note.text)
        self.assertNotIn(ip_hash(ip), note.text)
        self.assertNotIn(ip, note.title + note.text + note.link)
        self.assertNotIn(PHONE, note.text)


class TestCleanup(APITestCase):

    @override_settings(CONTACT_VIEW_RETENTION_DAYS=90)
    def test_old_records_removed_fresh_kept(self):
        listing = make_local_listing(make_user())
        old = ContactView.objects.create(listing=listing, is_guest=True, ip_hash='a' * 64,
                                         created_at=timezone.now() - timedelta(days=91))
        fresh = ContactView.objects.create(listing=listing, is_guest=True, ip_hash='b' * 64,
                                           created_at=timezone.now() - timedelta(days=89))
        self.assertEqual(cleanup_contact_views()['deleted'], 1)
        self.assertFalse(ContactView.objects.filter(pk=old.pk).exists())
        self.assertTrue(ContactView.objects.filter(pk=fresh.pk).exists())

    def test_beat_schedule_has_cleanup(self):
        tasks = {v['task'] for v in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn('local_listings.tasks.cleanup_contact_views', tasks)


class TestContactViewAdmin(APITestCase):
    URL = '/admin/local_listings/contactview/'

    def setUp(self):
        listing = make_local_listing(make_user())
        self.view = ContactView.objects.create(listing=listing, user=make_user())

    def _client(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_staff_without_perm_is_403(self):
        self.assertEqual(self._client(make_staff()).get(self.URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_sees_list_and_filter_link(self):
        client = self._client(make_moderator())
        self.assertEqual(client.get(self.URL).status_code, status.HTTP_200_OK)
        resp = client.get(f'{self.URL}?user__id__exact={self.view.user_id}')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertContains(resp, 'Переглядів за добу')

    def test_superuser_sees_list(self):
        self.assertEqual(self._client(make_staff(superuser=True)).get(self.URL).status_code, status.HTTP_200_OK)

    def test_add_change_delete_forbidden(self):
        client = self._client(make_moderator())
        self.assertEqual(client.get(f'{self.URL}add/').status_code, status.HTTP_403_FORBIDDEN)
        change = client.post(f'{self.URL}{self.view.pk}/change/', {})
        self.assertEqual(change.status_code, status.HTTP_403_FORBIDDEN)
        delete = client.post(f'{self.URL}{self.view.pk}/delete/', {'post': 'yes'})
        self.assertEqual(delete.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ContactView.objects.filter(pk=self.view.pk).exists())


class TestLaunchCheckSalt(APITestCase):

    @override_settings(PHONE_LOG_IP_SALT='', C2C_ENABLED=True)
    def test_empty_salt_with_c2c_is_warning_in_wave1(self):
        self.assertEqual(check_phone_log_salt()[0].level, WARNING)

    @override_settings(PHONE_LOG_IP_SALT='', C2C_ENABLED=False)
    def test_empty_salt_without_c2c_is_info(self):
        self.assertEqual(check_phone_log_salt()[0].level, INFO)

    def test_salt_equal_secret_key_is_error(self):
        with override_settings(PHONE_LOG_IP_SALT=settings.SECRET_KEY):
            self.assertEqual(check_phone_log_salt()[0].level, ERROR)

    @override_settings(PHONE_LOG_IP_SALT=SALT)
    def test_salt_set_is_ok(self):
        self.assertEqual(check_phone_log_salt()[0].level, OK)

    def test_env_example_salt_is_not_secret_key(self):
        text = (settings.BASE_DIR / '.env.example').read_text(encoding='utf-8')
        values = dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line.startswith('#'))
        self.assertEqual(values.get('PHONE_LOG_IP_SALT', '').strip(), '')
        self.assertNotEqual(values.get('PHONE_LOG_IP_SALT'), values.get('SECRET_KEY'))
