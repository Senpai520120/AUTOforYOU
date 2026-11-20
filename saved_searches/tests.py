"""Задача 10.22: проверка filters при сохранении, устойчивая и без потерь рассылка сохранённых поисков."""
import datetime
import logging
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from local_listings.models import LocalListing
from notifications.models import Notification
from saved_searches import tasks
from saved_searches.models import SavedSearch
from saved_searches.tasks import check_saved_searches
from tests.factories import make_local_listing, make_user

URL = '/api/v1/saved-searches/'
NUL = chr(0)


class SavedSearchFiltersValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user('ss_val@test.com')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _post(self, filters, name='Test'):
        return self.client.post(URL, {'name': name, 'filters': filters, 'notify': True}, format='json')

    def test_valid_filters_saved_normalized(self):
        r = self._post({'make': 'Toyota', 'year_min': 2020, 'price_max': '15000.50', 'fuel_type': 'petrol'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(
            r.data['filters'],
            {'make': 'Toyota', 'year_min': '2020', 'price_max': '15000.50', 'fuel_type': 'petrol'},
        )

    def test_unknown_key_400(self):
        r = self._post({'make': 'Toyota', 'is_admin': '1'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('is_admin', str(r.data['filters']))

    def test_non_numeric_year_400(self):
        r = self._post({'year_min': 'abc'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('year_min', str(r.data))

    def test_huge_number_400(self):
        r = self._post({'price_min': '1e30'})
        self.assertEqual(r.status_code, 400)

    def test_nul_in_value_400(self):
        r = self._post({'make': 'Toy' + NUL + 'ota'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('make', str(r.data))

    def test_nul_in_name_400(self):
        r = self._post({}, name='a' + NUL + 'b')
        self.assertEqual(r.status_code, 400)
        self.assertIn('name', r.data)

    def test_nested_value_400(self):
        r = self._post({'make': ['a', 'b']})
        self.assertEqual(r.status_code, 400)

    def test_filters_not_object_400(self):
        r = self._post(['make'])
        self.assertEqual(r.status_code, 400)

    def test_invalid_choice_400(self):
        r = self._post({'fuel_type': 'plutonium'})
        self.assertEqual(r.status_code, 400)

    def test_patch_validates_filters(self):
        ss = SavedSearch.objects.create(user=self.user, name='A', filters={})
        r = self.client.patch(f'{URL}{ss.pk}/', {'filters': {'zzz': 1}}, format='json')
        self.assertEqual(r.status_code, 400)


class SavedSearchDigestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user('ss_task@test.com')
        cls.seller = make_user('ss_seller@test.com')

    def setUp(self):
        self.t0 = timezone.now() - datetime.timedelta(days=2)
        for target, kwargs in (
            ('saved_searches.tasks.c2c_public_posting_enabled', {'return_value': True}),
            ('integrations.tasks.send_notification.delay', {}),
        ):
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _search(self, filters=None):
        return SavedSearch.objects.create(
            user=self.user, name='S', filters=filters or {}, notify=True, last_notified_at=self.t0)

    def _listing(self, published_at, **kw):
        """Активное объявление, опубликованное (moderated_at) в published_at; created_at - давно."""
        listing = make_local_listing(self.seller, **kw)
        LocalListing.objects.filter(pk=listing.pk).update(
            moderated_at=published_at, created_at=self.t0 - datetime.timedelta(days=30))
        return listing

    def _notifs(self):
        return Notification.objects.filter(user=self.user, type=Notification.Type.SAVED_SEARCH_MATCH)

    def test_selects_by_moderation_date_not_created_at(self):
        """Старое по created_at, но одобренное сейчас - попадает в рассылку."""
        self._search()
        self._listing(timezone.now() - datetime.timedelta(hours=1))
        check_saved_searches()
        self.assertEqual(self._notifs().count(), 1)

    def test_listing_approved_before_cursor_not_sent(self):
        """Создано после курсора, но одобрено до него - не берётся (отбор не по created_at)."""
        self._search()
        listing = make_local_listing(self.seller)
        LocalListing.objects.filter(pk=listing.pk).update(moderated_at=self.t0 - datetime.timedelta(hours=1))
        check_saved_searches()
        self.assertEqual(self._notifs().count(), 0)

    def test_cursor_is_latest_published_date(self):
        ss = self._search()
        published = timezone.now() - datetime.timedelta(hours=3)
        self._listing(published)
        check_saved_searches()
        ss.refresh_from_db()
        self.assertEqual(ss.last_notified_at, published)

    def test_more_than_ten_not_lost(self):
        ss = self._search()
        base = timezone.now() - datetime.timedelta(hours=20)
        for i in range(13):
            self._listing(base + datetime.timedelta(minutes=i))
        check_saved_searches()
        # 10 отдельных + одно «і ще 3»
        self.assertEqual(self._notifs().count(), 11)
        more = self._notifs().get(text='і ще 3 нових оголошень')
        self.assertEqual(more.link, '/local')
        ss.refresh_from_db()
        self.assertEqual(ss.last_notified_at, base + datetime.timedelta(minutes=12))
        # Повторный запуск ничего не добавляет
        check_saved_searches()
        self.assertEqual(self._notifs().count(), 11)

    def test_overflow_link_carries_filters(self):
        self._search({'make': 'Toyota'})
        base = timezone.now() - datetime.timedelta(hours=20)
        for i in range(11):
            self._listing(base + datetime.timedelta(minutes=i))
        check_saved_searches()
        self.assertEqual(self._notifs().get(text='і ще 1 нових оголошень').link, '/local?make=Toyota')

    def test_invalid_stored_filters_skipped_with_warning_others_processed(self):
        bad = self._search({'evil': 'x'})
        other = make_user('ss_other@test.com')
        good = SavedSearch.objects.create(
            user=other, name='G', filters={'make': 'Toyota'}, notify=True, last_notified_at=self.t0)
        self._listing(timezone.now() - datetime.timedelta(hours=1))
        with self.assertLogs('saved_searches.tasks', level=logging.WARNING) as cm:
            result = check_saved_searches()
        self.assertEqual(result, {'processed': 1})
        self.assertEqual(len(cm.records), 1)
        self.assertEqual(cm.records[0].levelno, logging.WARNING)
        self.assertIn(f'id={bad.pk}', cm.output[0])
        self.assertEqual(Notification.objects.filter(user=other).count(), 1)
        bad.refresh_from_db()
        good.refresh_from_db()
        self.assertEqual(bad.last_notified_at, self.t0)
        self.assertGreater(good.last_notified_at, self.t0)

    def test_exception_in_one_search_does_not_stop_loop(self):
        first = self._search({'make': 'Toyota'})
        other = make_user('ss_other2@test.com')
        second = SavedSearch.objects.create(
            user=other, name='G', filters={'make': 'Toyota'}, notify=True, last_notified_at=self.t0)
        self._listing(timezone.now() - datetime.timedelta(hours=1))
        real = tasks._process_search

        def flaky(ss_id, now):
            if ss_id == first.pk:
                raise RuntimeError('boom')
            return real(ss_id, now)

        with patch('saved_searches.tasks._process_search', side_effect=flaky):
            with self.assertLogs('saved_searches.tasks', level=logging.ERROR):
                result = check_saved_searches()
        self.assertEqual(result, {'processed': 1})
        second.refresh_from_db()
        self.assertGreater(second.last_notified_at, self.t0)
