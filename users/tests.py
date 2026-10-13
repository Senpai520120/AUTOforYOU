"""
Тесты верификации дилеров: DealerApplication, B2B-гейтинг, wholesale-фильтрация.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core import mail
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from tests.factories import (
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

from .models import DealerApplication
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

    def test_logout_requires_auth(self):
        resp = self.client.post(LOGOUT_URL, {'refresh': self.refresh_str}, format='json')
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
        resp = self.client.post(REGISTER_URL, {**_REG_BASE, 'agreed_to_terms': False}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('agreed_to_terms', resp.data)

    def test_register_without_consent_field_returns_400(self):
        resp = self.client.post(REGISTER_URL, _REG_BASE, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_with_consent_sets_agreed_to_terms_at(self):
        resp = self.client.post(REGISTER_URL, {**_REG_BASE, 'agreed_to_terms': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email=_REG_BASE['email'])
        self.assertIsNotNone(user.agreed_to_terms_at)

    def test_register_with_consent_returns_201(self):
        resp = self.client.post(REGISTER_URL, {**_REG_BASE, 'agreed_to_terms': True}, format='json')
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

    def test_register_ignores_role_admin(self):
        # Решение 1.2: поле role в запросе молча игнорируется (не 400): пользователь всегда buyer.
        resp = self.client.post(
            REGISTER_URL,
            {**_REG_BASE, 'role': 'admin', 'agreed_to_terms': True},
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
            {**_REG_BASE, 'role': 'dealer', 'agreed_to_terms': True},
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
            {**_REG_BASE, 'role': 'broker', 'agreed_to_terms': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.get(email=_REG_BASE['email']).role, 'buyer')

    def test_register_ignores_role_moderator(self):
        resp = self.client.post(
            REGISTER_URL,
            {**_REG_BASE, 'role': 'moderator', 'agreed_to_terms': True},
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
        self.assertEqual(names['Брокери'], {'view_calculation'})


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

    SiteSettings (1.12) и Lead (2.1) ещё не существуют; их проверка добавится с моделями.
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
        self.assertEqual(set(perms) & {'payments', 'pricing', 'users'}, set())

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
