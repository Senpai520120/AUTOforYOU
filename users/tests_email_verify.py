"""Подтверждение email и ограничения до него (задача 1.6)."""
import re
from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient

from local_listings.models import LocalListing
from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_local_listing, make_region_city, make_user

from .emails import build_verification_url, send_verification_email
from .tokens import email_verification_token

User = get_user_model()

REGISTER_URL = '/api/v1/auth/register/'
VERIFY_URL = '/api/v1/auth/verify-email/'
RESEND_URL = '/api/v1/auth/verify-email/resend/'
CONFIG_URL = '/api/v1/auth/config/'
PROFILE_URL = '/api/v1/auth/profile/'

REG = {
    'email': 'newbie@test.com',
    'password': 'StrongPass123!',
    'password2': 'StrongPass123!',
    'agreed_to_terms': True,
    'confirmed_age_18': True,
}


def _uid_token(user):
    return urlsafe_base64_encode(force_bytes(user.pk)), email_verification_token.make_token(user)


def _link_params(body):
    match = re.search(r'/verify-email\?uid=([^&\s]+)&token=([^\s]+)', body)
    return {'uid': match.group(1), 'token': match.group(2)}


@override_settings(SITE_URL='https://site.test')
class TestRegisterSendsVerification(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_register_sends_one_email_with_link_that_verifies(self):
        resp = self.client.post(REGISTER_URL, REG, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [REG['email']])
        self.assertIn('https://site.test/verify-email?uid=', message.body)
        user = User.objects.get(email=REG['email'])
        self.assertFalse(user.is_email_verified)

        resp = self.client.post(VERIFY_URL, _link_params(message.body), format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

    def test_repeated_link_returns_400(self):
        self.client.post(REGISTER_URL, REG, format='json')
        params = _link_params(mail.outbox[0].body)
        self.assertEqual(self.client.post(VERIFY_URL, params, format='json').status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(VERIFY_URL, params, format='json').status_code, status.HTTP_400_BAD_REQUEST)

    def test_other_users_uid_returns_400(self):
        self.client.post(REGISTER_URL, REG, format='json')
        params = _link_params(mail.outbox[0].body)
        other = make_user('other@test.com', verified=False)
        params['uid'] = urlsafe_base64_encode(force_bytes(other.pk))
        resp = self.client.post(VERIFY_URL, params, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        other.refresh_from_db()
        self.assertFalse(other.is_email_verified)

    def test_expired_token_returns_400(self):
        user = make_user('late@test.com', verified=False)
        uid, token = _uid_token(user)
        later = datetime.now() + timedelta(hours=49)
        with mock.patch.object(type(email_verification_token), '_now', return_value=later):
            resp = self.client.post(VERIFY_URL, {'uid': uid, 'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_token_within_ttl_is_valid(self):
        user = make_user('early@test.com', verified=False)
        uid, token = _uid_token(user)
        soon = datetime.now() + timedelta(hours=47)
        with mock.patch.object(type(email_verification_token), '_now', return_value=soon):
            resp = self.client.post(VERIFY_URL, {'uid': uid, 'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_email_change_invalidates_link(self):
        user = make_user('before@test.com', verified=False)
        uid, token = _uid_token(user)
        user.email = 'after@test.com'
        user.save(update_fields=['email'])
        resp = self.client.post(VERIFY_URL, {'uid': uid, 'token': token}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_garbage_payload_returns_400(self):
        resp = self.client.post(VERIFY_URL, {'uid': '!!', 'token': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post(VERIFY_URL, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(SITE_URL='')
    def test_empty_site_url_skips_email_but_registers(self):
        with self.assertLogs('users.emails', level='WARNING'):
            resp = self.client.post(REGISTER_URL, REG, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(User.objects.filter(email=REG['email']).exists())

    def test_smtp_failure_does_not_break_registration(self):
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError('smtp down')):
            with self.assertLogs('integrations.email', level='WARNING'):
                resp = self.client.post(REGISTER_URL, REG, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class TestRegisterValidation(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_weak_password_returns_400(self):
        data = {**REG, 'password': '123', 'password2': '123'}
        self.assertEqual(self.client.post(REGISTER_URL, data, format='json').status_code, 400)

    def test_password_mismatch_returns_400(self):
        data = {**REG, 'password2': 'OtherPass123!'}
        self.assertEqual(self.client.post(REGISTER_URL, data, format='json').status_code, 400)

    def test_without_adult_confirmation_returns_400(self):
        data = {**REG, 'confirmed_age_18': False}
        resp = self.client.post(REGISTER_URL, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirmed_age_18', resp.data)
        self.assertFalse(User.objects.filter(email=REG['email']).exists())

    def test_adult_field_missing_returns_400(self):
        data = {k: v for k, v in REG.items() if k != 'confirmed_age_18'}
        self.assertEqual(self.client.post(REGISTER_URL, data, format='json').status_code, 400)

    @override_settings(SITE_URL='https://site.test')
    def test_duplicate_email_same_response_and_already_registered_mail(self):
        first = self.client.post(REGISTER_URL, REG, format='json')
        mail.outbox.clear()
        second = self.client.post(REGISTER_URL, {**REG, 'email': REG['email'].upper()}, format='json')
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            {k: v for k, v in second.json().items() if k != 'email'},
            {k: v for k, v in first.json().items() if k != 'email'},
        )
        self.assertEqual(User.objects.filter(email__iexact=REG['email']).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('вже', mail.outbox[0].subject)
        self.assertNotIn('verify-email', mail.outbox[0].body)

    def test_duplicate_email_hashes_password_to_equalize_timing(self):
        self.client.post(REGISTER_URL, REG, format='json')
        with mock.patch('users.views.make_password') as hasher:
            resp = self.client.post(REGISTER_URL, REG, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        hasher.assert_called_once_with(REG['password'])

    def test_race_integrity_error_returns_same_201(self):
        with mock.patch('users.serializers.RegisterSerializer.save', side_effect=IntegrityError):
            resp = self.client.post(REGISTER_URL, REG, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.json()['email'], REG['email'])

    def test_register_response_has_no_id(self):
        resp = self.client.post(REGISTER_URL, REG, format='json')
        self.assertEqual(set(resp.json()), {'email', 'first_name', 'last_name', 'phone'})


class TestUnverifiedRestricted(CleanCacheTestCase):
    START_URL = '/api/v1/messages/start/'
    LOCAL_URL = '/api/v1/local/listings/'
    APPLY_URL = '/api/v1/dealers/apply/'

    def setUp(self):
        super().setUp()
        self.user = make_user('unverified@test.com', verified=False)
        self.client = auth_client(self.user)
        self.region, self.city = make_region_city()
        seller = make_user('seller@test.com')
        self.listing = make_local_listing(seller, region=self.region, city=self.city)

    def _listing_payload(self):
        return {
            'make': 'Toyota', 'model': 'Camry', 'year': 2020, 'mileage_km': 50000, 'engine_cc': 2500,
            'fuel_type': 'petrol', 'transmission': 'auto', 'body_type': 'sedan', 'condition': 'used',
            'price': '500000', 'currency': 'UAH', 'price_type': 'fixed',
            'region': self.region.pk, 'city': self.city.pk, 'description': 'Тест',
            'contact_phone': '+380501234567', 'agreed_to_rules': True,
        }

    def _start(self):
        return self.client.post(
            self.START_URL, {'listing_type': 'local', 'listing_id': self.listing.pk, 'text': 'Hi'}, format='json',
        )

    def _apply(self):
        return self.client.post(self.APPLY_URL, {
            'company_name': 'ТОВ Авто', 'full_name': 'Іван Іванов', 'contact_phone': '+380991234567',
            'documents': 'https://drive.google.com/doc', 'agreed_to_processing': True, 'confirmed_age_18': True,
        }, format='json')

    def _assert_blocked(self, resp):
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.json()['code'], 'email_not_verified')

    def test_local_create_blocked(self):
        self._assert_blocked(self.client.post(self.LOCAL_URL, self._listing_payload(), format='json'))
        self.assertFalse(LocalListing.objects.filter(owner=self.user).exists())

    def test_start_conversation_blocked(self):
        self._assert_blocked(self._start())

    def test_send_message_blocked(self):
        from messaging.services import get_or_create_conversation
        buyer = make_user('buyer2@test.com')
        conv, _, _ = get_or_create_conversation(buyer, 'local', self.listing.pk, 'Привіт')
        buyer.is_email_verified = False
        buyer.save(update_fields=['is_email_verified'])
        resp = auth_client(buyer).post(f'/api/v1/messages/conversations/{conv.pk}/', {'text': 'ще'}, format='json')
        self._assert_blocked(resp)

    def test_dealer_apply_blocked(self):
        self._assert_blocked(self._apply())

    def test_profile_and_reading_allowed(self):
        self.assertEqual(self.client.get(PROFILE_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/v1/messages/conversations/').status_code, status.HTTP_200_OK)

    def test_verified_user_passes(self):
        self.user.is_email_verified = True
        self.user.save(update_fields=['is_email_verified'])
        self.assertEqual(
            self.client.post(self.LOCAL_URL, self._listing_payload(), format='json').status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(self._start().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._apply().status_code, status.HTTP_201_CREATED)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_flag_off_allows_unverified(self):
        self.assertEqual(
            self.client.post(self.LOCAL_URL, self._listing_payload(), format='json').status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(self._start().status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._apply().status_code, status.HTTP_201_CREATED)

    def test_anonymous_gets_401_not_email_error(self):
        resp = APIClient().post(self.START_URL, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_profile_exposes_is_email_verified_read_only(self):
        resp = self.client.get(PROFILE_URL)
        self.assertIs(resp.json()['is_email_verified'], False)
        resp = self.client.patch(PROFILE_URL, {'is_email_verified': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)


@override_settings(SITE_URL='https://site.test')
class TestResendVerification(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.user = make_user('resend@test.com', verified=False)
        self.client = auth_client(self.user)

    def test_anonymous_gets_401(self):
        self.assertEqual(APIClient().post(RESEND_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_resend_sends_email(self):
        self.assertEqual(self.client.post(RESEND_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_verified_user_gets_no_email(self):
        self.user.is_email_verified = True
        self.user.save(update_fields=['is_email_verified'])
        self.assertEqual(self.client.post(RESEND_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_throttled(self):
        codes = [self.client.post(RESEND_URL).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])


class TestAuthConfig(CleanCacheTestCase):

    @override_settings(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SITE_KEY='site-pub', TURNSTILE_SECRET_KEY='SECRET-xyz')
    def test_auth_config_has_no_secret(self):
        resp = APIClient().get(CONFIG_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('SECRET-xyz', resp.content.decode())
        self.assertNotIn('TURNSTILE_SECRET_KEY', resp.content.decode())
        captcha = resp.json()['captcha']
        self.assertEqual(captcha['provider'], 'turnstile')
        self.assertEqual(captcha['site_key'], 'site-pub')
        self.assertEqual(captcha['login_after_failures'], 3)
        self.assertIs(captcha['on_login'], False)
        self.assertIs(resp.json()['email_verification_required'], True)

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_honeypot_config_issues_form_token(self):
        captcha = APIClient().get(CONFIG_URL).json()['captcha']
        self.assertEqual(captcha['provider'], 'honeypot')
        self.assertTrue(captcha['form_token'])

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_config_reflects_verification_flag(self):
        self.assertIs(APIClient().get(CONFIG_URL).json()['email_verification_required'], False)


class TestGrandfatherMigration(CleanCacheTestCase):

    def test_grandfather_marks_existing_users_verified(self):
        from importlib import import_module

        from django.apps import apps as django_apps
        migration = import_module('users.migrations.0012_grandfather_email_verified')
        old = make_user('old@test.com', verified=False)
        migration.grandfather(django_apps, None)
        old.refresh_from_db()
        self.assertTrue(old.is_email_verified)


class TestBuildUrl(CleanCacheTestCase):

    @override_settings(SITE_URL='https://site.test/')
    def test_url_has_no_double_slash(self):
        user = make_user('url@test.com', verified=False)
        self.assertTrue(build_verification_url(user).startswith('https://site.test/verify-email?uid='))

    @override_settings(SITE_URL='https://site.test')
    def test_send_uses_default_from_email(self):
        user = make_user('from@test.com', verified=False)
        with override_settings(DEFAULT_FROM_EMAIL='from@site.test'):
            send_verification_email(user)
        self.assertEqual(mail.outbox[0].from_email, 'from@site.test')


class TestCaptchaProviderSystemCheck(CleanCacheTestCase):

    def _errors(self):
        from users.apps import check_captcha_provider
        return check_captcha_provider(None)

    @override_settings(CAPTCHA_PROVIDER='off', DEBUG=False, IS_TESTING=False)
    def test_off_without_debug_is_error(self):
        self.assertEqual([e.id for e in self._errors()], ['users.E001'])

    @override_settings(CAPTCHA_PROVIDER='off', DEBUG=True, IS_TESTING=False)
    def test_off_in_debug_is_ok(self):
        self.assertEqual(self._errors(), [])

    @override_settings(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='0x4AAAreal', DEBUG=False, IS_TESTING=False)
    def test_turnstile_is_ok(self):
        self.assertEqual(self._errors(), [])
