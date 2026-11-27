"""users/lockout.py и users/permissions.py: тесты против выживших мутантов (scripts/mutation.sh access).

lockout: окно и длительность блокировки берутся из настроек в секундах, остаток считается от
текущего времени, истёкший ключ между add и incr не ломает счёт. permissions: каждый класс
пропускает только свою роль (IsBroker/IsModerator сейчас не подключены к view - тем более нужны тесты).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from users import lockout
from users.permissions import IsAdminRole, IsBroker, IsBrokerOrAdmin, IsEmailVerified, IsModerator

NOW = 1_000_000.0


@override_settings(LOGIN_FAILURE_WINDOW_MINUTES=7, LOGIN_LOCKOUT_MINUTES=11, LOGIN_MAX_FAILURES=3)
@patch('users.lockout.time.time', return_value=NOW)
class LockoutTests(SimpleTestCase):
    def _cache(self, incr=1, get=None):
        cache = MagicMock()
        cache.incr.return_value = incr
        cache.get.return_value = get
        return cache

    def test_failure_count_defaults_to_zero(self, _time):
        with patch('users.lockout.cache', self._cache()) as cache:
            cache.get.side_effect = lambda key, default=None: default
            self.assertEqual(lockout.failure_count('a@example.com'), 0)

    def test_attempt_within_limit_uses_window_in_seconds(self, _time):
        with patch('users.lockout.cache', self._cache(incr=3)) as cache:
            self.assertEqual(lockout.reserve_attempt('a@example.com', '1.2.3.4'), (3, None))
        cache.add.assert_called_once_with(lockout._fail_key('a@example.com'), 0, timeout=7 * 60)
        cache.set.assert_not_called()

    def test_expired_key_between_add_and_incr_restarts_count(self, _time):
        with patch('users.lockout.cache', self._cache()) as cache:
            cache.incr.side_effect = ValueError
            self.assertEqual(lockout.reserve_attempt('a@example.com', '1.2.3.4'), (1, None))
        cache.set.assert_called_once_with(lockout._fail_key('a@example.com'), 1, timeout=7 * 60)

    def test_over_limit_locks_for_lockout_minutes(self, _time):
        with patch('users.lockout.cache', self._cache(incr=4)) as cache:
            self.assertEqual(lockout.reserve_attempt('a@example.com', '1.2.3.4'), (4, 11 * 60))
        cache.set.assert_called_once_with(lockout._lock_key('a@example.com'), NOW + 11 * 60, timeout=11 * 60)
        cache.delete.assert_called_once_with(lockout._fail_key('a@example.com'))

    def test_is_locked_returns_remaining_seconds(self, _time):
        for until, expected in ((NOW + 90.7, 90), (NOW + 1.5, 1)):
            with self.subTest(until=until), patch('users.lockout.cache', self._cache(get=until)):
                self.assertEqual(lockout.is_locked('a@example.com'), expected)

    def test_lockout_log_has_short_hash_prefix_and_ip(self, _time):
        with patch('users.lockout.cache', self._cache(incr=4)), self.assertLogs('users.lockout', 'WARNING') as logs:
            lockout.reserve_attempt('a@example.com', '1.2.3.4')
        prefix = lockout._digest('a@example.com')[:12]
        self.assertEqual(logs.records[0].getMessage(), f'login lockout: account={prefix} ip=1.2.3.4')

    def test_is_locked_none_at_or_after_expiry(self, _time):
        for until in (NOW, NOW + 0.5, NOW - 5):
            with self.subTest(until=until), patch('users.lockout.cache', self._cache(get=until)):
                self.assertIsNone(lockout.is_locked('a@example.com'))

    def test_is_locked_none_without_lock(self, _time):
        with patch('users.lockout.cache', self._cache(get=None)):
            self.assertIsNone(lockout.is_locked('a@example.com'))


def _request(authenticated=True, **flags):
    defaults = dict(is_broker=False, is_moderator=False, is_admin_role=False, is_email_verified=False,
                    is_superuser=False)
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=authenticated, **{**defaults, **flags}))


class PermissionClassesTests(SimpleTestCase):
    CASES = [
        (IsBroker, {'is_broker': True}, {'is_moderator': True, 'is_admin_role': True}),
        (IsBrokerOrAdmin, {'is_broker': True}, {'is_moderator': True}),
        (IsBrokerOrAdmin, {'is_admin_role': True}, {}),
        (IsModerator, {'is_moderator': True}, {'is_broker': True}),
        (IsModerator, {'is_admin_role': True}, {}),
        (IsAdminRole, {'is_admin_role': True}, {'is_broker': True, 'is_moderator': True}),
    ]

    def test_only_matching_role_passes(self):
        for cls, allowed, denied in self.CASES:
            with self.subTest(cls=cls.__name__, allowed=allowed):
                self.assertIs(cls().has_permission(_request(**allowed), None), True)
                self.assertIs(cls().has_permission(_request(**denied), None), False)

    def test_role_flags_without_authentication_are_denied(self):
        for cls, allowed, _ in self.CASES:
            with self.subTest(cls=cls.__name__):
                self.assertIs(cls().has_permission(_request(authenticated=False, **allowed), None), False)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=False)
    def test_email_verified_not_required_lets_everyone(self):
        self.assertIs(IsEmailVerified().has_permission(_request(authenticated=False), None), True)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_email_verified_required(self):
        perm = IsEmailVerified()
        self.assertIs(perm.has_permission(_request(is_email_verified=True), None), True)
        self.assertIs(perm.has_permission(_request(is_superuser=True), None), True)
        self.assertIs(perm.has_permission(_request(), None), False)
        self.assertIs(perm.has_permission(_request(authenticated=False, is_email_verified=True), None), False)
