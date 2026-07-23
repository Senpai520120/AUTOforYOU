"""
Tests for C2C-промт 4: favorites, notifications, saved_searches.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from local_listings.models import LocalListing, Region, City
from users.models import CustomUser
from notifications.models import Notification
from notifications.services import create_notification, unread_count
from favorites.models import Favorite
from saved_searches.models import SavedSearch
from saved_searches.tasks import check_saved_searches


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_user(email, role='buyer', **kw):
    return CustomUser.objects.create_user(email=email, password='pass1234', role=role, **kw)


def make_listing(owner, region, city, **kw):
    defaults = dict(
        make='Toyota', model='Camry', year=2020,
        mileage_km=50000, fuel_type='petrol', transmission='auto',
        body_type='sedan', condition='used',
        price='500000', currency='UAH', price_type='fixed',
        region=region, city=city,
        status=LocalListing.Status.ACTIVE,
        agreed_to_rules=True,
    )
    defaults.update(kw)
    return LocalListing.objects.create(owner=owner, **defaults)


class SetupMixin(TestCase):
    def setUp(self):
        self.buyer = make_user('buyer@test.com')
        self.seller = make_user('seller@test.com')
        self.region = Region.objects.create(name='Київська', slug='kyivska')
        self.city = City.objects.create(name='Київ', slug='kyiv', region=self.region)
        self.listing = make_listing(self.seller, self.region, self.city)
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)


# ─── Notifications ────────────────────────────────────────────────────────────

class TestNotificationService(SetupMixin):
    def test_create_notification(self):
        n = create_notification(
            self.buyer.pk,
            Notification.Type.LISTING_APPROVED,
            'Заголовок',
            'Текст',
            '/local/1',
        )
        self.assertEqual(n.user_id, self.buyer.pk)
        self.assertEqual(n.type, Notification.Type.LISTING_APPROVED)
        self.assertFalse(n.is_read)

    def test_unread_count(self):
        create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'A', '')
        create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'B', '')
        self.assertEqual(unread_count(self.buyer.pk), 2)

    def test_unread_decreases_after_mark_read(self):
        n = create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'A', '')
        Notification.objects.filter(pk=n.pk).update(is_read=True)
        self.assertEqual(unread_count(self.buyer.pk), 0)


class TestNotificationAPI(SetupMixin):
    def test_anon_gets_401(self):
        r = self.client.get('/api/v1/notifications/')
        self.assertEqual(r.status_code, 401)

    def test_list_own_notifications(self):
        create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'Test', '')
        self.auth(self.buyer)
        r = self.client.get('/api/v1/notifications/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)

    def test_other_user_cannot_see(self):
        create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'Test', '')
        self.auth(self.seller)
        r = self.client.get('/api/v1/notifications/')
        self.assertEqual(len(r.data), 0)

    def test_unread_count_api(self):
        create_notification(self.buyer.pk, Notification.Type.LISTING_APPROVED, 'OK', '')
        self.auth(self.buyer)
        r = self.client.get('/api/v1/notifications/unread-count/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['unread_count'], 1)

    def test_mark_read_single(self):
        n = create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'A', '')
        self.auth(self.buyer)
        r = self.client.post('/api/v1/notifications/mark-read/', {'id': n.pk}, format='json')
        self.assertEqual(r.status_code, 200)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_read_all(self):
        create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'A', '')
        create_notification(self.buyer.pk, Notification.Type.NEW_MESSAGE, 'B', '')
        self.auth(self.buyer)
        self.client.post('/api/v1/notifications/mark-read/', {'all': True}, format='json')
        self.assertEqual(unread_count(self.buyer.pk), 0)

    def test_moderation_creates_in_app_notification(self):
        """approve_listing должен создавать in-app Notification."""
        from local_listings.services import approve_listing
        admin = make_user('admin@test.com', role='admin')
        self.listing.status = LocalListing.Status.PENDING
        self.listing.save()
        approve_listing(self.listing, admin)
        n = Notification.objects.filter(user=self.seller, type=Notification.Type.LISTING_APPROVED).first()
        self.assertIsNotNone(n)

    def test_reject_creates_in_app_notification(self):
        from local_listings.services import reject_listing
        admin = make_user('admin2@test.com', role='admin')
        self.listing.status = LocalListing.Status.PENDING
        self.listing.save()
        reject_listing(self.listing, admin, 'Погані фото')
        n = Notification.objects.filter(user=self.seller, type=Notification.Type.LISTING_REJECTED).first()
        self.assertIsNotNone(n)

    def test_new_message_creates_notification(self):
        """Нове повідомлення через messaging → в-app Notification для отримувача."""
        from messaging.services import get_or_create_conversation
        get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        n = Notification.objects.filter(user=self.seller, type=Notification.Type.NEW_MESSAGE).first()
        self.assertIsNotNone(n)


# ─── Favorites ────────────────────────────────────────────────────────────────

class TestFavoritesAPI(SetupMixin):
    def test_anon_gets_401(self):
        r = self.client.get('/api/v1/favorites/')
        self.assertEqual(r.status_code, 401)

    def test_add_local_listing_to_favorites(self):
        self.auth(self.buyer)
        r = self.client.post(
            '/api/v1/favorites/',
            {'listing_type': 'local', 'listing_id': self.listing.pk},
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Favorite.objects.filter(user=self.buyer, local_listing=self.listing).exists())

    def test_duplicate_add_returns_200(self):
        self.auth(self.buyer)
        payload = {'listing_type': 'local', 'listing_id': self.listing.pk}
        self.client.post('/api/v1/favorites/', payload, format='json')
        r = self.client.post('/api/v1/favorites/', payload, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Favorite.objects.filter(user=self.buyer).count(), 1)

    def test_list_favorites(self):
        Favorite.objects.create(user=self.buyer, local_listing=self.listing)
        self.auth(self.buyer)
        r = self.client.get('/api/v1/favorites/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['listing_type'], 'local')

    def test_other_user_sees_empty(self):
        Favorite.objects.create(user=self.buyer, local_listing=self.listing)
        self.auth(self.seller)
        r = self.client.get('/api/v1/favorites/')
        self.assertEqual(len(r.data), 0)

    def test_remove_from_favorites(self):
        Favorite.objects.create(user=self.buyer, local_listing=self.listing)
        self.auth(self.buyer)
        r = self.client.delete(
            '/api/v1/favorites/',
            {'listing_type': 'local', 'listing_id': self.listing.pk},
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Favorite.objects.filter(user=self.buyer).exists())

    def test_status_endpoint(self):
        self.auth(self.buyer)
        r = self.client.get(f'/api/v1/favorites/status/?listing_type=local&listing_id={self.listing.pk}')
        self.assertFalse(r.data['is_favorite'])
        Favorite.objects.create(user=self.buyer, local_listing=self.listing)
        r = self.client.get(f'/api/v1/favorites/status/?listing_type=local&listing_id={self.listing.pk}')
        self.assertTrue(r.data['is_favorite'])


# ─── SavedSearches ────────────────────────────────────────────────────────────

class TestSavedSearchAPI(SetupMixin):
    def test_anon_gets_401(self):
        r = self.client.get('/api/v1/saved-searches/')
        self.assertEqual(r.status_code, 401)

    def test_create_saved_search(self):
        self.auth(self.buyer)
        r = self.client.post(
            '/api/v1/saved-searches/',
            {'name': 'Toyota 2020+', 'filters': {'make': 'Toyota', 'year_min': '2020'}, 'notify': True},
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(SavedSearch.objects.filter(user=self.buyer).count(), 1)

    def test_list_own_saved_searches(self):
        SavedSearch.objects.create(user=self.buyer, name='Test', filters={}, notify=True)
        self.auth(self.buyer)
        r = self.client.get('/api/v1/saved-searches/')
        self.assertEqual(len(r.data), 1)

    def test_other_user_cannot_see(self):
        SavedSearch.objects.create(user=self.buyer, name='Test', filters={}, notify=True)
        self.auth(self.seller)
        r = self.client.get('/api/v1/saved-searches/')
        self.assertEqual(len(r.data), 0)

    def test_delete_saved_search(self):
        ss = SavedSearch.objects.create(user=self.buyer, name='Test', filters={}, notify=True)
        self.auth(self.buyer)
        r = self.client.delete(f'/api/v1/saved-searches/{ss.pk}/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(SavedSearch.objects.filter(pk=ss.pk).exists())

    def test_other_user_cannot_delete(self):
        ss = SavedSearch.objects.create(user=self.buyer, name='Test', filters={}, notify=True)
        self.auth(self.seller)
        r = self.client.delete(f'/api/v1/saved-searches/{ss.pk}/')
        self.assertEqual(r.status_code, 404)


class TestSavedSearchTask(SetupMixin):
    def test_task_creates_notification_for_new_listing(self):
        """Нове оголошення, що підходить — створює Notification."""
        ss = SavedSearch.objects.create(
            user=self.buyer,
            name='Camry',
            filters={'make': 'Toyota'},
            notify=True,
            last_notified_at=None,
        )
        # listing was created after saved_search.created_at — task should catch it
        # Force last_notified_at to be before listing creation
        from django.utils import timezone
        import datetime
        ss.last_notified_at = timezone.now() - datetime.timedelta(days=1)
        ss.save()

        # Ensure listing created_at is after last_notified_at
        self.listing.created_at = timezone.now()
        self.listing.save(update_fields=['created_at'] if hasattr(self.listing, 'created_at') else [])

        check_saved_searches()
        n = Notification.objects.filter(user=self.buyer, type=Notification.Type.SAVED_SEARCH_MATCH).first()
        self.assertIsNotNone(n)

    def test_task_does_not_duplicate_on_rerun(self):
        """Повторний запуск задачі не дублює сповіщення."""
        from django.utils import timezone
        import datetime
        SavedSearch.objects.create(
            user=self.buyer,
            name='Camry',
            filters={'make': 'Toyota'},
            notify=True,
            last_notified_at=timezone.now() - datetime.timedelta(days=1),
        )
        check_saved_searches()
        count_first = Notification.objects.filter(user=self.buyer, type=Notification.Type.SAVED_SEARCH_MATCH).count()

        # Run again — last_notified_at is now updated, so no new listings
        check_saved_searches()
        count_second = Notification.objects.filter(user=self.buyer, type=Notification.Type.SAVED_SEARCH_MATCH).count()
        self.assertEqual(count_first, count_second)

    def test_task_skips_non_matching(self):
        """SavedSearch для Honda не спрацьовує на Toyota."""
        from django.utils import timezone
        import datetime
        SavedSearch.objects.create(
            user=self.buyer,
            name='Honda',
            filters={'make': 'Honda'},
            notify=True,
            last_notified_at=timezone.now() - datetime.timedelta(days=1),
        )
        check_saved_searches()
        n = Notification.objects.filter(user=self.buyer, type=Notification.Type.SAVED_SEARCH_MATCH).first()
        self.assertIsNone(n)
