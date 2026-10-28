"""Вход через Keycloak (SSO-1). Сети нет: RSA-ключ генерируется здесь, token endpoint и JWKS мокаются."""
import time
from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core import signing
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from tests.base import CleanCacheTestCase
from tests.factories import make_admin_role, make_moderator, make_staff, make_user

from . import oidc
from .jwt import SESSION_CLAIM
from .models import CustomUser, OidcIdentity
from .oidc_views import FLOW_COOKIE, FLOW_COOKIE_SALT, safe_next

START = '/api/v1/auth/oidc/start/'
CALLBACK = '/api/v1/auth/oidc/callback/'
LOGOUT = '/api/v1/auth/oidc/logout/'
CONFIG = '/api/v1/auth/config/'

ALICE = 'ad_alice@corp.example.test'
SUB = '6f1c3c1e-0000-4000-8000-00000000a11c'
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
DROP = object()


def make_id_token(nonce, *, key=KEY, alg='RS256', **overrides):
    now = int(time.time())
    claims = {
        'iss': settings.OIDC_ISSUER, 'aud': settings.OIDC_CLIENT_ID, 'azp': settings.OIDC_CLIENT_ID,
        'sub': SUB, 'iat': now, 'exp': now + 300, 'nonce': nonce,
        'email': ALICE, 'email_verified': True, 'preferred_username': 'ad_alice',
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not DROP}, key, algorithm=alg)


@override_settings(OIDC_ENABLED=True)
class OidcTestCase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        jwks = mock.Mock()
        jwks.get_signing_key_from_jwt.return_value = mock.Mock(key=KEY.public_key())
        patcher = mock.patch('users.oidc._jwk_client', return_value=jwks)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch('users.oidc.httpx.post')
        self.token_post = patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, next_path='/me'):
        response = self.client.get(START, {'next': next_path})
        flow = signing.loads(self.client.cookies[FLOW_COOKIE].value, salt=FLOW_COOKIE_SALT)
        return response, flow

    def sign_in(self, *, state=None, token=None, **claims):
        """start -> Keycloak (id_token с nonce этого входа) -> callback."""
        _, flow = self.start()
        token = token or make_id_token(flow['nonce'], **claims)
        self.token_post.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={'id_token': token}))
        return self.client.get(CALLBACK, {'code': 'auth-code', 'state': state or flow['state']})

    def assertSignedIn(self, response, next_path='/me'):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], next_path)
        self.assertTrue(response.cookies[settings.AUTH_COOKIE_ACCESS_NAME].value)
        self.assertTrue(response.cookies[settings.AUTH_COOKIE_REFRESH_NAME].value)
        self.assertEqual(response.cookies[FLOW_COOKIE].value, '')
        hint = response.cookies[settings.AUTH_COOKIE_SSO_HINT_NAME]
        self.assertEqual(hint.value, '1')
        self.assertFalse(hint['httponly'])

    def assertRefused(self, response, code):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'/login?sso_error={code}')
        self.assertNotIn(settings.AUTH_COOKIE_ACCESS_NAME, response.cookies)
        self.assertNotIn(settings.AUTH_COOKIE_REFRESH_NAME, response.cookies)
        self.assertEqual(response.cookies[FLOW_COOKIE].value, '')


class StartTests(OidcTestCase):
    def test_redirects_to_keycloak_with_pkce(self):
        response, flow = self.start()
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response['Location'])
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}',
                         'http://kc-browser.test/realms/myapp/protocol/openid-connect/auth')
        query = parse_qs(url.query)
        self.assertEqual(query['client_id'], ['autoforyou'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['code_challenge'], [oidc._code_challenge(flow['code_verifier'])])
        self.assertEqual(query['state'], [flow['state']])
        self.assertEqual(query['nonce'], [flow['nonce']])
        self.assertEqual(query['scope'], ['openid email profile'])
        self.assertEqual(query['redirect_uri'], [settings.OIDC_REDIRECT_URI])
        self.assertEqual(flow['next'], '/me')

    def test_flow_cookie_is_httponly_lax_and_short_lived(self):
        response, _ = self.start()
        cookie = response.cookies[FLOW_COOKIE]
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'], 'Lax')
        self.assertEqual(cookie['path'], '/api/v1/auth/oidc/')
        self.assertEqual(cookie['max-age'], 600)

    def test_code_challenge_is_base64url_sha256_without_padding(self):
        # RFC 7636, приложение B.
        self.assertEqual(oidc._code_challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'),
                         'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')

    def test_foreign_next_becomes_root(self):
        for value in ('https://evil.example', '//evil.example/x', '/\\evil.example', '/\t/evil.example',
                      '///evil.example', 'me', ''):
            with self.subTest(value=value):
                _, flow = self.start(value)
                self.assertEqual(flow['next'], '/')

    def test_safe_next_keeps_own_path_with_query(self):
        self.assertEqual(safe_next('/listings?page=2'), '/listings?page=2')


class CallbackSuccessTests(OidcTestCase):
    def test_verified_email_signs_in_existing_user_and_links_sub(self):
        user = make_user(ALICE)
        response = self.sign_in()
        self.assertSignedIn(response)
        self.assertEqual(OidcIdentity.objects.get(sub=SUB).user, user)
        refresh = RefreshToken(response.cookies[settings.AUTH_COOKIE_REFRESH_NAME].value)
        self.assertEqual(refresh['user_id'], str(user.pk))
        user.refresh_from_db()
        self.assertIsNotNone(user.last_login)

    def test_token_request_carries_pkce_verifier_and_secret(self):
        make_user(ALICE)
        _, flow = self.start()
        self.token_post.return_value = mock.Mock(
            status_code=200, json=mock.Mock(return_value={'id_token': make_id_token(flow['nonce'])}))
        self.client.get(CALLBACK, {'code': 'auth-code', 'state': flow['state']})
        url = self.token_post.call_args.args[0]
        data = self.token_post.call_args.kwargs['data']
        self.assertEqual(url, 'http://kc-backend.test/realms/myapp/protocol/openid-connect/token')
        self.assertEqual(data['code_verifier'], flow['code_verifier'])
        self.assertEqual(data['grant_type'], 'authorization_code')
        self.assertEqual(data['client_secret'], settings.OIDC_CLIENT_SECRET)
        self.assertEqual(self.token_post.call_args.kwargs['timeout'], 5)

    def test_second_sign_in_finds_user_by_sub_after_email_change_in_keycloak(self):
        user = make_user(ALICE)
        self.assertSignedIn(self.sign_in())
        response = self.sign_in(email='alice.new@corp.example.test')
        self.assertSignedIn(response)
        refresh = RefreshToken(response.cookies[settings.AUTH_COOKIE_REFRESH_NAME].value)
        self.assertEqual(refresh['user_id'], str(user.pk))

    def test_email_match_ignores_case(self):
        make_user(ALICE)
        self.assertSignedIn(self.sign_in(email='AD_Alice@Corp.Example.Test'))

    def test_role_and_session_version_unchanged_refresh_has_sv(self):
        user = make_user(ALICE, role='dealer', session_version=3)
        response = self.sign_in()
        self.assertSignedIn(response)
        user.refresh_from_db()
        self.assertEqual(user.role, 'dealer')
        self.assertEqual(user.session_version, 3)
        refresh = RefreshToken(response.cookies[settings.AUTH_COOKIE_REFRESH_NAME].value)
        self.assertEqual(refresh[SESSION_CLAIM], 3)

    def test_unverified_local_email_without_password_becomes_verified(self):
        user = make_user(ALICE, verified=False, password=None)
        self.assertSignedIn(self.sign_in())
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)

    def test_unverified_local_email_with_password_is_refused(self):
        # Аккаунт мог зарегистрировать паролем чужой человек: владелец адреса в него не попадает.
        user = make_user(ALICE, verified=False)
        self.assertRefused(self.sign_in(), 'not_allowed')
        self.assertFalse(OidcIdentity.objects.exists())
        user.refresh_from_db()
        self.assertFalse(user.is_email_verified)

    def test_too_many_attempts_redirect_to_login(self):
        make_user(ALICE)
        # scope login - только у callback: start не тратит попытку входа.
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'login': '1/min'}):
            self.assertSignedIn(self.sign_in())
            response = self.sign_in()
        self.assertRefused(response, 'throttled')


class CallbackRefusalTests(OidcTestCase):
    def test_unverified_email_is_refused_without_link(self):
        make_user(ALICE)
        for value in (False, DROP, 'true'):
            with self.subTest(email_verified=value):
                self.assertRefused(self.sign_in(email_verified=value), 'not_allowed')
                self.assertFalse(OidcIdentity.objects.exists())

    def test_no_account_is_refused_and_user_not_created(self):
        response = self.sign_in()
        self.assertRefused(response, 'no_account')
        self.assertFalse(CustomUser.objects.filter(email__iexact=ALICE).exists())
        self.assertFalse(OidcIdentity.objects.exists())

    def test_privileged_users_are_not_linked_by_email(self):
        makers = {
            'staff': lambda: make_staff(ALICE),
            'superuser': lambda: make_staff(ALICE, superuser=True),
            'broker': lambda: make_user(ALICE, role='broker'),
            'moderator': lambda: make_moderator(ALICE),
            'admin': lambda: make_admin_role(ALICE),
        }
        for name, make in makers.items():
            with self.subTest(name):
                user = make()
                self.assertRefused(self.sign_in(), 'not_allowed')
                self.assertFalse(OidcIdentity.objects.exists())
                user.delete()

    def test_privileged_user_signs_in_after_link_command(self):
        user = make_admin_role(ALICE)
        call_command('link_oidc_user', f'{ALICE}={SUB}', stdout=mock.Mock())
        response = self.sign_in()
        self.assertSignedIn(response)
        user.refresh_from_db()
        self.assertEqual(user.role, 'admin')

    def test_blocked_users_are_refused(self):
        now = timezone.now()
        for field, value in (
            ('is_banned', True), ('is_active', False), ('deleted_at', now), ('deletion_scheduled_at', now),
        ):
            with self.subTest(field):
                user = make_user(ALICE, **{field: value})
                self.assertRefused(self.sign_in(), 'not_allowed')
                self.assertFalse(OidcIdentity.objects.exists())
                user.delete()

    def test_banned_after_link_is_refused_by_sub(self):
        user = make_user(ALICE)
        self.assertSignedIn(self.sign_in())
        CustomUser.objects.filter(pk=user.pk).update(is_banned=True)
        self.assertRefused(self.sign_in(), 'not_allowed')

    def test_user_linked_to_another_sub_is_refused(self):
        user = make_user(ALICE)
        OidcIdentity.objects.create(user=user, sub='another-keycloak-account')
        self.assertRefused(self.sign_in(), 'not_allowed')
        self.assertFalse(OidcIdentity.objects.filter(sub=SUB).exists())

    def test_concurrent_link_of_sub_is_refused(self):
        # Два первых входа одновременно: связь уже создал другой запрос.
        make_user(ALICE)
        with mock.patch.object(OidcIdentity.objects, 'create', side_effect=IntegrityError):
            self.assertRefused(self.sign_in(), 'not_allowed')

    def test_keycloak_error_is_refused_without_token_request(self):
        make_user(ALICE)
        self.start()
        response = self.client.get(CALLBACK, {'error': 'access_denied', 'state': 'x'})
        self.assertRefused(response, 'cancelled')
        self.token_post.assert_not_called()

    def test_token_endpoint_failure_is_refused(self):
        make_user(ALICE)
        _, flow = self.start()
        self.token_post.return_value = mock.Mock(status_code=400, json=mock.Mock(return_value={'error': 'invalid_grant'}))
        self.assertRefused(self.client.get(CALLBACK, {'code': 'c', 'state': flow['state']}), 'failed')


class CallbackForgeryTests(OidcTestCase):
    def setUp(self):
        super().setUp()
        make_user(ALICE)

    def assertForgeryRefused(self, response):
        self.assertRefused(response, 'failed')
        self.assertFalse(OidcIdentity.objects.exists())

    def test_state_mismatch(self):
        self.assertForgeryRefused(self.sign_in(state='forged-state'))

    def test_no_flow_cookie_gives_nothing(self):
        # Публичный эндпоинт: без cookie от start ничего не выдаёт и в Keycloak не ходит.
        response = self.client.get(CALLBACK, {'code': 'c', 'state': 's'})
        self.assertForgeryRefused(response)
        self.token_post.assert_not_called()

    def test_tampered_flow_cookie(self):
        _, flow = self.start()
        self.client.cookies[FLOW_COOKIE] = signing.dumps(flow, salt='another-salt')
        self.assertForgeryRefused(self.client.get(CALLBACK, {'code': 'c', 'state': flow['state']}))
        self.token_post.assert_not_called()

    def test_flow_cookie_older_than_600_seconds(self):
        _, flow = self.start()
        with mock.patch('django.core.signing.time') as fake_time:
            fake_time.time.return_value = time.time() + 601
            response = self.client.get(CALLBACK, {'code': 'c', 'state': flow['state']})
        self.assertForgeryRefused(response)
        self.token_post.assert_not_called()

    def test_foreign_audience(self):
        # Без azp: отказ должен дать именно проверка audience.
        self.assertForgeryRefused(self.sign_in(aud='another-client', azp=DROP))

    def test_foreign_azp(self):
        self.assertForgeryRefused(self.sign_in(aud=['autoforyou', 'another-client'], azp='another-client'))

    def test_foreign_issuer(self):
        self.assertForgeryRefused(self.sign_in(iss='http://evil.example/realms/myapp'))

    def test_expired_token(self):
        now = int(time.time())
        self.assertForgeryRefused(self.sign_in(iat=now - 600, exp=now - 300))

    def test_missing_exp(self):
        self.assertForgeryRefused(self.sign_in(exp=DROP))

    def test_nonce_mismatch(self):
        _, flow = self.start()
        token = make_id_token('another-nonce')
        self.token_post.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={'id_token': token}))
        self.assertForgeryRefused(self.client.get(CALLBACK, {'code': 'c', 'state': flow['state']}))

    def test_signed_by_another_key(self):
        _, flow = self.start()
        token = make_id_token(flow['nonce'], key=OTHER_KEY)
        self.token_post.return_value = mock.Mock(status_code=200, json=mock.Mock(return_value={'id_token': token}))
        self.assertForgeryRefused(self.client.get(CALLBACK, {'code': 'c', 'state': flow['state']}))

    def test_alg_none_and_hs256(self):
        for alg, key in (('none', None), ('HS256', 'shared-secret-guess')):
            with self.subTest(alg):
                _, flow = self.start()
                token = make_id_token(flow['nonce'], key=key, alg=alg)
                self.token_post.return_value = mock.Mock(
                    status_code=200, json=mock.Mock(return_value={'id_token': token}))
                self.assertForgeryRefused(self.client.get(CALLBACK, {'code': 'c', 'state': flow['state']}))


class LogoutAndConfigTests(OidcTestCase):
    def test_logout_clears_cookies_and_goes_to_keycloak_logout(self):
        response = self.client.get(LOGOUT)
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response['Location'])
        self.assertEqual(f'{url.scheme}://{url.netloc}{url.path}',
                         'http://kc-browser.test/realms/myapp/protocol/openid-connect/logout')
        query = parse_qs(url.query)
        self.assertEqual(query['client_id'], ['autoforyou'])
        self.assertEqual(query['post_logout_redirect_uri'], [settings.OIDC_POST_LOGOUT_REDIRECT_URI])
        self.assertEqual(response.cookies[settings.AUTH_COOKIE_ACCESS_NAME].value, '')
        self.assertEqual(response.cookies[settings.AUTH_COOKIE_SSO_HINT_NAME].value, '')

    def test_logout_blacklists_refresh_if_password_logout_failed(self):
        refresh = RefreshToken.for_user(make_user(ALICE))
        self.client.cookies[settings.AUTH_COOKIE_REFRESH_NAME] = str(refresh)
        self.client.get(LOGOUT)
        with self.assertRaises(TokenError):
            RefreshToken(str(refresh)).check_blacklist()

    def test_password_logout_clears_sso_hint(self):
        response = self.client.post('/api/v1/auth/token/logout/', {}, content_type='application/json')
        self.assertEqual(response.cookies[settings.AUTH_COOKIE_SSO_HINT_NAME].value, '')

    def test_config_advertises_sso(self):
        body = self.client.get(CONFIG).json()
        self.assertIs(body['oidc_enabled'], True)
        self.assertEqual(body['oidc_start_url'], START)
        self.assertEqual(body['oidc_logout_url'], LOGOUT)


@override_settings(OIDC_ENABLED=False)
class DisabledTests(CleanCacheTestCase):
    def test_routes_are_404(self):
        for path in (START, CALLBACK, LOGOUT):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_config_says_disabled(self):
        body = self.client.get(CONFIG).json()
        self.assertIs(body['oidc_enabled'], False)
        self.assertIsNone(body['oidc_start_url'])


class LinkCommandTests(CleanCacheTestCase):
    def test_existing_link_needs_replace(self):
        user = make_admin_role(ALICE)
        OidcIdentity.objects.create(user=user, sub='old-sub')
        with self.assertRaisesMessage(CommandError, '--replace'):
            call_command('link_oidc_user', f'{ALICE}={SUB}', stdout=mock.Mock())
        call_command('link_oidc_user', f'{ALICE}={SUB}', '--replace', stdout=mock.Mock())
        self.assertEqual(OidcIdentity.objects.get(user=user).sub, SUB)

    def test_sub_of_another_user_needs_replace(self):
        bob = make_user('ad_bob@corp.example.test')
        OidcIdentity.objects.create(user=bob, sub=SUB)
        alice = make_admin_role(ALICE)
        with self.assertRaisesMessage(CommandError, 'ad_bob@corp.example.test'):
            call_command('link_oidc_user', f'{ALICE}={SUB}', stdout=mock.Mock())
        call_command('link_oidc_user', f'{ALICE}={SUB}', '--replace', stdout=mock.Mock())
        self.assertEqual(OidcIdentity.objects.get(sub=SUB).user, alice)
        self.assertFalse(OidcIdentity.objects.filter(user=bob).exists())

    def test_same_email_in_two_cases_is_an_error(self):
        make_user(ALICE)
        make_user(ALICE.upper())
        with self.assertRaisesMessage(CommandError, 'Несколько пользователей'):
            call_command('link_oidc_user', f'{ALICE}={SUB}', stdout=mock.Mock())

    def test_bad_format_and_unknown_user(self):
        with self.assertRaisesMessage(CommandError, 'Формат'):
            call_command('link_oidc_user', 'no-separator', stdout=mock.Mock())
        with self.assertRaisesMessage(CommandError, 'Нет пользователя'):
            call_command('link_oidc_user', f'nobody@example.test={SUB}', stdout=mock.Mock())


class ExpiryHelperTests(CleanCacheTestCase):
    def test_deletion_far_in_future_still_blocks(self):
        user = make_user(ALICE, deletion_scheduled_at=timezone.now() + timedelta(days=30))
        with self.assertRaisesMessage(oidc.OidcError, 'deletion scheduled'):
            oidc.find_user({'sub': SUB, 'email': ALICE, 'email_verified': True})
        self.assertFalse(OidcIdentity.objects.filter(user=user).exists())
