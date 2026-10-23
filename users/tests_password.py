"""Сброс и смена пароля, отзыв всех сессий (задача 1.7)."""
import re
from datetime import timedelta
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import RequestFactory, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from tests.base import CleanCacheTestCase
from tests.factories import TEST_PASSWORD, make_staff, make_user

from .admin import CustomUserAdmin
from .jwt import VersionedRefreshToken
from .tasks import flush_expired_tokens

User = get_user_model()

RESET_URL = '/api/v1/auth/password-reset/'
CONFIRM_URL = '/api/v1/auth/password-reset/confirm/'
CHANGE_URL = '/api/v1/auth/password-change/'
LOGOUT_ALL_URL = '/api/v1/auth/token/logout-all/'
REFRESH_URL = '/api/v1/auth/token/refresh/'
PROFILE_URL = '/api/v1/auth/profile/'
TOKEN_URL = '/api/v1/auth/token/'
NEW_PASSWORD = 'Brand-new-Pass-7391'


def _bearer(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return client


def _session(user):
    """(refresh, access) пользователя с текущей версией сессий."""
    refresh = VersionedRefreshToken.for_user(user)
    return str(refresh), str(refresh.access_token)


def _uid_token(user):
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)


def _link_params(body):
    match = re.search(r'/password-reset/confirm\?uid=([^&\s]+)&token=([^\s]+)', body)
    return {'uid': match.group(1), 'token': match.group(2)}


class PasswordTestCase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'password_reset': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = APIClient()


@override_settings(SITE_URL='https://site.test', CAPTCHA_PROVIDER='off')
class TestPasswordResetRequest(PasswordTestCase):

    def test_existing_email_gets_one_letter_with_site_link(self):
        user = make_user('owner@test.com')
        resp = self.client.post(RESET_URL, {'email': 'owner@test.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertIn('https://site.test/password-reset/confirm?uid=', mail.outbox[0].body)

    def test_unknown_email_same_body_and_no_letter(self):
        make_user('owner@test.com')
        known = self.client.post(RESET_URL, {'email': 'owner@test.com'}, format='json')
        mail.outbox.clear()
        unknown = self.client.post(RESET_URL, {'email': 'ghost@test.com'}, format='json')
        self.assertEqual(unknown.status_code, status.HTTP_200_OK)
        self.assertEqual(unknown.json(), known.json())
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_and_banned_get_no_letter_but_same_200(self):
        make_user('inactive@test.com', is_active=False)
        make_user('banned@test.com', is_active=False, is_banned=True)
        for email in ('inactive@test.com', 'banned@test.com'):
            resp = self.client.post(RESET_URL, {'email': email}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_lookup_is_case_insensitive(self):
        make_user('owner@test.com')
        self.client.post(RESET_URL, {'email': 'Owner@Test.com'}, format='json')
        self.assertEqual(len(mail.outbox), 1)

    def test_task_is_queued_for_any_email_without_db_lookup_in_request(self):
        make_user('owner@test.com')
        for email in ('owner@test.com', 'ghost@test.com'):
            with mock.patch('users.views.send_password_reset_email_task.delay') as delay:
                with self.assertNumQueries(0):
                    resp = self.client.post(RESET_URL, {'email': email}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            delay.assert_called_once_with(email)

    def test_broker_down_does_not_leak_or_fail(self):
        make_user('owner@test.com')
        with mock.patch('users.views.send_password_reset_email_task.delay', side_effect=OSError('redis down')):
            resp = self.client.post(RESET_URL, {'email': 'owner@test.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_invalid_email_format_is_400(self):
        resp = self.client.post(RESET_URL, {'email': 'not-an-email'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_letter_template_is_ukrainian_and_has_no_hardcoded_domain(self):
        make_user('owner@test.com')
        self.client.post(RESET_URL, {'email': 'owner@test.com'}, format='json')
        body = mail.outbox[0].body
        self.assertIn('скидання пароля', body)
        self.assertNotIn('autoforyou.ua', body)


@override_settings(SITE_URL='https://site.test', CAPTCHA_PROVIDER='off')
class TestPasswordResetConfirm(PasswordTestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user('owner@test.com')

    def _confirm(self, uid, token, password=NEW_PASSWORD, password2=None):
        return self.client.post(CONFIRM_URL, {
            'uid': uid, 'token': token, 'new_password': password,
            'new_password2': password if password2 is None else password2,
        }, format='json')

    def test_valid_link_changes_password_and_login_works(self):
        resp = self._confirm(*_uid_token(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        login = self.client.post(TOKEN_URL, {'email': 'owner@test.com', 'password': NEW_PASSWORD}, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        old = self.client.post(TOKEN_URL, {'email': 'owner@test.com', 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(old.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_link_from_letter_works_end_to_end(self):
        self.client.post(RESET_URL, {'email': 'owner@test.com'}, format='json')
        params = _link_params(mail.outbox[0].body)
        resp = self.client.post(CONFIRM_URL, {**params, 'new_password': NEW_PASSWORD,
                                              'new_password2': NEW_PASSWORD}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_link_is_single_use(self):
        uid, token = _uid_token(self.user)
        self.assertEqual(self._confirm(uid, token).status_code, status.HTTP_200_OK)
        again = self._confirm(uid, token, password='Another-Pass-5521')
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_expired_token_is_400(self):
        uid, token = _uid_token(self.user)
        real_now = default_token_generator._now
        with mock.patch.object(default_token_generator, '_now',
                               lambda: real_now() + timedelta(seconds=61)):
            resp = self._confirm(uid, token)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(TEST_PASSWORD))

    @override_settings(PASSWORD_RESET_TIMEOUT=60)
    def test_token_just_before_expiry_still_works(self):
        uid, token = _uid_token(self.user)
        real_now = default_token_generator._now
        with mock.patch.object(default_token_generator, '_now',
                               lambda: real_now() + timedelta(seconds=30)):
            self.assertEqual(self._confirm(uid, token).status_code, status.HTTP_200_OK)

    def test_tampered_token_and_foreign_uid_neutral_400(self):
        uid, token = _uid_token(self.user)
        other = make_user('other@test.com')
        other_uid, _ = _uid_token(other)
        for u, t in ((uid, token + 'x'), (other_uid, token), ('!!!', token), (uid, '')):
            resp = self._confirm(u, t)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, (u, t))
            self.assertNotIn('new_password', resp.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(TEST_PASSWORD))

    def test_weak_password_is_400_and_token_stays_usable(self):
        uid, token = _uid_token(self.user)
        resp = self._confirm(uid, token, password='12345678')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', resp.json())
        self.assertEqual(self._confirm(uid, token).status_code, status.HTTP_200_OK)

    def test_mismatched_passwords_is_400(self):
        uid, token = _uid_token(self.user)
        resp = self._confirm(uid, token, password2='Different-Pass-1111')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password2', resp.json())

    def test_inactive_user_link_is_400(self):
        uid, token = _uid_token(self.user)
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertEqual(self._confirm(uid, token).status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_revokes_all_sessions(self):
        refresh, access = _session(self.user)
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_200_OK)
        self._confirm(*_uid_token(self.user))
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post(REFRESH_URL, {'refresh': refresh}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_confirm_needs_no_captcha(self):
        with override_settings(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='sk'), \
                mock.patch('httpx.post') as post:
            resp = self._confirm(*_uid_token(self.user))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        post.assert_not_called()

    def test_confirm_clears_login_lockout(self):
        from . import lockout
        for _ in range(10):
            lockout.reserve_attempt('owner@test.com', '127.0.0.1')
        self._confirm(*_uid_token(self.user))
        self.assertIsNone(lockout.is_locked('owner@test.com'))


@override_settings(CAPTCHA_PROVIDER='off')
class TestPasswordChange(PasswordTestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user('owner@test.com')
        self.data = {'old_password': TEST_PASSWORD, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD}

    def test_without_credentials_is_401(self):
        self.assertEqual(self.client.post(CHANGE_URL, self.data, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_wrong_old_password_is_400_and_nothing_changes(self):
        _, access = _session(self.user)
        resp = _bearer(access).post(CHANGE_URL, {**self.data, 'old_password': 'wrong-old-pass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('old_password', resp.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(TEST_PASSWORD))
        self.assertEqual(self.user.session_version, 0)

    def test_weak_mismatch_and_same_password_are_400(self):
        _, access = _session(self.user)
        client = _bearer(access)
        for patch in ({'new_password': '12345678', 'new_password2': '12345678'},
                      {'new_password2': 'Different-Pass-1111'},
                      {'new_password': TEST_PASSWORD, 'new_password2': TEST_PASSWORD}):
            resp = client.post(CHANGE_URL, {**self.data, **patch}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, patch)

    def test_success_revokes_old_sessions_and_issues_new_cookies(self):
        refresh, access = _session(self.user)
        other_refresh, other_access = _session(self.user)
        resp = _bearer(access).post(CHANGE_URL, self.data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        # старые refresh в blacklist, старые access отклоняются сразу
        for old in (refresh, other_refresh):
            self.assertEqual(self.client.post(REFRESH_URL, {'refresh': old}, format='json').status_code,
                             status.HTTP_401_UNAUTHORIZED)
        for old in (access, other_access):
            self.assertEqual(_bearer(old).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        # текущему устройству выдана новая пара
        new_access = resp.cookies['access'].value
        self.assertEqual(_bearer(new_access).get(PROFILE_URL).status_code, status.HTTP_200_OK)
        new_refresh = resp.cookies['refresh'].value
        self.assertEqual(self.client.post(REFRESH_URL, {'refresh': new_refresh}, format='json').status_code,
                         status.HTTP_200_OK)

    def test_other_users_sessions_untouched(self):
        other = make_user('other@test.com')
        _, other_access = _session(other)
        _, access = _session(self.user)
        _bearer(access).post(CHANGE_URL, self.data, format='json')
        self.assertEqual(_bearer(other_access).get(PROFILE_URL).status_code, status.HTTP_200_OK)


@override_settings(CAPTCHA_PROVIDER='off')
class TestLogoutAll(PasswordTestCase):

    def test_anonymous_is_401(self):
        self.assertEqual(self.client.post(LOGOUT_ALL_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_revokes_all_own_sessions_and_clears_cookies(self):
        user = make_user('owner@test.com')
        other = make_user('other@test.com')
        refresh1, access1 = _session(user)
        refresh2, access2 = _session(user)
        other_refresh, other_access = _session(other)
        resp = _bearer(access1).post(LOGOUT_ALL_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for name in ('access', 'refresh'):
            self.assertEqual(resp.cookies[name].value, '')
            self.assertEqual(resp.cookies[name]['max-age'], 0)
        for old in (refresh1, refresh2):
            self.assertEqual(self.client.post(REFRESH_URL, {'refresh': old}, format='json').status_code,
                             status.HTTP_401_UNAUTHORIZED)
        for old in (access1, access2):
            self.assertEqual(_bearer(old).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        # чужая сессия цела
        self.assertEqual(_bearer(other_access).get(PROFILE_URL).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(REFRESH_URL, {'refresh': other_refresh}, format='json').status_code,
                         status.HTTP_200_OK)

    def test_can_login_again_after_logout_all(self):
        user = make_user('owner@test.com')
        _, access = _session(user)
        _bearer(access).post(LOGOUT_ALL_URL)
        login = self.client.post(TOKEN_URL, {'email': 'owner@test.com', 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertEqual(_bearer(login.cookies['access'].value).get(PROFILE_URL).status_code, status.HTTP_200_OK)


class TestRevokeService(PasswordTestCase):

    def test_blacklists_every_outstanding_token_and_sets_mark(self):
        from .services import revoke_all_sessions
        user = make_user('owner@test.com')
        other = make_user('other@test.com')
        RefreshToken.for_user(user)
        RefreshToken.for_user(user)
        RefreshToken.for_user(other)
        revoke_all_sessions(user)
        revoke_all_sessions(user)  # идемпотентно
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 2)
        self.assertEqual(BlacklistedToken.objects.filter(token__user=other).count(), 0)
        user.refresh_from_db()
        self.assertEqual(user.session_version, 2)

    def test_works_for_inactive_user_with_unusable_password(self):
        from .services import revoke_all_sessions
        user = make_user('gone@test.com')
        RefreshToken.for_user(user)
        user.is_active = False
        user.set_unusable_password()
        user.save()
        revoke_all_sessions(user)
        self.assertEqual(BlacklistedToken.objects.filter(token__user=user).count(), 1)

    def test_legacy_token_without_sv_is_version_zero(self):
        from .services import revoke_all_sessions
        user = make_user('owner@test.com')
        legacy = str(RefreshToken.for_user(user).access_token)  # выдан до 1.7: без claim sv
        self.assertEqual(_bearer(legacy).get(PROFILE_URL).status_code, status.HTTP_200_OK)
        revoke_all_sessions(user)
        self.assertEqual(_bearer(legacy).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_without_sv_is_rejected_after_revoke(self):
        from .services import revoke_all_sessions
        user = make_user('owner@test.com')
        access = VersionedRefreshToken.for_user(user).access_token
        del access.payload['sv']
        revoke_all_sessions(user)
        self.assertEqual(_bearer(str(access)).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_issued_after_revoke_is_valid(self):
        from .services import revoke_all_sessions
        user = make_user('owner@test.com')
        revoke_all_sessions(user)
        access = str(VersionedRefreshToken.for_user(user).access_token)
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_200_OK)


class TestBanAdminAction(PasswordTestCase):

    def _run(self, action, users):
        request = RequestFactory().post('/admin/users/customuser/')
        request.user = make_staff(superuser=True)
        request._messages = mock.Mock()
        model_admin = CustomUserAdmin(User, admin_site)
        action(model_admin, request, User.objects.filter(pk__in=[u.pk for u in users]))

    def test_ban_revokes_refresh_and_access(self):
        from .admin import ban_users
        victim = make_user('victim@test.com')
        refresh, access = _session(victim)
        self._run(ban_users, [victim])
        victim.refresh_from_db()
        self.assertTrue(victim.is_banned)
        self.assertFalse(victim.is_active)
        self.assertEqual(self.client.post(REFRESH_URL, {'refresh': refresh}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_ban_skips_superuser_and_unban_restores_only_banned(self):
        from .admin import ban_users, unban_users
        boss = make_staff('boss@test.com', superuser=True)
        inactive = make_user('inactive@test.com', is_active=False)  # не забанен сервисом
        victim = make_user('victim@test.com')
        self._run(ban_users, [boss, victim])
        boss.refresh_from_db()
        self.assertFalse(boss.is_banned)
        self._run(unban_users, [inactive, victim])
        inactive.refresh_from_db()
        victim.refresh_from_db()
        self.assertFalse(inactive.is_active)  # разбан не включает «чужих» неактивных
        self.assertFalse(victim.is_banned)
        self.assertTrue(victim.is_active)


@override_settings(SITE_URL='https://site.test', CAPTCHA_PROVIDER='off')
class TestPasswordResetThrottle(CleanCacheTestCase):

    def test_third_request_is_429(self):
        make_user('owner@test.com')
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'password_reset': '2/min'}):
            client = APIClient()
            statuses = [client.post(RESET_URL, {'email': 'owner@test.com'}, format='json').status_code
                        for _ in range(3)]
        self.assertEqual(statuses, [200, 200, 429])

    def test_confirm_shares_the_scope(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'password_reset': '2/min'}):
            client = APIClient()
            payload = {'uid': 'x', 'token': 'y', 'new_password': 'a', 'new_password2': 'a'}
            statuses = [client.post(CONFIRM_URL, payload, format='json').status_code for _ in range(3)]
        self.assertEqual(statuses, [400, 400, 429])


@override_settings(SITE_URL='https://site.test')
class TestPasswordResetCaptcha(PasswordTestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user('owner@test.com')

    @override_settings(CAPTCHA_PROVIDER='honeypot')
    def test_filled_honeypot_is_captcha_failed_and_no_letter(self):
        resp = self.client.post(RESET_URL, {'email': 'owner@test.com', 'website': 'http://spam'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()['code'], 'captcha_failed')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='sk', TURNSTILE_SITE_KEY='pk')
    def test_turnstile_failure_same_400_for_existing_and_unknown_without_db(self):
        response = mock.Mock()
        response.json.return_value = {'success': False}
        bodies = []
        with mock.patch('httpx.post', return_value=response):
            for email in ('owner@test.com', 'ghost@test.com'):
                with self.assertNumQueries(0):
                    resp = self.client.post(RESET_URL, {'email': email, 'captcha_token': 't'}, format='json')
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                bodies.append(resp.json())
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(bodies[0]['code'], 'captcha_failed')
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='sk', TURNSTILE_SITE_KEY='pk')
    def test_turnstile_success_sends_letter(self):
        response = mock.Mock()
        response.json.return_value = {'success': True}
        with mock.patch('httpx.post', return_value=response):
            resp = self.client.post(RESET_URL, {'email': 'owner@test.com', 'captcha_token': 't'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)


class TestFlushTask(CleanCacheTestCase):

    def test_task_calls_both_commands(self):
        with mock.patch('users.tasks.call_command') as call:
            flush_expired_tokens()
        self.assertEqual([c.args[0] for c in call.call_args_list], ['flushexpiredtokens', 'clearsessions'])

    def test_task_is_in_beat_schedule(self):
        from django.conf import settings
        tasks = [entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()]
        self.assertIn('users.tasks.flush_expired_tokens', tasks)

    def test_flushexpiredtokens_removes_expired_outstanding(self):
        user = make_user('owner@test.com')
        RefreshToken.for_user(user)
        OutstandingToken.objects.update(expires_at=timezone.now() - timedelta(days=1))
        from django.core.management import call_command
        call_command('flushexpiredtokens')
        self.assertEqual(OutstandingToken.objects.count(), 0)


class TestSessionVersion(PasswordTestCase):

    def test_refresh_with_pre_revoke_version_is_401_without_blacklist(self):
        user = make_user('owner@test.com')
        refresh, _ = _session(user)
        User.objects.filter(pk=user.pk).update(session_version=1)  # версия выросла, blacklist пуст
        self.assertFalse(BlacklistedToken.objects.exists())
        resp = self.client.post(REFRESH_URL, {'refresh': refresh}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(OutstandingToken.objects.count(), 1)  # новый refresh не выдан

    def test_login_and_refresh_carry_current_version(self):
        from .services import revoke_all_sessions
        user = make_user('owner@test.com')
        revoke_all_sessions(user)
        login = self.client.post(TOKEN_URL, {'email': 'owner@test.com', 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.assertEqual(RefreshToken(login.cookies['refresh'].value)['sv'], 1)
        refreshed = self.client.post(REFRESH_URL, {'refresh': login.cookies['refresh'].value}, format='json')
        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertEqual(RefreshToken(refreshed.cookies['refresh'].value)['sv'], 1)

    def test_ban_unban_old_refresh_and_access_stay_dead(self):
        from .services import ban_user, unban_user
        user = make_user('owner@test.com')
        refresh, access = _session(user)
        ban_user(user)
        unban_user(user)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(self.client.post(REFRESH_URL, {'refresh': refresh}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)


class TestCookieCsrf(PasswordTestCase):

    def _cookie_client(self, user):
        _, access = _session(user)
        client = APIClient(enforce_csrf_checks=True)
        client.cookies['access'] = access
        return client

    def test_password_change_with_cookie_and_no_csrf_is_403(self):
        user = make_user('owner@test.com')
        resp = self._cookie_client(user).post(CHANGE_URL, {
            'old_password': TEST_PASSWORD, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        user.refresh_from_db()
        self.assertTrue(user.check_password(TEST_PASSWORD))

    def test_logout_all_with_cookie_and_no_csrf_is_403(self):
        user = make_user('owner@test.com')
        resp = self._cookie_client(user).post(LOGOUT_ALL_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        user.refresh_from_db()
        self.assertEqual(user.session_version, 0)


class TestReportBanAndAdminForm(PasswordTestCase):

    def test_report_ban_revokes_sessions_and_skips_superuser(self):
        from reports.admin import ban_reported_user
        from reports.models import Report
        victim = make_user('victim@test.com')
        boss = make_staff('boss@test.com', superuser=True)
        reporter = make_user('rep@test.com')
        refresh, access = _session(victim)
        reports = [Report.objects.create(reporter=reporter, reported_user=u, reason='fraud')
                   for u in (victim, boss)]
        request = RequestFactory().post('/admin/')
        request.user = boss
        request._messages = mock.Mock()
        ban_reported_user(CustomUserAdmin(User, admin_site), request,
                          Report.objects.filter(pk__in=[r.pk for r in reports]))
        victim.refresh_from_db()
        boss.refresh_from_db()
        self.assertTrue(victim.is_banned)
        self.assertFalse(boss.is_banned)
        self.assertTrue(boss.is_active)
        self.assertEqual(self.client.post(REFRESH_URL, {'refresh': refresh}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_form_deactivation_revokes_sessions(self):
        user = make_user('owner@test.com')
        _, access = _session(user)
        model_admin = CustomUserAdmin(User, admin_site)
        request = RequestFactory().post('/admin/')
        request.user = make_staff(superuser=True)
        user.is_active = False
        form = mock.Mock(changed_data=['is_active'])
        model_admin.save_model(request, user, form, change=True)
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_is_banned_is_readonly_in_admin_form(self):
        model_admin = CustomUserAdmin(User, admin_site)
        self.assertIn('is_banned', model_admin.readonly_fields)
