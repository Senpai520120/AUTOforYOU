from rest_framework.test import APITestCase

from tests.factories import auth_client, make_local_listing, make_user

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
