from unittest import mock

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from audit.models import AuditAction, AuditLog
from local_listings.models import LocalListing
from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_local_listing, make_staff, make_user

from .models import Report


class TestReportCreate(APITestCase):
    URL = '/api/v1/reports/'

    def setUp(self):
        cache.clear()
        self.reporter = make_user('rep@test.com')
        self.owner = make_user('owner@test.com')
        self.listing = make_local_listing(self.owner, make='BMW', model='X5', year=2021,
                                          body_type='suv', price='900000')
        self.client = auth_client(self.reporter)

    def post(self, listing, **extra):
        return self.client.post(self.URL, {'listing': listing, 'reason': 'spam', **extra}, format='json')

    def test_create_listing_report(self):
        r = self.post(self.listing.pk, comment='Це спам')
        self.assertEqual(r.status_code, 201)
        report = Report.objects.get()
        self.assertEqual(report.status, Report.Status.NEW)
        self.assertEqual(report.reporter, self.reporter)
        self.assertEqual(report.listing, self.listing)
        self.assertEqual(r.json(), {'id': report.pk, 'listing': self.listing.pk, 'reason': 'spam', 'comment': 'Це спам'})

    def test_anon_cannot_report(self):
        r = APIClient().post(self.URL, {'listing': self.listing.pk, 'reason': 'spam'}, format='json')
        self.assertEqual(r.status_code, 401)

    @override_settings(EMAIL_VERIFICATION_REQUIRED=True)
    def test_unverified_email_is_403(self):
        r = auth_client(make_user(verified=False)).post(
            self.URL, {'listing': self.listing.pk, 'reason': 'spam'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['code'], 'email_not_verified')
        self.assertFalse(Report.objects.exists())

    def test_duplicate_report_rejected(self):
        self.post(self.listing.pk)
        r = self.post(self.listing.pk, reason='duplicate')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Ви вже подали скаргу на це оголошення.', str(r.json()))
        self.assertEqual(Report.objects.count(), 1)

    def test_listing_is_required(self):
        r = self.client.post(self.URL, {'reason': 'spam'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('listing', r.json())

    def test_reported_user_from_client_is_ignored(self):
        """B9: нарушитель - владелец объявления; чужой id в reported_user ни на что не влияет."""
        stranger = make_user()
        r = self.post(self.listing.pk, reported_user=stranger.pk)
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(Report.objects.get().reported_user)

    def test_report_on_user_without_listing_is_impossible(self):
        r = self.client.post(self.URL, {'reported_user': self.owner.pk, 'reason': 'fraud'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Report.objects.exists())

    def test_cannot_report_own_listing(self):
        r = auth_client(self.owner).post(self.URL, {'listing': self.listing.pk, 'reason': 'spam'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Report.objects.exists())

    def test_hidden_and_missing_listing_give_identical_404(self):
        """B9: по ответу не узнать, есть ли скрытое объявление."""
        missing = self.post(999999)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json(), {'detail': 'Оголошення не знайдено.'})
        for st in LocalListing.Status:
            if st == LocalListing.Status.ACTIVE:
                continue
            LocalListing.objects.filter(pk=self.listing.pk).update(status=st)
            with self.subTest(status=st):
                r = self.post(self.listing.pk)
                self.assertEqual(r.status_code, missing.status_code)
                self.assertEqual(r.json(), missing.json())
        self.assertFalse(Report.objects.exists())

    def test_comment_over_limit_is_400_not_saved(self):
        with override_settings(REPORT_COMMENT_MAX_LENGTH=10):
            r = self.post(self.listing.pk, comment='x' * 11)
            self.assertEqual(r.status_code, 400)
            self.assertIn('comment', r.json())
            self.assertFalse(Report.objects.exists())
            self.assertEqual(self.post(self.listing.pk, comment='x' * 10).status_code, 201)

    def test_default_comment_limit_is_1000(self):
        r = self.post(self.listing.pk, comment='x' * 1001)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.post(self.listing.pk, comment='x' * 1000).status_code, 201)

    def test_reports_rate_limit_third_is_429(self):
        others = [make_local_listing(self.owner) for _ in range(3)]
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'reports': '2/hour'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            for listing in others[:2]:
                self.assertEqual(self.post(listing.pk).status_code, 201)
            r = self.post(others[2].pk)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()['detail'], 'Забагато скарг, спробуйте пізніше.')
        self.assertEqual(Report.objects.count(), 2)


class TestReportAdminActionsAudit(CleanCacheTestCase):
    """1.13: действия по жалобам пишут журнал с автором; без права change действий нет."""
    URL = '/admin/reports/report/'

    def setUp(self):
        super().setUp()
        self.admin = make_staff(superuser=True)
        self.owner = make_user('owner-rep@test.com')
        self.listing = make_local_listing(self.owner)
        self.report = Report.objects.create(reporter=make_user(), listing=self.listing, reason='fraud')

    def _post(self, user, action, **extra):
        self.client.force_login(user)
        return self.client.post(self.URL, {'action': action, '_selected_action': [self.report.pk], **extra})

    def test_hide_listing_logs_listing_and_report(self):
        resp = self._post(self.admin, 'hide_listing')
        self.assertEqual(resp.status_code, 302)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.HIDDEN)
        hide = AuditLog.objects.get(action=AuditAction.LISTING_HIDE)
        self.assertEqual(hide.actor, self.admin)
        self.assertEqual(hide.target_id, str(self.listing.pk))
        self.assertIn(f'report#{self.report.pk}', hide.reason)
        review = AuditLog.objects.get(action=AuditAction.REPORT_REVIEW)
        self.assertEqual(review.after, {'status': Report.Status.REVIEWED})

    def test_dismiss_logs(self):
        self._post(self.admin, 'dismiss_report')
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.DISMISSED)
        row = AuditLog.objects.get(action=AuditAction.REPORT_DISMISS)
        self.assertEqual(row.actor, self.admin)
        self.assertEqual(row.target_id, str(self.report.pk))

    def test_ban_reported_user_requires_reason(self):
        resp = self._post(self.admin, 'ban_reported_user', apply='1', reason='')
        self.assertContains(resp, 'Причину блокування вказати обов&#x27;язково')
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_banned)
        self.assertFalse(AuditLog.objects.filter(action=AuditAction.USER_BLOCK).exists())

    def test_ban_reported_user_blocks_with_reason_and_logs(self):
        resp = self._post(self.admin, 'ban_reported_user', apply='1', reason='Шахрайство за скаргою')
        self.assertEqual(resp.status_code, 302)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_banned)
        self.assertEqual(self.owner.blocks.get().reason, 'Шахрайство за скаргою')
        row = AuditLog.objects.get(action=AuditAction.USER_BLOCK)
        self.assertEqual(row.actor, self.admin)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.REVIEWED)

    def test_view_only_staff_has_no_actions(self):
        from django.contrib.auth.models import Permission
        staff = make_staff()
        staff.user_permissions.add(Permission.objects.get(codename='view_report'))
        resp = self._post(staff, 'dismiss_report')
        self.assertEqual(resp.status_code, 200)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.NEW)
        self.assertFalse(AuditLog.objects.exists())
