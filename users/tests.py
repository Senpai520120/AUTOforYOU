"""
Тесты верификации дилеров: DealerApplication, B2B-гейтинг, wholesale-фильтрация.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from tests.base import CleanCacheTestCase
from tests.factories import (
    TEST_PASSWORD,
    auth_client,
    make_admin_role,
    make_broker,
    make_dealer,
    make_listing,
    make_local_listing,
    make_moderator,
    make_region_city,
    make_staff,
    make_user,
    make_vehicle,
)

from .models import ConsentDocument, ConsentMethod, ConsentRecord, DealerApplication, ImmutableError
from .services import DuplicatePendingError, apply_for_dealer, approve_application, reject_application

User = get_user_model()

APPLY_URL = '/api/v1/dealers/apply/'
STATUS_URL = '/api/v1/dealers/application/'


_APPLY_DATA = {
    'company_name': 'ТОВ Авто',
    'full_name': 'Іван Іванов',
    'contact_phone': '+380991234567',
    'documents': 'https://drive.google.com/doc123',
    'agreed_to_processing': True,
    'confirmed_age_18': True,
}


# ── Менеджер и строковые представления моделей ────────────────────────────────

class TestUserModel(APITestCase):
    def test_create_user_without_email_raises(self):
        with self.assertRaisesMessage(ValueError, 'Email обязателен'):
            User.objects.create_user(email='')

    def test_create_superuser_sets_admin_flags(self):
        admin = User.objects.create_superuser(email='root@test.com', password='x-Pass-12345')
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, 'admin')

    def test_str_is_email(self):
        self.assertEqual(str(make_user('s@test.com')), 's@test.com')

    def test_dealer_application_str_contains_company_and_email(self):
        user = make_user('d@test.com')
        app = apply_for_dealer(user, _APPLY_DATA['company_name'], 'Іван', '+380991234567')
        self.assertIn('d@test.com', str(app))
        self.assertIn(_APPLY_DATA['company_name'], str(app))


# ── Сервисный слой ────────────────────────────────────────────────────────────

class TestDealerApplicationService(APITestCase):

    def setUp(self):
        self.user = make_user()
        self.admin = make_staff(superuser=True)

    def test_apply_creates_pending(self):
        app = apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380991234567')
        self.assertEqual(app.status, DealerApplication.Status.PENDING)
        self.assertEqual(app.user, self.user)

    def test_duplicate_pending_raises(self):
        apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380')
        with self.assertRaises(DuplicatePendingError):
            apply_for_dealer(self.user, 'ТОВ Авто 2', 'Іван', '+380')

    def test_second_apply_allowed_after_rejection(self):
        app = apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380')
        reject_application(app, self.admin)
        app2 = apply_for_dealer(self.user, 'ТОВ Авто 2', 'Іван', '+380')
        self.assertEqual(app2.status, DealerApplication.Status.PENDING)

    def test_approve_sets_is_verified_dealer(self):
        app = apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380')
        approve_application(app, self.admin)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_verified_dealer)
        self.assertEqual(self.user.role, 'dealer')

    def test_approve_sets_reviewed_by_and_at(self):
        app = apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380')
        approve_application(app, self.admin)
        app.refresh_from_db()
        self.assertEqual(app.status, DealerApplication.Status.APPROVED)
        self.assertEqual(app.reviewed_by, self.admin)
        self.assertIsNotNone(app.reviewed_at)

    def test_reject_saves_notes(self):
        app = apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380')
        reject_application(app, self.admin, notes='Недостаточно документов')
        app.refresh_from_db()
        self.assertEqual(app.status, DealerApplication.Status.REJECTED)
        self.assertEqual(app.review_notes, 'Недостаточно документов')
        self.assertFalse(self.user.is_verified_dealer)


# ── API эндпоинты ─────────────────────────────────────────────────────────────

class TestDealerApplyAPI(APITestCase):

    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(self.user)

    def test_apply_returns_201(self):
        resp = self.client.post(APPLY_URL, _APPLY_DATA)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['status'], 'pending')

    def test_duplicate_pending_returns_409(self):
        self.client.post(APPLY_URL, _APPLY_DATA)
        resp = self.client.post(APPLY_URL, _APPLY_DATA)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_unauthenticated_returns_401(self):
        self.client.logout()
        resp = self.client.post(APPLY_URL, _APPLY_DATA)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_fields_returns_400(self):
        resp = self.client.post(APPLY_URL, {'company_name': 'only'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class TestDealerApplicationStatusAPI(APITestCase):

    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(self.user)

    def test_no_application_returns_404(self):
        resp = self.client.get(STATUS_URL)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_application_status(self):
        apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380')
        resp = self.client.get(STATUS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], 'pending')


# ── B2B гейтинг ──────────────────────────────────────────────────────────────

class TestB2BGating(APITestCase):

    B2B_URL = '/api/v1/b2b/board/'

    def test_unauthenticated_gets_401(self):
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_gets_403(self):
        user = make_user('plain@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_verified_dealer_gets_200(self):
        user = make_dealer('dealer@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_gets_200(self):
        admin = make_staff('admin2@test.com', superuser=True)
        self.client.force_authenticate(admin)
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ── Wholesale-фильтрация в каталоге ──────────────────────────────────────────

class TestWholesaleCatalogFilter(APITestCase):

    LISTINGS_URL = '/api/v1/listings/'

    def setUp(self):
        self.seller = make_user('seller@test.com')
        self.retail = make_listing(make_vehicle(), self.seller, channel='retail')
        self.wholesale = make_listing(make_vehicle(), self.seller, channel='wholesale')

    def test_anonymous_sees_only_retail(self):
        resp = self.client.get(self.LISTINGS_URL)
        ids = [r['id'] for r in resp.data['results']] if 'results' in resp.data else [r['id'] for r in resp.data]
        self.assertIn(self.retail.id, ids)
        self.assertNotIn(self.wholesale.id, ids)

    def test_regular_user_sees_only_retail(self):
        user = make_user('buyer@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self.LISTINGS_URL)
        ids = [r['id'] for r in resp.data['results']] if 'results' in resp.data else [r['id'] for r in resp.data]
        self.assertIn(self.retail.id, ids)
        self.assertNotIn(self.wholesale.id, ids)

    def test_verified_dealer_sees_wholesale(self):
        dealer = make_dealer('dea@test.com')
        self.client.force_authenticate(dealer)
        resp = self.client.get(self.LISTINGS_URL)
        ids = [r['id'] for r in resp.data['results']] if 'results' in resp.data else [r['id'] for r in resp.data]
        self.assertIn(self.retail.id, ids)
        self.assertIn(self.wholesale.id, ids)


# ── JWT Blacklist (logout) ────────────────────────────────────────────────────

LOGOUT_URL = '/api/v1/auth/token/logout/'
TOKEN_REFRESH_URL = '/api/v1/auth/token/refresh/'
TOKEN_URL = '/api/v1/auth/token/'


class TestJWTLogout(APITestCase):

    def setUp(self):
        self.user = make_user('jwt@test.com')
        from rest_framework_simplejwt.tokens import RefreshToken
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)
        self.refresh_str = str(self.refresh)

    def test_logout_returns_ok(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')
        resp = self.client.post(LOGOUT_URL, {'refresh': self.refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['ok'])

    def test_logout_blacklists_refresh(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')
        self.client.post(LOGOUT_URL, {'refresh': self.refresh_str}, format='json')
        # Отозванный refresh не позволяет получить новый access
        resp = self.client.post(TOKEN_REFRESH_URL, {'refresh': self.refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_without_access_still_revokes(self):
        # Задача 1.3: logout — AllowAny, чтобы выйти можно было и с протухшим access.
        resp = self.client.post(LOGOUT_URL, {'refresh': self.refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post(TOKEN_REFRESH_URL, {'refresh': self.refresh_str}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_missing_refresh_returns_400(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')
        resp = self.client.post(LOGOUT_URL, {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ── Реєстрація: згода з умовами ──────────────────────────────────────────────

REGISTER_URL = '/api/v1/auth/register/'

_REG_BASE = {
    'email': 'newuser@test.com',
    'password': 'StrongPass123!',
    'password2': 'StrongPass123!',
    'role': 'buyer',
}


class TestRegistrationConsent(APITestCase):

    def test_register_without_consent_returns_400(self):
        resp = self.client.post(REGISTER_URL, {**_REG_BASE, 'agreed_to_terms': False, 'confirmed_age_18': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agreed_to_terms', resp.data)

    def test_register_without_consent_field_returns_400(self):
        resp = self.client.post(REGISTER_URL, _REG_BASE, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_with_consent_sets_agreed_to_terms_at(self):
        resp = self.client.post(REGISTER_URL, {**_REG_BASE, 'agreed_to_terms': True, 'confirmed_age_18': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=_REG_BASE['email'])
        self.assertIsNotNone(user.agreed_to_terms_at)

    def test_register_with_consent_returns_201(self):
        resp = self.client.post(REGISTER_URL, {**_REG_BASE, 'agreed_to_terms': True, 'confirmed_age_18': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


# ── Эскалация привилегий через поле role ──────────────────────────────────────

PROFILE_URL = '/api/v1/auth/profile/'
B2B_URL = '/api/v1/b2b/board/'


class TestRoleIsNotSelfAssignable(APITestCase):
    """
    role пользователь указывает сам при регистрации, поэтому она не должна
    давать привилегий. Раньше значение 'admin' открывало B2B-доску и чтение
    чужих переписок по импортным листингам.
    """

    def setUp(self):
        super().setUp()
        cache.clear()  # throttle register (5/hour) копится в LocMem-кэше между тестами

    def test_register_ignores_role_admin(self):
        # Решение 1.2: поле role в запросе молча игнорируется (не 400): пользователь всегда buyer.
        resp = self.client.post(
            REGISTER_URL,
            {**_REG_BASE, 'role': 'admin', 'agreed_to_terms': True, 'confirmed_age_18': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=_REG_BASE['email'])
        self.assertEqual(user.role, 'buyer')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_register_ignores_role_dealer(self):
        # Раньше самовыбор dealer был разрешён; теперь dealer ставит только approve_application.
        resp = self.client.post(
            REGISTER_URL,
            {**_REG_BASE, 'role': 'dealer', 'agreed_to_terms': True, 'confirmed_age_18': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=_REG_BASE['email'])
        self.assertEqual(user.role, 'buyer')
        self.assertFalse(user.is_verified_dealer)
        self.assertFalse(user.is_staff)

    def test_register_ignores_role_broker(self):
        resp = self.client.post(
            REGISTER_URL,
            {**_REG_BASE, 'role': 'broker', 'agreed_to_terms': True, 'confirmed_age_18': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(email=_REG_BASE['email']).role, 'buyer')

    def test_register_ignores_role_moderator(self):
        resp = self.client.post(
            REGISTER_URL,
            {**_REG_BASE, 'role': 'moderator', 'agreed_to_terms': True, 'confirmed_age_18': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(email=_REG_BASE['email']).role, 'buyer')

    def test_patch_profile_cannot_change_role(self):
        user = make_user('selfpromote@test.com')
        self.client.force_authenticate(user=user)

        resp = self.client.patch(PROFILE_URL, {'role': 'admin'}, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.role, 'buyer')

    def test_role_admin_without_is_staff_has_no_b2b_access(self):
        # Роль выставлена напрямую в БД — эмулируем состояние, которое
        # раньше можно было получить через API.
        user = make_user('fakeadmin@test.com', role='admin')
        self.assertFalse(user.is_staff)
        self.client.force_authenticate(user=user)

        resp = self.client.get(B2B_URL)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_real_admin_has_b2b_access(self):
        self.client.force_authenticate(user=make_staff('realadmin@test.com', superuser=True))

        resp = self.client.get(B2B_URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_profile_exposes_is_staff(self):
        # Фронт показывает админские разделы по тому же признаку, по которому
        # их проверяет бэкенд. Раньше is_staff в профиль не отдавался, и шапка
        # ориентировалась на role — пользователь видел ссылку на B2B и получал 403.
        self.client.force_authenticate(user=make_staff('staffflag@test.com', superuser=True))
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['is_staff'])

    def test_profile_exposes_is_admin_role(self):
        self.client.force_authenticate(user=make_admin_role('adminflag@test.com'))
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIs(resp.data['is_admin_role'], True)

    def test_profile_is_admin_role_false_for_broker_with_is_staff(self):
        self.client.force_authenticate(user=make_broker('brokerflag@test.com'))
        resp = self.client.get(PROFILE_URL)
        self.assertIs(resp.data['is_staff'], True)
        self.assertIs(resp.data['is_admin_role'], False)

    def test_patch_profile_cannot_set_is_admin_role(self):
        user = make_user('escalate_adminrole@test.com')
        self.client.force_authenticate(user=user)
        resp = self.client.patch(PROFILE_URL, {'is_admin_role': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIs(resp.data['is_admin_role'], False)

    def test_profile_is_staff_false_for_regular_user(self):
        self.client.force_authenticate(user=make_user('plain@test.com'))
        resp = self.client.get(PROFILE_URL)
        self.assertFalse(resp.data['is_staff'])

    def test_patch_profile_cannot_grant_is_staff(self):
        user = make_user('escalate_staff@test.com')
        self.client.force_authenticate(user=user)

        self.client.patch(PROFILE_URL, {'is_staff': True}, format='json')

        user.refresh_from_db()
        self.assertFalse(user.is_staff)


# ── Согласие на обработку ПД в заявке дилера ──────────────────────────────────

class TestDealerApplicationConsent(APITestCase):

    def test_apply_without_consent_returns_400(self):
        # Чекбокс на фронте согласие показывал, но прямой POST в API проходил
        # мимо него — согласие нигде не фиксировалось и доказать его было нельзя.
        self.client.force_authenticate(user=make_user('noconsent@test.com'))
        payload = {k: v for k, v in _APPLY_DATA.items() if k != 'agreed_to_processing'}

        resp = self.client.post(APPLY_URL, payload, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agreed_to_processing', resp.data)
        self.assertFalse(DealerApplication.objects.exists())

    def test_apply_with_consent_false_returns_400(self):
        self.client.force_authenticate(user=make_user('falseconsent@test.com'))

        resp = self.client.post(
            APPLY_URL, {**_APPLY_DATA, 'agreed_to_processing': False}, format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DealerApplication.objects.exists())

    def test_apply_records_consent_timestamp(self):
        self.client.force_authenticate(user=make_user('withconsent@test.com'))

        resp = self.client.post(APPLY_URL, _APPLY_DATA, format='json')

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        application = DealerApplication.objects.get()
        # Метка времени, а не булев флаг: доказывать нужно и момент тоже.
        self.assertIsNotNone(application.agreed_to_processing_at)
        self.assertIsNotNone(resp.data['agreed_to_processing_at'])


# ── Роли и права (задача 1.2) ─────────────────────────────────────────────────

CONVERSATIONS_URL = '/api/v1/messages/conversations/'
LOCAL_DETAIL = '/api/v1/local/listings/{}/'


class TestRoleHelpers(TestCase):
    def test_role_helpers(self):
        broker = make_user(role='broker')
        moderator = make_user(role='moderator')
        admin = make_admin_role()
        superuser = make_staff(superuser=True)  # role остаётся buyer
        buyer = make_user()
        self.assertTrue(broker.is_broker)
        self.assertFalse(broker.is_admin_role)
        self.assertTrue(moderator.is_moderator)
        self.assertFalse(moderator.is_broker)
        self.assertTrue(admin.is_admin_role)
        self.assertTrue(superuser.is_admin_role)
        self.assertFalse(buyer.is_admin_role)
        self.assertFalse(buyer.is_broker)

    def test_brokers_and_admins_manager(self):
        broker = make_user(role='broker')
        admin = make_admin_role()
        make_user(role='moderator')
        make_user(role='dealer')
        make_staff()  # is_staff без роли
        self.assertEqual(set(User.objects.brokers_and_admins()), {broker, admin})


class TestImportedConversationsVisibility(TestCase):
    """06-S9: импортные диалоги видят только broker и admin."""

    def setUp(self):
        from messaging.services import get_or_create_conversation
        self.broker = make_broker()
        self.admin = make_admin_role()
        self.buyer = make_user()
        self.other = make_user()
        self.dealer = make_dealer()
        self.staff_only = make_staff()
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification'):
            self.conv, _, _ = get_or_create_conversation(
                self.buyer, 'imported', listing.pk, 'Цікавить авто',
            )

    def _ids(self, user):
        resp = auth_client(user).get(CONVERSATIONS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [c['id'] for c in resp.data]

    def test_broker_sees_imported_conversation(self):
        self.assertEqual(self._ids(self.broker), [self.conv.pk])

    def test_admin_sees_imported_conversation(self):
        self.assertEqual(self._ids(self.admin), [self.conv.pk])

    def test_buyer_does_not_see_foreign_imported_conversation(self):
        self.assertEqual(self._ids(self.other), [])

    def test_dealer_does_not_see_foreign_imported_conversation(self):
        self.assertEqual(self._ids(self.dealer), [])

    def test_is_staff_without_role_does_not_see(self):
        self.assertEqual(self._ids(self.staff_only), [])

    def test_buyer_cannot_open_foreign_imported_conversation(self):
        resp = auth_client(self.other).get(f'{CONVERSATIONS_URL}{self.conv.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_dealer_cannot_open_foreign_imported_conversation(self):
        resp = auth_client(self.dealer).get(f'{CONVERSATIONS_URL}{self.conv.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_is_staff_without_role_cannot_open(self):
        resp = auth_client(self.staff_only).get(f'{CONVERSATIONS_URL}{self.conv.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_broker_can_open(self):
        resp = auth_client(self.broker).get(f'{CONVERSATIONS_URL}{self.conv.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_anonymous_gets_401(self):
        resp = self.client.get(CONVERSATIONS_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class TestImportedConversationNotifications(TestCase):
    def test_import_conversation_notifies_only_brokers_and_admins(self):
        from messaging.services import get_or_create_conversation
        broker = make_broker()
        admin = make_admin_role()
        make_staff()  # is_staff без роли
        make_moderator()
        make_dealer()
        buyer = make_user()
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification') as task:
            get_or_create_conversation(buyer, 'imported', listing.pk, 'Привіт')
        recipients = [c.args[0] for c in task.delay.call_args_list]
        self.assertCountEqual(recipients, [broker.pk, admin.pk])

    def test_participant_is_first_broker_then_admin(self):
        from messaging.services import get_or_create_conversation
        admin = make_admin_role()
        broker = make_broker()
        buyer = make_user()
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification'):
            conv, _, _ = get_or_create_conversation(buyer, 'imported', listing.pk, 'Привіт')
        self.assertEqual(set(conv.participants.all()), {buyer, broker})
        broker.delete()
        listing2 = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification'):
            conv2, _, _ = get_or_create_conversation(buyer, 'imported', listing2.pk, 'Привіт')
        self.assertEqual(set(conv2.participants.all()), {buyer, admin})


class TestDealerApplicationAdmin(TestCase):
    def setUp(self):
        self.admin = make_staff(superuser=True)
        self.user = make_user()
        self.app = apply_for_dealer(self.user, 'ТОВ Авто', 'Іван', '+380991234567')
        self.client.force_login(self.admin)

    def test_approve_via_admin_form_is_not_possible(self):
        from django.contrib import admin as dj_admin
        model_admin = dj_admin.site._registry[DealerApplication]
        self.assertIn('status', model_admin.readonly_fields)
        self.assertIn('agreed_to_processing_at', model_admin.readonly_fields)
        # POST формы со status=approved статус не меняет
        url = f'/admin/users/dealerapplication/{self.app.pk}/change/'
        self.client.post(url, {
            'user': self.user.pk, 'company_name': 'ТОВ Авто', 'full_name': 'Іван',
            'contact_phone': '+380', 'documents': '', 'status': 'approved',
            'review_notes': '',
        })
        self.app.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.app.status, DealerApplication.Status.PENDING)
        self.assertFalse(self.user.is_verified_dealer)

    def test_approve_action_sets_dealer(self):
        resp = self.client.post('/admin/users/dealerapplication/', {
            'action': '_approve', '_selected_action': [self.app.pk],
        })
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.app.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.app.status, DealerApplication.Status.APPROVED)
        self.assertTrue(self.user.is_verified_dealer)
        self.assertEqual(self.user.role, 'dealer')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_approve_is_atomic(self):
        with mock.patch('users.services._notify', side_effect=RuntimeError('boom')):
            with self.assertRaisesMessage(RuntimeError, 'boom'):
                approve_application(self.app, self.admin)
        self.app.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.app.status, DealerApplication.Status.PENDING)
        self.assertFalse(self.user.is_verified_dealer)


class TestAssignRoleActions(TestCase):
    def setUp(self):
        self.admin = make_staff(superuser=True)
        self.client.force_login(self.admin)

    def _run(self, action, user):
        resp = self.client.post('/admin/users/customuser/', {
            'action': action, '_selected_action': [user.pk],
        })
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        user.refresh_from_db()

    def test_assign_moderator_action(self):
        user = make_user()
        self._run('assign_moderator', user)
        self.assertEqual(user.role, 'moderator')
        self.assertTrue(user.is_staff)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['Модератори'])
        self.assertTrue(user.has_perm('local_listings.moderate_locallisting'))
        # повторный запуск идемпотентен
        self._run('assign_moderator', user)
        self.assertEqual(user.groups.count(), 1)
        self.assertEqual(user.role, 'moderator')

    def test_revoke_moderator_action(self):
        user = make_moderator()
        self._run('revoke_moderator', user)
        self.assertEqual(user.role, 'buyer')
        self.assertFalse(user.is_staff)
        self.assertEqual(user.groups.count(), 0)
        self._run('revoke_moderator', user)
        self.assertEqual(user.role, 'buyer')

    def test_assign_and_revoke_broker_action(self):
        user = make_user()
        self._run('assign_broker', user)
        self.assertEqual(user.role, 'broker')
        self.assertTrue(user.is_staff)
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['Брокери'])
        self._run('assign_broker', user)
        self.assertEqual(user.groups.count(), 1)
        self._run('revoke_broker', user)
        self.assertEqual(user.role, 'buyer')
        self.assertFalse(user.is_staff)

    def test_revoke_returns_verified_dealer_to_dealer(self):
        user = make_user(role='moderator', is_verified_dealer=True)
        self._run('revoke_moderator', user)
        self.assertEqual(user.role, 'dealer')


class TestRoleGroupsMigration(TestCase):
    def test_groups_and_permissions(self):
        names = {
            g.name: set(g.permissions.values_list('codename', flat=True))
            for g in Group.objects.all()
        }
        self.assertIn('moderate_locallisting', names['Модератори'])
        self.assertIn('moderate_locallisting', names['Адміністратори'])
        self.assertIn('change_locallisting', names['Модератори'])
        self.assertEqual(
            names['Брокери'],
            {'view_calculation', 'view_lead', 'change_lead', 'view_leadstatuschange'},
        )
        self.assertFalse({c for c in names['Модератори'] if c.endswith('lead')})


class TestModerationRequiresPermission(TestCase):
    def setUp(self):
        self.owner = make_user()
        self.listing = make_local_listing(self.owner, status='pending')
        self.url = LOCAL_DETAIL.format(self.listing.pk)

    def test_regular_user_does_not_see_foreign_pending(self):
        resp = auth_client(make_user()).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_moderator_sees_pending(self):
        resp = auth_client(make_moderator()).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_broker_without_permission_does_not_see_pending(self):
        resp = auth_client(make_broker()).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_is_staff_without_permission_does_not_see_pending(self):
        resp = auth_client(make_staff()).get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_action_without_permission_changes_nothing(self):
        user = make_staff()
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='local_listings',
            codename__in=['view_locallisting', 'change_locallisting'],
        ))
        self.client.force_login(user)
        resp = self.client.post('/admin/local_listings/locallisting/', {
            'action': 'approve_listings', '_selected_action': [self.listing.pk],
        })
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'pending')

    def test_admin_action_with_permission_approves(self):
        self.client.force_login(make_moderator())
        resp = self.client.post('/admin/local_listings/locallisting/', {
            'action': 'approve_listings', '_selected_action': [self.listing.pk],
        })
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'active')


class TestModeratorBoundaries(TestCase):
    """Q10: модератор не видит платежи, тарифы, Calculation, пользователей и чужие импортные диалоги.

    SiteSettings (1.12): модератор и брокер не открывают настройки сайта. Lead (2.1) ещё не существует.
    """

    def setUp(self):
        self.moderator = make_moderator()
        self.client.force_login(self.moderator)

    def test_payments_forbidden(self):
        resp = self.client.get('/admin/payments/payment/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_pricing_calculation_forbidden(self):
        resp = self.client.get('/admin/pricing/calculation/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_pricing_tariffs_forbidden(self):
        resp = self.client.get('/admin/pricing/exchangerate/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_users_forbidden(self):
        resp = self.client.get('/admin/users/customuser/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderation_queue_visible(self):
        resp = self.client.get('/admin/local_listings/locallisting/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_group_has_no_forbidden_permissions(self):
        perms = Group.objects.get(name='Модератори').permissions.values_list(
            'content_type__app_label', flat=True,
        )
        self.assertEqual(set(perms) & {'payments', 'pricing', 'users', 'site_settings'}, set())

    def test_site_settings_change_get_forbidden(self):
        from django.urls import reverse
        url = reverse('admin:site_settings_sitesettings_change', args=[1])
        for user in (self.moderator, make_broker()):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_site_settings_change_post_forbidden(self):
        from django.urls import reverse
        url = reverse('admin:site_settings_sitesettings_change', args=[1])
        for user in (self.moderator, make_broker()):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url, {'phone': '+380500000000'}).status_code,
                             status.HTTP_403_FORBIDDEN)

    def test_cannot_open_foreign_imported_conversation(self):
        from messaging.services import get_or_create_conversation
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification'):
            conv, _, _ = get_or_create_conversation(make_user(), 'imported', listing.pk, 'Hi')
        resp = auth_client(self.moderator).get(f'{CONVERSATIONS_URL}{conv.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TestSellerTypeDealer(TestCase):
    """05-Q22: seller_type=dealer только для верифицированного дилера."""

    def _payload(self):
        region, city = make_region_city()
        return dict(
            make='Toyota', model='Camry', year=2020, mileage_km=50000,
            fuel_type='petrol', transmission='auto', body_type='sedan',
            price='500000', currency='UAH', price_type='fixed',
            region=region.pk, city=city.pk, agreed_to_rules=True, seller_type='dealer',
        )

    def test_unverified_user_gets_400(self):
        resp = auth_client(make_user()).post('/api/v1/local/listings/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('seller_type', resp.data)

    def test_verified_dealer_gets_201(self):
        resp = auth_client(make_dealer()).post('/api/v1/local/listings/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


# ── Ревью безопасности 1.2 ────────────────────────────────────────────────────

class TestBareAdminRoleGivesNothing(TestCase):
    """role='admin' без is_staff/is_superuser прав не даёт (самозваный admin)."""

    def setUp(self):
        self.fake = make_user(role='admin')

    def test_is_admin_role_false(self):
        self.assertFalse(self.fake.is_admin_role)

    def test_not_in_brokers_and_admins(self):
        self.assertNotIn(self.fake, User.objects.brokers_and_admins())

    def test_cannot_open_imported_conversation(self):
        from messaging.services import get_or_create_conversation
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification'):
            conv, _, _ = get_or_create_conversation(make_user(), 'imported', listing.pk, 'Hi')
        resp = auth_client(self.fake).get(f'{CONVERSATIONS_URL}{conv.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_not_notified_about_imported_conversation(self):
        from messaging.services import get_or_create_conversation
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification') as task:
            get_or_create_conversation(make_user(), 'imported', listing.pk, 'Hi')
        self.assertNotIn(self.fake.pk, [c.args[0] for c in task.delay.call_args_list])

    def test_deals_listing_buyers_forbidden(self):
        listing = make_local_listing(make_user())
        resp = auth_client(self.fake).get(f'/api/v1/deals/listing-buyers/{listing.pk}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class TestRevokeBrokerReleasesConversations(TestCase):
    def test_former_broker_removed_and_successor_added(self):
        from messaging.services import get_or_create_conversation
        from users.services import revoke_role
        broker = make_broker()
        admin = make_admin_role()
        listing = make_listing(make_vehicle(), make_user())
        with mock.patch('integrations.tasks.send_notification'):
            conv, _, _ = get_or_create_conversation(make_user(), 'imported', listing.pk, 'Hi')
        self.assertTrue(conv.participants.filter(pk=broker.pk).exists())
        revoke_role(broker, 'broker')
        self.assertFalse(conv.participants.filter(pk=broker.pk).exists())
        self.assertTrue(conv.participants.filter(pk=admin.pk).exists())


class TestRoleAdminHardening(TestCase):
    def _viewonly_staff(self):
        from django.contrib.auth.models import Permission
        user = make_staff()
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='users', content_type__model='customuser',
            codename__in=['view_customuser', 'change_customuser'],
        ))
        return user

    def test_non_superuser_cannot_assign_role_via_action(self):
        target = make_user()
        self.client.force_login(self._viewonly_staff())
        self.client.post('/admin/users/customuser/', {
            'action': 'assign_broker', '_selected_action': [target.pk],
        })
        target.refresh_from_db()
        self.assertEqual(target.role, 'buyer')

    def test_staff_without_change_permission_has_no_role_actions(self):
        from django.contrib.auth.models import Permission
        user = make_staff()
        user.user_permissions.add(Permission.objects.get(codename='view_customuser'))
        self.client.force_login(user)
        target = make_user()
        resp = self.client.post('/admin/users/customuser/', {
            'action': 'assign_broker', '_selected_action': [target.pk],
        })
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)  # действие недоступно
        target.refresh_from_db()
        self.assertEqual(target.role, 'buyer')

    def test_role_and_verified_dealer_readonly_in_form(self):
        from django.contrib import admin as dj_admin
        ma = dj_admin.site._registry[User]
        self.assertIn('role', ma.readonly_fields)
        self.assertIn('is_verified_dealer', ma.readonly_fields)

    def test_assign_moderator_removes_broker_group(self):
        from users.services import assign_role
        user = make_broker()
        assign_role(user, 'moderator')
        self.assertEqual(list(user.groups.values_list('name', flat=True)), ['Модератори'])

    def test_ban_excludes_only_superusers(self):
        from users.admin import ban_users
        staff = make_staff()
        ban_users(mock.MagicMock(), mock.MagicMock(), User.objects.filter(pk=staff.pk))
        staff.refresh_from_db()
        self.assertTrue(staff.is_banned)
        su = make_staff(superuser=True)
        ban_users(mock.MagicMock(), mock.MagicMock(), User.objects.filter(pk=su.pk))
        su.refresh_from_db()
        self.assertFalse(su.is_banned)

    def test_moderator_cannot_change_owner_via_change_form(self):
        owner = make_user()
        thief = make_user()
        listing = make_local_listing(owner, status='pending')
        self.client.force_login(make_moderator())
        resp = self.client.post(f'/admin/local_listings/locallisting/{listing.pk}/change/', {
            'owner': thief.pk, 'status': 'active', 'make': 'Toyota', 'model': 'Camry',
            'year': 2020, 'mileage_km': 1, 'fuel_type': 'petrol', 'transmission': 'auto',
            'body_type': 'sedan', 'condition': listing.condition, 'price': '1', 'currency': 'UAH', 'price_type': 'fixed',
            'region': listing.region_id, 'city': listing.city_id,
            'images-TOTAL_FORMS': 0, 'images-INITIAL_FORMS': 0,
        })
        # форма сохранилась (302), но owner/status из POST проигнорированы
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        listing.refresh_from_db()
        self.assertEqual(listing.year, 2020)
        self.assertEqual(listing.owner_id, owner.pk)
        self.assertEqual(listing.status, 'pending')


class TestDemoteBareAdminMigration(TestCase):
    def test_demotes_only_non_superusers(self):
        import importlib

        from django.apps import apps
        mod = importlib.import_module('users.migrations.0011_demote_bare_admin_role')
        fake = make_user(role='admin')
        dealer_fake = make_user(role='admin', is_verified_dealer=True)
        real = make_staff(superuser=True, role='admin')
        mod.demote(apps, None)
        for u in (fake, dealer_fake, real):
            u.refresh_from_db()
        self.assertEqual(
            (fake.role, dealer_fake.role, real.role), ('buyer', 'dealer', 'admin'),
        )


# ─── Задача 1.3: JWT в httpOnly-cookie + CSRF ────────────────────────────────

REFRESH_URL = TOKEN_REFRESH_URL
CSRF_URL = '/api/v1/auth/csrf/'
PROFILE_URL = '/api/v1/auth/profile/'
SHOPS_URL = '/api/v1/auth/me/trusted-shops/'


def _expired_access(user):
    from datetime import timedelta

    from rest_framework_simplejwt.tokens import AccessToken
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=-timedelta(minutes=1))
    return str(token)


def _load_settings(env):
    """Отдельная копия core/settings.py с подменённым окружением (Django-настройки не трогает)."""
    import importlib.util
    import os

    from django.conf import settings as dj_settings
    path = os.path.join(dj_settings.BASE_DIR, 'core', 'settings.py')
    spec = importlib.util.spec_from_file_location('settings_env_probe', path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, env):
        spec.loader.exec_module(module)
    return module


def _blacklisted(token):
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
    return BlacklistedToken.objects.filter(token__jti=token['jti']).exists()


class CookieAuthTests(CleanCacheTestCase):

    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client = APIClient(enforce_csrf_checks=True)

    def _login(self):
        resp = self.client.post(TOKEN_URL, {'email': self.user.email, 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        return resp

    def _csrf(self):
        resp = self.client.get(CSRF_URL)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        return {'HTTP_X_CSRFTOKEN': self.client.cookies['csrftoken'].value}

    # 23-D20 (часть 1)
    def test_login_sets_httponly_cookies(self):
        resp = self._login()
        access, refresh = resp.cookies['access'], resp.cookies['refresh']
        self.assertTrue(access['httponly'])
        self.assertTrue(refresh['httponly'])
        self.assertEqual(access['samesite'], 'Lax')
        self.assertEqual(refresh['samesite'], 'Lax')
        self.assertEqual(access['path'], '/')
        self.assertEqual(refresh['path'], '/api/v1/auth/')
        self.assertEqual(access['max-age'], 15 * 60)
        self.assertEqual(refresh['max-age'], 7 * 24 * 3600)

    def test_login_updates_last_login(self):
        self._login()
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    @override_settings(AUTH_COOKIE_SECURE=True)
    def test_secure_flag_from_settings(self):
        resp = self._login()
        self.assertTrue(resp.cookies['access']['secure'])
        self.assertTrue(resp.cookies['refresh']['secure'])

    @override_settings(AUTH_COOKIE_SECURE=False)
    def test_no_secure_flag_when_disabled(self):
        resp = self._login()
        self.assertEqual(resp.cookies['access']['secure'], '')

    # Метка сессии для фронта (1.4): читается JS, токена не содержит.
    def test_login_sets_readable_session_hint(self):
        resp = self._login()
        hint = resp.cookies['has_session']
        self.assertEqual(hint.value, '1')
        self.assertEqual(hint['httponly'], '')
        self.assertEqual(hint['path'], '/')
        self.assertEqual(hint['max-age'], 7 * 24 * 3600)

    def test_refresh_failure_clears_session_hint(self):
        resp = APIClient().post(REFRESH_URL, {'refresh': 'garbage'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.cookies['has_session']['max-age'], 0)

    # 23-D20 (часть 2): с задачи 1.4 токены только в cookie, в теле их нет.
    def test_token_body_has_no_tokens(self):
        resp = self._login()
        self.assertEqual(resp.data, {'ok': True})
        self.assertIn('access', resp.cookies)
        self.assertIn('refresh', resp.cookies)

        resp = self.client.post(REFRESH_URL, **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data, {'ok': True})
        self.assertIn('access', resp.cookies)
        self.assertIn('refresh', resp.cookies)

    def test_csrf_endpoint_sets_readable_cookie(self):
        resp = self.client.get(CSRF_URL)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(resp.cookies['csrftoken']['httponly'], '')

    def test_cookie_auth_get_profile(self):
        self._login()
        self.client.credentials()  # только cookie, без Bearer
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['email'], self.user.email)

    def test_cookie_auth_post_without_csrf_forbidden(self):
        self._login()
        resp = self.client.post(SHOPS_URL, {'name': 'Shop'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('CSRF', str(resp.data['detail']))

    def test_cookie_auth_post_with_csrf_ok(self):
        self._login()
        resp = self.client.post(SHOPS_URL, {'name': 'Shop'}, format='json', **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_bearer_post_without_csrf_ok(self):
        from rest_framework_simplejwt.tokens import AccessToken
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.user)}')
        resp = self.client.post(SHOPS_URL, {'name': 'Shop'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_bearer_invalid_still_401(self):
        # Явный API-клиент с плохим токеном — 401, как в SimpleJWT.
        self.client.credentials(HTTP_AUTHORIZATION='Bearer garbage')
        resp = self.client.get('/api/v1/pricing/rates/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_cookie_on_protected_is_401(self):
        self.client.cookies['access'] = _expired_access(self.user)
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('Bearer', resp['WWW-Authenticate'])

    def test_garbage_cookie_on_allowany_get_is_anonymous(self):
        self.client.cookies['access'] = 'garbage'
        resp = self.client.get('/api/v1/pricing/rates/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_banned_user_cookie_is_anonymous(self):
        self._login()
        self.user.is_banned = True
        self.user.save(update_fields=['is_banned'])
        resp = self.client.get(PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # 23-D21
    def test_refresh_from_cookie_rotates(self):
        login = self._login()
        old_refresh = login.cookies['refresh'].value
        old_access = login.cookies['access'].value
        resp = self.client.post(REFRESH_URL, **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertNotEqual(resp.cookies['refresh'].value, old_refresh)
        self.assertNotEqual(resp.cookies['access'].value, old_access)
        self.assertEqual(resp.cookies['refresh']['path'], '/api/v1/auth/')

        reuse = APIClient().post(REFRESH_URL, {'refresh': old_refresh}, format='json')
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(reuse.cookies['access']['max-age'], 0)

    def test_refresh_from_cookie_without_csrf_forbidden(self):
        self._login()
        resp = self.client.post(REFRESH_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_refresh_from_body_without_csrf_ok(self):
        # Bearer-клиенты шлют refresh в теле без X-CSRFToken.
        refresh = RefreshToken.for_user(self.user)
        resp = APIClient(enforce_csrf_checks=True).post(REFRESH_URL, {'refresh': str(refresh)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertIn('access', resp.cookies)

    def test_refresh_garbage_is_neutral_401(self):
        resp = APIClient().post(REFRESH_URL, {'refresh': 'garbage'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.data, {'detail': 'Сесія завершилась. Увійдіть знову.'})

    # Logout (01-S13)
    def test_logout_with_expired_access_and_refresh_cookie(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies['access'] = _expired_access(self.user)
        self.client.cookies['refresh'] = str(refresh)
        resp = self.client.post(LOGOUT_URL, **self._csrf())
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(_blacklisted(refresh))
        self.assertEqual(resp.cookies['access']['max-age'], 0)
        self.assertEqual(resp.cookies['refresh']['max-age'], 0)
        self.assertEqual(resp.cookies['refresh']['path'], '/api/v1/auth/')
        self.assertEqual(resp.cookies['has_session']['max-age'], 0)

    def test_logout_refresh_cookie_without_csrf_forbidden(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(self.user)
        self.client.cookies['refresh'] = str(refresh)
        resp = self.client.post(LOGOUT_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(_blacklisted(refresh))

    def test_logout_foreign_refresh_rejected(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        foreign = RefreshToken.for_user(make_user())
        resp = auth_client(self.user).post(LOGOUT_URL, {'refresh': str(foreign)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(_blacklisted(foreign))

    def test_logout_own_refresh_in_body(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        own = RefreshToken.for_user(self.user)
        resp = auth_client(self.user).post(LOGOUT_URL, {'refresh': str(own)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(_blacklisted(own))

    def test_logout_garbage_refresh_neutral_text(self):
        resp = APIClient().post(LOGOUT_URL, {'refresh': 'garbage'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data, {'detail': 'Сесію вже завершено.'})

    def test_jwt_lifetimes_from_env(self):
        from datetime import timedelta
        module = _load_settings({'JWT_ACCESS_MINUTES': '30', 'JWT_REFRESH_DAYS': '14'})
        self.assertEqual(module.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'], timedelta(minutes=30))
        self.assertEqual(module.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'], timedelta(days=14))

    def test_open_cors_disables_credentials(self):
        # Ревью 1.3: «все origin» + credentials = любой сайт читает данные по cookie.
        self.assertTrue(_load_settings({'CORS_ALLOW_ALL_ORIGINS': 'false'}).CORS_ALLOW_CREDENTIALS)
        self.assertFalse(_load_settings({'CORS_ALLOW_ALL_ORIGINS': 'true'}).CORS_ALLOW_CREDENTIALS)

    def test_samesite_none_rejected(self):
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaisesMessage(ImproperlyConfigured, 'AUTH_COOKIE_SAMESITE'):
            _load_settings({'AUTH_COOKIE_SAMESITE': 'None'})

    # Ревью 1.3: login-CSRF через кросс-сайтовую HTML-форму.
    def test_login_form_encoded_rejected(self):
        resp = self.client.post(TOKEN_URL, {'email': self.user.email, 'password': TEST_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        self.assertNotIn('access', resp.cookies)

    def test_logout_form_encoded_rejected(self):
        resp = self.client.post(LOGOUT_URL, {'refresh': 'garbage'})
        self.assertEqual(resp.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        self.assertNotIn('access', resp.cookies)

    def test_login_rotates_csrf_token(self):
        before = self._csrf()['HTTP_X_CSRFTOKEN']
        resp = self._login()
        self.assertNotEqual(resp.cookies['csrftoken'].value, before)

    def test_cookie_post_on_allowany_without_csrf_forbidden(self):
        # Действие от имени вошедшего (расчёт попадёт в его историю) — только с CSRF.
        self._login()
        resp = self.client.post('/api/v1/pricing/calculate/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cookie_post_foreign_origin_forbidden(self):
        self._login()
        resp = self.client.post(
            SHOPS_URL, {'name': 'Shop'}, format='json',
            HTTP_ORIGIN='https://evil.example', **self._csrf(),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Origin', str(resp.data['detail']))

    def test_refresh_for_deleted_user_is_401(self):
        refresh = RefreshToken.for_user(self.user)
        self.user.delete()
        resp = APIClient().post(REFRESH_URL, {'refresh': str(refresh)}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # Регрессия: эндпоинт без DRF-аутентификации cookie и CSRF не трогают.
    def test_liqpay_callback_ignores_cookie_and_csrf(self):
        self._login()
        resp = self.client.post('/api/v1/payments/liqpay/callback/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data, {'error': 'data и signature обязательны.'})


class CookieAuthAllowAnyTests(CleanCacheTestCase):
    """09-Q7: протухшая cookie не ломает AllowAny-эндпоинты."""

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)
        cls.user = make_user()

    def test_expired_cookie_on_allowany_is_anonymous(self):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies['access'] = _expired_access(self.user)
        resp = client.post('/api/v1/pricing/calculate/', {
            'auction': 'copart', 'auction_price_usd': '5000', 'engine_cc': 2000,
            'fuel_type': 'petrol', 'vehicle_year': 2018, 'member_type': 'broker',
            'payment_type': 'secured', 'title_type': 'salvage',
            'us_port': 'houston', 'eu_port': 'klaipeda',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, getattr(resp, 'data', None))


# ── Журнал согласий (задача 1.14) ─────────────────────────────────────────────

class TestConsentLogRegistration(APITestCase):
    PAYLOAD = {**_REG_BASE, 'agreed_to_terms': True, 'confirmed_age_18': True}

    def setUp(self):
        super().setUp()
        cache.clear()

    def _set_version(self, version):
        from site_settings.models import SiteSettings
        s = SiteSettings.load()
        s.legal_docs_version = version
        s.save()

    def test_without_age_confirmation_400_and_nothing_created(self):
        payload = {k: v for k, v in self.PAYLOAD.items() if k != 'confirmed_age_18'}
        resp = self.client.post(REGISTER_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirmed_age_18', resp.data)
        self.assertFalse(User.objects.filter(email=_REG_BASE['email']).exists())
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_age_false_400(self):
        resp = self.client.post(REGISTER_URL, {**self.PAYLOAD, 'confirmed_age_18': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_register_writes_three_records_with_version(self):
        self._set_version('2026-10-01')
        resp = self.client.post(REGISTER_URL, self.PAYLOAD, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=_REG_BASE['email'])
        records = ConsentRecord.objects.all()
        self.assertEqual(records.count(), 3)
        self.assertEqual(
            sorted(r.document for r in records),
            [ConsentDocument.AGE_18, ConsentDocument.PRIVACY, ConsentDocument.TERMS],
        )
        for r in records:
            self.assertEqual(r.user, user)
            self.assertEqual(r.method, ConsentMethod.REGISTER)
            self.assertEqual(r.doc_version, '2026-10-01')
        self.assertIsNotNone(user.agreed_to_terms_at)

    def test_new_version_does_not_change_old_records(self):
        self._set_version('v1')
        self.client.post(REGISTER_URL, self.PAYLOAD, format='json')
        self._set_version('v2')
        self.client.post(REGISTER_URL, {**self.PAYLOAD, 'email': 'second@test.com'}, format='json')
        self.assertEqual(ConsentRecord.objects.filter(doc_version='v1').count(), 3)
        self.assertEqual(ConsentRecord.objects.filter(doc_version='v2', user__email='second@test.com').count(), 3)

    def test_empty_version_allowed(self):
        self.client.post(REGISTER_URL, self.PAYLOAD, format='json')
        self.assertEqual(ConsentRecord.objects.filter(doc_version='').count(), 3)

    def test_consent_failure_rolls_back_user(self):
        with mock.patch('users.serializers.record_consents', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                self.client.post(REGISTER_URL, self.PAYLOAD, format='json')
        self.assertFalse(User.objects.filter(email=_REG_BASE['email']).exists())

    def test_queryset_update_bulk_update_delete_forbidden(self):
        self.client.post(REGISTER_URL, self.PAYLOAD, format='json')
        with self.assertRaises(ImmutableError):
            ConsentRecord.objects.update(doc_version='x')
        with self.assertRaises(ImmutableError):
            ConsentRecord.objects.filter(document='terms').update(doc_version='x')
        with self.assertRaises(ImmutableError):
            ConsentRecord.objects.bulk_update(list(ConsentRecord.objects.all()), ['doc_version'])
        with self.assertRaises(ImmutableError):
            ConsentRecord.objects.all().delete()
        with self.assertRaises(ImmutableError):
            ConsentRecord.objects.first().delete()
        self.assertEqual(ConsentRecord.objects.count(), 3)
        self.assertEqual(ConsentRecord.objects.exclude(doc_version='').count(), 0)

    def test_record_is_immutable(self):
        self.client.post(REGISTER_URL, self.PAYLOAD, format='json')
        record = ConsentRecord.objects.first()
        record.doc_version = 'hacked'
        with self.assertRaises(ImmutableError):
            record.save()

    def test_no_ip_or_user_agent_fields(self):
        names = {f.name for f in ConsentRecord._meta.get_fields()}
        for forbidden in ('ip', 'ip_address', 'user_agent', 'text', 'consent_text'):
            self.assertNotIn(forbidden, names)


class TestConsentLogDealer(APITestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('dealerconsent@test.com')
        self.client.force_authenticate(self.user)

    def test_without_age_400(self):
        payload = {k: v for k, v in _APPLY_DATA.items() if k != 'confirmed_age_18'}
        resp = self.client.post(APPLY_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirmed_age_18', resp.data)
        self.assertFalse(DealerApplication.objects.exists())
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_age_false_400(self):
        resp = self.client.post(APPLY_URL, {**_APPLY_DATA, 'confirmed_age_18': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(DealerApplication.objects.exists())
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_with_age_two_records(self):
        resp = self.client.post(APPLY_URL, _APPLY_DATA, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        records = ConsentRecord.objects.all()
        self.assertEqual(
            sorted(r.document for r in records), [ConsentDocument.AGE_18, ConsentDocument.DEALER_PROCESSING],
        )
        self.assertTrue(all(r.method == ConsentMethod.DEALER_FORM and r.user == self.user for r in records))
        self.assertIsNotNone(DealerApplication.objects.get().agreed_to_processing_at)


class TestConsentRecordAdmin(TestCase):
    URL = '/admin/users/consentrecord/'

    def setUp(self):
        self.user = make_user()
        self.record = ConsentRecord.objects.create(
            user=self.user, document=ConsentDocument.TERMS, method=ConsentMethod.REGISTER,
        )

    def test_admin_can_view_but_not_add_change_delete(self):
        self.client.force_login(make_staff(superuser=True))
        self.assertEqual(self.client.get(self.URL).status_code, 200)
        self.assertEqual(self.client.get(self.URL + 'add/').status_code, 403)
        self.assertEqual(self.client.get(f'{self.URL}{self.record.pk}/change/').status_code, 200)  # view-only
        self.assertEqual(self.client.post(f'{self.URL}{self.record.pk}/change/', {}).status_code, 403)
        self.assertEqual(self.client.get(f'{self.URL}{self.record.pk}/delete/').status_code, 403)
        self.assertEqual(self.client.post(f'{self.URL}{self.record.pk}/delete/', {'post': 'yes'}).status_code, 403)
        self.assertTrue(ConsentRecord.objects.filter(pk=self.record.pk).exists())

    def test_admin_role_staff_can_view(self):
        self.client.force_login(make_admin_role())
        self.assertEqual(self.client.get(self.URL).status_code, 200)

    def test_moderator_and_broker_denied(self):
        for maker in (make_moderator, make_broker):
            with self.subTest(maker=maker.__name__):
                self.client.force_login(maker())
                self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_regular_user_redirected_to_login(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.URL).status_code, 302)

    def test_moderator_does_not_see_section_in_index(self):
        self.client.force_login(make_moderator())
        self.assertNotContains(self.client.get('/admin/'), 'consentrecord')


class TestConsentRecordUserDeletion(TestCase):
    def test_deleting_user_keeps_record_with_null_user(self):
        user = make_user()
        ConsentRecord.objects.create(user=user, document=ConsentDocument.TERMS, method=ConsentMethod.REGISTER)
        user.delete()
        record = ConsentRecord.objects.get()
        self.assertIsNone(record.user)
        self.assertEqual(record.document, ConsentDocument.TERMS)

    def test_deleting_lead_keeps_record_with_public_id(self):
        from leads.models import Lead
        from leads.services import create_lead
        from site_settings.models import SiteSettings
        s = SiteSettings.load()
        s.partner_name = 'Партнер'
        s.save()
        lead = create_lead(user=None, data={'name': 'Іван', 'phone': '0671234567', 'contact_method': 'telegram'})
        public_id = lead.public_id
        Lead.objects.filter(pk=lead.pk).delete()
        records = ConsentRecord.objects.all()
        self.assertEqual(records.count(), 2)
        for r in records:
            self.assertIsNone(r.lead)
            self.assertEqual(r.lead_public_id, public_id)
