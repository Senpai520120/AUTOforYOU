"""
Тесты верификации дилеров: DealerApplication, B2B-гейтинг, wholesale-фильтрация.
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import DealerApplication
from .services import apply_for_dealer, approve_application, reject_application, DuplicatePendingError

User = get_user_model()

APPLY_URL = '/api/v1/dealers/apply/'
STATUS_URL = '/api/v1/dealers/application/'


def _make_user(email='user@test.com', **kwargs):
    return User.objects.create_user(email=email, password='testpass123', **kwargs)


def _make_admin(email='admin@test.com'):
    return User.objects.create_superuser(email=email, password='testpass123')


_APPLY_DATA = {
    'company_name': 'ТОВ Авто',
    'full_name': 'Іван Іванов',
    'contact_phone': '+380991234567',
    'documents': 'https://drive.google.com/doc123',
}


# ── Сервисный слой ────────────────────────────────────────────────────────────

class TestDealerApplicationService(APITestCase):

    def setUp(self):
        self.user = _make_user()
        self.admin = _make_admin()

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
        self.user = _make_user()
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
        self.user = _make_user()
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
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_regular_user_gets_403(self):
        user = _make_user('plain@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_verified_dealer_gets_200(self):
        user = _make_user('dealer@test.com', is_verified_dealer=True, role='dealer')
        self.client.force_authenticate(user)
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_gets_200(self):
        admin = _make_admin('admin2@test.com')
        self.client.force_authenticate(admin)
        resp = self.client.get(self.B2B_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ── Wholesale-фильтрация в каталоге ──────────────────────────────────────────

class TestWholesaleCatalogFilter(APITestCase):

    LISTINGS_URL = '/api/v1/listings/'

    def _make_listing(self, channel, seller):
        from vehicles.models import Vehicle
        from listings.models import Listing
        v = Vehicle.objects.create(
            make='Toyota', model='Camry', year=2020, vin=f'VIN{channel[:1].upper()}001',
            fuel_type='petrol', engine_cc=2000, mileage_km=50000,
        )
        return Listing.objects.create(
            vehicle=v, seller=seller, price=10000, currency='USD', channel=channel,
        )

    def setUp(self):
        self.seller = _make_user('seller@test.com')
        self.retail = self._make_listing('retail', self.seller)
        self.wholesale = self._make_listing('wholesale', self.seller)

    def test_anonymous_sees_only_retail(self):
        resp = self.client.get(self.LISTINGS_URL)
        ids = [r['id'] for r in resp.data['results']] if 'results' in resp.data else [r['id'] for r in resp.data]
        self.assertIn(self.retail.id, ids)
        self.assertNotIn(self.wholesale.id, ids)

    def test_regular_user_sees_only_retail(self):
        user = _make_user('buyer@test.com')
        self.client.force_authenticate(user)
        resp = self.client.get(self.LISTINGS_URL)
        ids = [r['id'] for r in resp.data['results']] if 'results' in resp.data else [r['id'] for r in resp.data]
        self.assertIn(self.retail.id, ids)
        self.assertNotIn(self.wholesale.id, ids)

    def test_verified_dealer_sees_wholesale(self):
        dealer = _make_user('dea@test.com', is_verified_dealer=True, role='dealer')
        self.client.force_authenticate(dealer)
        resp = self.client.get(self.LISTINGS_URL)
        ids = [r['id'] for r in resp.data['results']] if 'results' in resp.data else [r['id'] for r in resp.data]
        self.assertIn(self.retail.id, ids)
        self.assertIn(self.wholesale.id, ids)
