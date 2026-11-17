"""Задача 1.17 (D1-D8): отзыв сессий при смене пароля вне API, регистр email, лимиты, права в админке."""
import importlib
import threading
import unittest
from unittest import mock

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.base import CleanCacheTestCase
from tests.factories import TEST_PASSWORD, make_user

from .jwt import VersionedRefreshToken
from .models import DealerApplication
from .services import DuplicatePendingError, apply_for_dealer

User = get_user_model()

REGISTER_URL = '/api/v1/auth/register/'
RESET_URL = '/api/v1/auth/password-reset/'
TOKEN_URL = '/api/v1/auth/token/'
REFRESH_URL = '/api/v1/auth/token/refresh/'
PROFILE_URL = '/api/v1/auth/profile/'
CHANGE_URL = '/api/v1/auth/password-change/'
APPLY_URL = '/api/v1/dealers/apply/'
NEW_PASSWORD = 'Brand-new-Pass-7391'
STRONG = 'Zx9-unrelated-Pw-4417'

_REG = {
    'email': 'fresh@test.com', 'password': STRONG, 'password2': STRONG,
    'agreed_to_terms': True, 'confirmed_age_18': True,
}


def _tokens(user):
    refresh = VersionedRefreshToken.for_user(user)
    return str(refresh), str(refresh.access_token)


def _bearer(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
    return client


class SessionRevokeOutsideApiTests(CleanCacheTestCase):
    """D1: смена пароля через админку и changepassword отзывает сессии."""

    def setUp(self):
        super().setUp()
        self.victim = make_user('victim@test.com')
        self.refresh, self.access = _tokens(self.victim)
        self.api = APIClient()

    def _assert_old_session_dead_new_login_works(self, password):
        self.assertEqual(_bearer(self.access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.api.post(REFRESH_URL, {'refresh': self.refresh}, format='json').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.api.post(TOKEN_URL, {'email': 'victim@test.com', 'password': password}, format='json').status_code,
            status.HTTP_200_OK,
        )

    def test_admin_password_change_form_revokes_sessions(self):
        boss = make_user('boss@test.com', is_staff=True, is_superuser=True)
        self.client.force_login(boss)
        url = reverse('admin:auth_user_password_change', args=[self.victim.pk])
        resp = self.client.post(url, {'password1': NEW_PASSWORD, 'password2': NEW_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self._assert_old_session_dead_new_login_works(NEW_PASSWORD)

    def test_changepassword_command_revokes_sessions(self):
        with mock.patch(
            'django.contrib.auth.management.commands.changepassword.getpass.getpass',
            side_effect=[NEW_PASSWORD, NEW_PASSWORD],
        ):
            call_command('changepassword', 'victim@test.com', stdout=mock.Mock())
        self._assert_old_session_dead_new_login_works(NEW_PASSWORD)

    def test_anonymous_cannot_use_admin_password_form(self):
        url = reverse('admin:auth_user_password_change', args=[self.victim.pk])
        resp = self.client.post(url, {'password1': NEW_PASSWORD, 'password2': NEW_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn('/admin/login/', resp['Location'])
        self.victim.refresh_from_db()
        self.assertTrue(self.victim.check_password(TEST_PASSWORD))

    def test_one_shift_per_password_change(self):
        for save_kwargs in ({}, {'update_fields': ['password']}):
            user = User.objects.get(pk=self.victim.pk)
            before = user.session_version
            user.set_password(NEW_PASSWORD)
            user.save(**save_kwargs)
            user.save()  # повторное сохранение сдвиг не повторяет
            user.refresh_from_db()
            self.assertEqual(user.session_version, before + 1)

    def test_api_password_change_shifts_exactly_once(self):
        resp = _bearer(self.access).post(CHANGE_URL, {
            'old_password': TEST_PASSWORD, 'new_password': NEW_PASSWORD, 'new_password2': NEW_PASSWORD,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(User.objects.get(pk=self.victim.pk).session_version, 1)

    def test_hash_upgrade_on_login_does_not_revoke_sessions(self):
        # пароль не менялся, пересчитывается только хэш (устаревший алгоритм) - чужие сессии живут
        with override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher']):
            legacy = make_user('legacy@test.com')
        self.assertTrue(legacy.password.startswith('pbkdf2_sha1$'))
        resp = self.api.post(TOKEN_URL, {'email': 'legacy@test.com', 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        legacy.refresh_from_db()
        self.assertTrue(legacy.password.startswith('pbkdf2_sha256$'))  # апгрейд был
        self.assertEqual(legacy.session_version, 0)

    def test_new_user_does_not_shift(self):
        self.assertEqual(make_user('new@test.com').session_version, 0)


@override_settings(CAPTCHA_PROVIDER='off')
class EmailCaseTests(CleanCacheTestCase):
    """D2: один аккаунт на адрес независимо от регистра."""

    def test_login_is_case_insensitive(self):
        user = make_user('john.doe@test.com')
        client = APIClient()
        for typed in ('John.Doe@test.com', 'john.doe@test.com'):
            resp = client.post(TOKEN_URL, {'email': typed, 'password': TEST_PASSWORD}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_200_OK, typed)
        self.assertEqual(User.objects.get().pk, user.pk)

    def test_email_is_stored_lowercase(self):
        user = make_user('Mixed.Case@Test.COM')
        self.assertEqual(user.email, 'mixed.case@test.com')
        user.email = 'AGAIN@Test.com'
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.email, 'again@test.com')

    def test_register_other_case_answers_like_new_account(self):
        make_user('john.doe@test.com')
        client = APIClient()
        fresh = client.post(REGISTER_URL, {**_REG, 'email': 'brand.new@test.com'}, format='json')
        dup = client.post(REGISTER_URL, {**_REG, 'email': 'John.Doe@test.com'}, format='json')
        self.assertEqual(dup.status_code, status.HTTP_201_CREATED)
        self.assertEqual(set(dup.json()), set(fresh.json()))
        self.assertEqual(User.objects.filter(email__iexact='john.doe@test.com').count(), 1)

    def test_register_stores_lowercase(self):
        resp = APIClient().post(REGISTER_URL, {**_REG, 'email': 'New.User@Test.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='new.user@test.com').exists())

    def test_db_rejects_duplicate_by_lower_email(self):
        make_user('john.doe@test.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            # bulk_create обходит save(): проверяем именно constraint в БД
            User.objects.bulk_create([User(email='JOHN.DOE@test.com', password='x')])

    @override_settings(SITE_URL='https://site.test')
    def test_reset_finds_account_by_any_case(self):
        make_user('john.doe@test.com')
        resp = APIClient().post(RESET_URL, {'email': 'John.DOE@test.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_lockout_counter_is_shared_between_cases(self):
        from . import lockout
        self.assertEqual(lockout._fail_key('A@Test.com'), lockout._fail_key('a@test.com'))


class EmailMigrationTests(CleanCacheTestCase):
    """D2: миграция данных останавливается на дублях и выводит список, иначе приводит к нижнему регистру."""

    def _migration(self):
        return importlib.import_module('users.migrations.0020_email_lowercase_unique')

    def test_duplicates_stop_migration_with_list(self):
        fake_user = mock.Mock()
        fake_user.objects.order_by.return_value.values_list.return_value = [
            (1, 'Dup@test.com'), (2, 'dup@test.com'), (3, 'solo@test.com'),
        ]
        fake_apps = mock.Mock()
        fake_apps.get_model.return_value = fake_user
        with self.assertRaisesMessage(RuntimeError, 'dup@test.com: id=1 (Dup@test.com), id=2 (dup@test.com)'):
            self._migration().lowercase_emails(fake_apps, None)
        fake_user.objects.filter.assert_not_called()  # ничего не сливали и не меняли

    def test_without_duplicates_lowercases_rows(self):
        user = make_user('a@test.com')
        User.objects.filter(pk=user.pk).update(email='A@Test.com')
        self._migration().lowercase_emails(apps, None)
        user.refresh_from_db()
        self.assertEqual(user.email, 'a@test.com')


@override_settings(CAPTCHA_PROVIDER='off')
class RegisterValidationTests(CleanCacheTestCase):
    """D3, D7."""

    def test_password_equal_to_email_is_400(self):
        email = 'longpassword@test.com'
        resp = APIClient().post(
            REGISTER_URL, {**_REG, 'email': email, 'password': email, 'password2': email}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', resp.json())

    def test_password_equal_to_first_name_is_400(self):
        name = 'Oleksandrovych'
        resp = APIClient().post(
            REGISTER_URL, {**_REG, 'first_name': name, 'password': name, 'password2': name}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bad_phone_is_400(self):
        resp = APIClient().post(REGISTER_URL, {**_REG, 'phone': 'abc'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('phone', resp.json())

    def test_good_phone_is_201_and_saved(self):
        resp = APIClient().post(REGISTER_URL, {**_REG, 'phone': '+380991234567'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(email='fresh@test.com').phone, '+380991234567')

    def test_empty_phone_is_201(self):
        resp = APIClient().post(REGISTER_URL, {**_REG, 'phone': ''}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


@override_settings(CAPTCHA_PROVIDER='off', SITE_URL='https://site.test')
class EmailMailLimitTests(CleanCacheTestCase):
    """D4: лимит писем на один адрес, ответ нейтральный (не 429)."""

    def _reset(self, email, ip):
        return APIClient(REMOTE_ADDR=ip).post(RESET_URL, {'email': email}, format='json')

    def test_fourth_reset_for_one_address_sends_no_letter_but_same_200(self):
        make_user('owner@test.com')
        responses = [self._reset('owner@test.com', f'10.0.0.{i}') for i in range(1, 5)]
        self.assertEqual([r.status_code for r in responses], [200, 200, 200, 200])
        self.assertEqual(len({str(r.json()) for r in responses}), 1)
        self.assertEqual(len(mail.outbox), 3)

    def test_limit_is_per_address_and_case_insensitive(self):
        make_user('owner@test.com')
        make_user('other@test.com')
        for i in range(1, 4):
            self._reset('Owner@Test.com', f'10.0.1.{i}')
        self._reset('owner@test.com', '10.0.1.9')
        self.assertEqual(len(mail.outbox), 3)
        self._reset('other@test.com', '10.0.1.10')
        self.assertEqual(len(mail.outbox), 4)

    def test_unknown_address_consumes_slots_too(self):
        # слот занимается и для несуществующего адреса: по поведению аккаунт не отличить
        for i in range(1, 4):
            self._reset('ghost@test.com', f'10.0.2.{i}')
        make_user('ghost@test.com')
        self._reset('ghost@test.com', '10.0.2.9')
        self.assertEqual(len(mail.outbox), 0)

    def test_already_registered_letter_limited_and_response_same(self):
        make_user('john.doe@test.com')
        statuses = []
        for i in range(1, 5):
            client = APIClient(REMOTE_ADDR=f'10.0.3.{i}')
            statuses.append(
                client.post(REGISTER_URL, {**_REG, 'email': 'john.doe@test.com'}, format='json').status_code)
        self.assertEqual(statuses, [201, 201, 201, 201])
        self.assertEqual(len(mail.outbox), 3)

    def test_rate_comes_from_settings(self):
        make_user('owner@test.com')
        with mock.patch.dict(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], {'password_reset_email': '1/hour'}):
            self._reset('owner@test.com', '10.0.4.1')
            self._reset('owner@test.com', '10.0.4.2')
        self.assertEqual(len(mail.outbox), 1)


class AdminPrivilegeFieldsTests(CleanCacheTestCase):
    """D6: staff без superuser не правит права."""

    def setUp(self):
        super().setUp()
        self.staff = make_user('hr@test.com', is_staff=True)
        self.staff.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='users', codename__in=('change_customuser', 'view_customuser')))
        self.target = make_user('target@test.com')
        self.url = reverse('admin:users_customuser_change', args=[self.target.pk])

    def _post(self, **extra):
        data = {'email': 'target@test.com', 'first_name': 'Ivan', 'last_name': '', 'phone': '',
                'is_active': 'on', 'is_email_verified': 'on', 'last_login_0': '', 'last_login_1': '', **extra}
        return self.client.post(self.url, data)

    def test_privilege_fields_readonly_for_staff_editable_for_superuser(self):
        from django.contrib.admin.sites import site
        model_admin = site._registry[User]
        names = ('is_superuser', 'is_staff', 'groups', 'user_permissions')
        readonly = model_admin.get_readonly_fields(mock.Mock(user=self.staff), self.target)
        for name in names:
            self.assertIn(name, readonly)
        root = make_user('root@test.com', is_staff=True, is_superuser=True)
        readonly = model_admin.get_readonly_fields(mock.Mock(user=root), self.target)
        for name in names:
            self.assertNotIn(name, readonly)

    def test_post_with_forged_privileges_changes_nothing(self):
        group = Group.objects.create(name='Forge')
        self.client.force_login(self.staff)
        resp = self._post(is_superuser='on', is_staff='on', groups=[group.pk])
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, 'Ivan')  # форма сохранилась, права - нет
        self.assertFalse(self.target.is_superuser)
        self.assertFalse(self.target.is_staff)
        self.assertEqual(self.target.groups.count(), 0)

    def test_superuser_can_change_privileges(self):
        self.client.force_login(make_user('root@test.com', is_staff=True, is_superuser=True))
        resp = self._post(is_staff='on')
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)


_APPLY = {
    'company_name': 'ТОВ Авто', 'full_name': 'Іван Іванов', 'contact_phone': '+380991234567',
    'documents': '', 'agreed_to_processing': True, 'confirmed_age_18': True,
}


class DealerPendingUniqueTests(CleanCacheTestCase):
    """D8."""

    def test_db_rejects_second_pending(self):
        user = make_user()
        DealerApplication.objects.create(user=user, company_name='A', full_name='B', contact_phone='1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            DealerApplication.objects.create(user=user, company_name='C', full_name='D', contact_phone='2')

    def test_second_after_rejection_is_allowed_in_db(self):
        user = make_user()
        DealerApplication.objects.create(
            user=user, company_name='A', full_name='B', contact_phone='1', status='rejected')
        DealerApplication.objects.create(user=user, company_name='C', full_name='D', contact_phone='2')
        self.assertEqual(DealerApplication.objects.filter(user=user).count(), 2)

    def test_service_maps_integrity_error_to_duplicate_error(self):
        # проверка exists() прошла (гонка), вставку отклонил constraint
        user = make_user()
        DealerApplication.objects.create(user=user, company_name='A', full_name='B', contact_phone='1')
        with mock.patch('users.services.DealerApplication.objects.filter') as flt:
            flt.return_value.exists.return_value = False
            with self.assertRaises(DuplicatePendingError):
                apply_for_dealer(user, 'C', 'D', '2')
        self.assertEqual(DealerApplication.objects.filter(user=user).count(), 1)

    @override_settings(CAPTCHA_PROVIDER='off')
    def test_api_race_returns_409(self):
        user = make_user()
        DealerApplication.objects.create(user=user, company_name='A', full_name='B', contact_phone='1')
        client = APIClient()
        client.force_authenticate(user)
        with mock.patch('users.services.DealerApplication.objects.filter') as flt:
            flt.return_value.exists.return_value = False
            resp = client.post(APPLY_URL, _APPLY, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)


class DealerPendingConcurrencyTests(TransactionTestCase):
    """D8: настоящая параллельность - только PostgreSQL (SQLite не даёт конкурентной записи)."""

    @unittest.skipUnless(connection.vendor == 'postgresql', 'нужен PostgreSQL')
    def test_parallel_applications_give_one_pending(self):
        user = make_user('race@test.com')
        barrier = threading.Barrier(2)
        results = []

        def worker():
            try:
                barrier.wait()
                apply_for_dealer(user, 'ТОВ', 'Іван', '+380991234567')
                results.append('ok')
            except DuplicatePendingError:
                results.append('dup')
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ['dup', 'ok'])
        self.assertEqual(DealerApplication.objects.filter(user=user, status='pending').count(), 1)


class PendingMigrationCheckTests(CleanCacheTestCase):
    """D8: миграция 0021 останавливается на дублях pending и не сливает их."""

    def _fake_apps(self, rows):
        model = mock.Mock()
        model.objects.filter.return_value.order_by.return_value.values_list.return_value = rows
        fake_apps = mock.Mock()
        fake_apps.get_model.return_value = model
        return fake_apps

    def _check(self, fake_apps):
        module = importlib.import_module('users.migrations.0021_dealerapplication_pending_unique')
        module.check_pending_duplicates(fake_apps, None)

    def test_duplicates_stop_migration_with_list(self):
        with self.assertRaisesMessage(RuntimeError, 'user_id=7: заявки id=[1, 3]'):
            self._check(self._fake_apps([(1, 7), (2, 8), (3, 7)]))

    def test_no_duplicates_passes(self):
        self._check(self._fake_apps([(1, 7), (2, 8)]))

    def test_real_data_without_duplicates_passes(self):
        DealerApplication.objects.create(user=make_user(), company_name='A', full_name='B', contact_phone='1')
        self._check(apps)


class AdminStaffProtectionTests(CleanCacheTestCase):
    """Staff с change_customuser не правит других сотрудников и superuser."""

    def setUp(self):
        super().setUp()
        self.staff = make_user('hr@test.com', is_staff=True)
        self.staff.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='users', codename__in=('change_customuser', 'view_customuser')))
        self.root = make_user('root@test.com', is_staff=True, is_superuser=True)
        self.plain = make_user('plain@test.com')

    def test_staff_cannot_change_superuser_password(self):
        self.client.force_login(self.staff)
        url = reverse('admin:auth_user_password_change', args=[self.root.pk])
        resp = self.client.post(url, {'password1': NEW_PASSWORD, 'password2': NEW_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.root.refresh_from_db()
        self.assertTrue(self.root.check_password(TEST_PASSWORD))

    def test_staff_cannot_change_superuser_email(self):
        self.client.force_login(self.staff)
        url = reverse('admin:users_customuser_change', args=[self.root.pk])
        resp = self.client.post(url, {'email': 'evil@test.com', 'is_active': 'on'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.root.refresh_from_db()
        self.assertEqual(self.root.email, 'root@test.com')

    def test_staff_can_still_change_password_of_plain_user(self):
        self.client.force_login(self.staff)
        url = reverse('admin:auth_user_password_change', args=[self.plain.pk])
        resp = self.client.post(url, {'password1': NEW_PASSWORD, 'password2': NEW_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)

    def test_superuser_can_change_superuser_password(self):
        other = make_user('root2@test.com', is_staff=True, is_superuser=True)
        self.client.force_login(self.root)
        url = reverse('admin:auth_user_password_change', args=[other.pk])
        resp = self.client.post(url, {'password1': NEW_PASSWORD, 'password2': NEW_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        other.refresh_from_db()
        self.assertTrue(other.check_password(NEW_PASSWORD))


class UnusablePasswordAndAsyncCheckTests(CleanCacheTestCase):
    def test_set_unusable_password_revokes_sessions(self):
        user = make_user('u@test.com')
        _, access = _tokens(user)
        user.set_unusable_password()
        user.save()
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(User.objects.get(pk=user.pk).session_version, 1)

    def test_admin_form_with_unusable_password_revokes_sessions(self):
        user = make_user('u@test.com')
        _, access = _tokens(user)
        self.client.force_login(make_user('boss@test.com', is_staff=True, is_superuser=True))
        url = reverse('admin:auth_user_password_change', args=[user.pk])
        resp = self.client.post(url, {'usable_password': 'false', 'unset-password': '1'})
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertFalse(User.objects.get(pk=user.pk).has_usable_password())
        self.assertEqual(_bearer(access).get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_anonymize_shifts_session_version_exactly_once(self):
        from .services import anonymize_user
        user = make_user('gone@test.com')
        anonymize_user(user)
        self.assertEqual(User.objects.get(pk=user.pk).session_version, 1)

    def test_acheck_password_hash_upgrade_does_not_revoke_sessions(self):
        from asgiref.sync import async_to_sync
        with override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher']):
            legacy = make_user('legacy@test.com')
        self.assertTrue(async_to_sync(legacy.acheck_password)(TEST_PASSWORD))
        legacy.refresh_from_db()
        self.assertTrue(legacy.password.startswith('pbkdf2_sha256$'))  # апгрейд был
        self.assertEqual(legacy.session_version, 0)


@override_settings(CAPTCHA_PROVIDER='off', SITE_URL='https://site.test')
class SeparateCountersTests(CleanCacheTestCase):
    def test_register_on_existing_address_does_not_eat_reset_limit(self):
        make_user('john.doe@test.com')
        for i in range(1, 4):
            APIClient(REMOTE_ADDR=f'10.0.5.{i}').post(
                REGISTER_URL, {**_REG, 'email': 'john.doe@test.com'}, format='json')
        self.assertEqual(len(mail.outbox), 3)  # письма «вже є акаунт»
        mail.outbox.clear()
        resp = APIClient(REMOTE_ADDR='10.0.5.9').post(RESET_URL, {'email': 'john.doe@test.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
