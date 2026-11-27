"""users/oidc.py: тесты против выживших мутантов cosmic-ray (scripts/mutation.sh sso).

Главное: email считается подтверждённым только при email_verified именно True (не 1 и не "true"),
чужой azp отсекается при любом значении, ответ token endpoint принимается только с HTTP 200,
state/nonce/PKCE - по 32 случайных байта. Проверка неоднозначного email (users[:2], len > 1) -
вторая линия: в БД уникальность Lower('email'), мутанты там эквивалентны.
"""
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings

from tests.base import CleanCacheTestCase
from tests.factories import make_user

from . import oidc
from .tests_oidc import KEY, make_id_token


class AuthRequestEntropyTests(SimpleTestCase):
    def test_state_nonce_verifier_are_32_random_bytes(self):
        _, flow = oidc.build_auth_request('/me')
        for name in ('state', 'nonce', 'code_verifier'):
            with self.subTest(name=name):
                self.assertEqual(len(flow[name]), 43)  # base64url без padding от 32 байт


@mock.patch('users.oidc.httpx.post')
class ExchangeCodeTests(SimpleTestCase):
    def _response(self, status, body=None, json_error=None):
        json = mock.Mock(side_effect=json_error) if json_error else mock.Mock(return_value=body)
        return mock.Mock(status_code=status, json=json)

    def test_id_token_only_from_http_200(self, post):
        for status in (199, 201, 500):
            with self.subTest(status=status):
                post.return_value = self._response(status, {'id_token': 'tok'})
                with self.assertRaisesMessage(oidc.OidcError, 'no id_token'):
                    oidc.exchange_code('code', 'verifier')
        post.return_value = self._response(200, {'id_token': 'tok'})
        self.assertEqual(oidc.exchange_code('code', 'verifier'), 'tok')

    def test_network_error_and_bad_json_are_oidc_errors(self, post):
        for effect, name in ((httpx.ConnectError('down'), 'ConnectError'), (None, 'ValueError')):
            with self.subTest(name=name):
                if effect:
                    post.side_effect = effect
                else:
                    post.side_effect = None
                    post.return_value = self._response(200, json_error=ValueError('bad json'))
                with self.assertRaisesMessage(oidc.OidcError, f'token endpoint: {name}'):
                    oidc.exchange_code('code', 'verifier')

    def test_empty_or_non_string_id_token_is_refused(self, post):
        for token in ('', 123, None):
            with self.subTest(token=token):
                post.return_value = self._response(200, {'id_token': token})
                with self.assertRaisesMessage(oidc.OidcError, 'no id_token'):
                    oidc.exchange_code('code', 'verifier')


class JwkClientCacheTests(SimpleTestCase):
    def test_client_is_created_once_per_url_with_key_cache(self):
        self.addCleanup(oidc._jwk_clients.clear)
        oidc._jwk_clients.clear()
        with mock.patch('users.oidc.jwt.PyJWKClient') as client_cls:
            first, second = oidc._jwk_client(), oidc._jwk_client()
        self.assertIs(first, second)
        client_cls.assert_called_once_with(oidc.certs_endpoint(), cache_keys=True, timeout=oidc.TOKEN_TIMEOUT)


class VerifyIdTokenTests(SimpleTestCase):
    def setUp(self):
        jwks = mock.Mock()
        jwks.get_signing_key_from_jwt.return_value = mock.Mock(key=KEY.public_key())
        patcher = mock.patch('users.oidc._jwk_client', return_value=jwks)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_foreign_azp_refused_whatever_its_order(self):
        for azp in ('0-before', 'zzz-after'):
            with self.subTest(azp=azp), self.assertRaisesMessage(oidc.OidcError, 'foreign azp'):
                oidc.verify_id_token(make_id_token('n1', azp=azp), 'n1')

    def test_empty_sub_refused(self):
        with self.assertRaisesMessage(oidc.OidcError, 'id_token'):
            oidc.verify_id_token(make_id_token('n1', sub=''), 'n1')


class VerifiedEmailTests(SimpleTestCase):
    def test_only_boolean_true_counts(self):
        for flag in (1, 'true', 'True', None, False):
            with self.subTest(flag=flag):
                self.assertEqual(oidc.verified_email({'email': 'a@x.test', 'email_verified': flag}), '')
        self.assertEqual(oidc.verified_email({'email': ' a@x.test ', 'email_verified': True}), 'a@x.test')
        self.assertEqual(oidc.verified_email({'email': 42, 'email_verified': True}), '')


@override_settings(OIDC_ENABLED=True)
class MarkSignedInTests(CleanCacheTestCase):
    def _user(self, verified):
        return make_user('pat@corp.example.test', verified=verified)

    def test_unverified_local_email_verified_on_same_address_any_case(self):
        user = self._user(False)
        oidc.mark_signed_in(user, {'email': 'PAT@corp.example.test', 'email_verified': True})
        user.refresh_from_db()
        self.assertIs(user.is_email_verified, True)

    def test_other_address_or_unverified_claim_does_not_verify(self):
        for claims in ({'email': 'other@corp.example.test', 'email_verified': True},
                       {'email': 'pat@corp.example.test', 'email_verified': False},
                       {'email': 'aaa@corp.example.test', 'email_verified': True},
                       {'email': 'zzz@corp.example.test', 'email_verified': True}):
            with self.subTest(claims=claims):
                user = self._user(False)
                oidc.mark_signed_in(user, claims)
                user.refresh_from_db()
                self.assertIs(user.is_email_verified, False)
                user.delete()

    def test_already_verified_user_is_not_saved_again(self):
        user = self._user(True)
        with mock.patch.object(type(user), 'save') as save:
            oidc.mark_signed_in(user, {'email': 'pat@corp.example.test', 'email_verified': True})
        # update_last_login сохраняет last_login; флаг email повторно не пишется.
        self.assertEqual(save.call_args_list, [mock.call(update_fields=['last_login'])])
