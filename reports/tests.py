from rest_framework.test import APITestCase

from audit.models import AuditAction, AuditLog
from local_listings.models import LocalListing
from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_local_listing, make_staff, make_user

from .models import Report


class TestReportCreate(APITestCase):
    def setUp(self):
        self.reporter = make_user('rep@test.com')
        self.owner = make_user('owner@test.com')
        self.listing = make_local_listing(self.owner, make='BMW', model='X5', year=2021,
                                          body_type='suv', price='900000')

    def test_create_listing_report(self):
        self.client = auth_client(self.reporter)
        r = self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk,
            'reason': 'spam',
            'comment': 'Це спам',
        }, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Report.objects.count(), 1)
        report = Report.objects.first()
        self.assertEqual(report.status, Report.Status.NEW)
        self.assertEqual(report.reporter, self.reporter)

    def test_create_user_report(self):
        self.client = auth_client(self.reporter)
        r = self.client.post('/api/v1/reports/', {
            'reported_user': self.owner.pk,
            'reason': 'fraud',
        }, format='json')
        self.assertEqual(r.status_code, 201)

    def test_anon_cannot_report(self):
        r = self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk,
            'reason': 'spam',
        }, format='json')
        self.assertEqual(r.status_code, 401)

    def test_duplicate_report_rejected(self):
        self.client = auth_client(self.reporter)
        self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk, 'reason': 'spam',
        }, format='json')
        r = self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk, 'reason': 'duplicate',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Report.objects.count(), 1)

    def test_cannot_report_without_target(self):
        self.client = auth_client(self.reporter)
        r = self.client.post('/api/v1/reports/', {'reason': 'spam'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_cannot_report_both_listing_and_user(self):
        self.client = auth_client(self.reporter)
        r = self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk,
            'reported_user': self.owner.pk,
            'reason': 'spam',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_cannot_report_self(self):
        self.client = auth_client(self.reporter)
        r = self.client.post('/api/v1/reports/', {
            'reported_user': self.reporter.pk,
            'reason': 'fraud',
        }, format='json')
        self.assertEqual(r.status_code, 400)


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
