from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.models import CustomUser
from local_listings.models import Region, City, LocalListing
from .models import Report


def _token(user):
    return str(RefreshToken.for_user(user).access_token)


def _auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {_token(user)}')


def _make_user(email='u@test.com', **kw):
    return CustomUser.objects.create_user(email=email, password='pass', **kw)


def _make_region(name='Тест-обл'):
    return Region.objects.get_or_create(name=name, defaults={'slug': name.lower().replace(' ', '-')})[0]


def _make_city(region, name='Тест-місто'):
    return City.objects.get_or_create(region=region, slug='tc', defaults={'name': name})[0]


def _make_listing(owner, region, city, status_val=LocalListing.Status.ACTIVE):
    return LocalListing.objects.create(
        owner=owner, make='BMW', model='X5', year=2021,
        mileage_km=30000, fuel_type='petrol', transmission='auto',
        body_type='suv', price='900000', currency='UAH', price_type='fixed',
        region=region, city=city, status=status_val, agreed_to_rules=True,
    )


class TestReportCreate(APITestCase):
    def setUp(self):
        self.reporter = _make_user('rep@test.com')
        self.owner = _make_user('owner@test.com')
        self.region = _make_region()
        self.city = _make_city(self.region)
        self.listing = _make_listing(self.owner, self.region, self.city)

    def test_create_listing_report(self):
        _auth(self.client, self.reporter)
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
        _auth(self.client, self.reporter)
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
        _auth(self.client, self.reporter)
        self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk, 'reason': 'spam',
        }, format='json')
        r = self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk, 'reason': 'duplicate',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Report.objects.count(), 1)

    def test_cannot_report_without_target(self):
        _auth(self.client, self.reporter)
        r = self.client.post('/api/v1/reports/', {'reason': 'spam'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_cannot_report_both_listing_and_user(self):
        _auth(self.client, self.reporter)
        r = self.client.post('/api/v1/reports/', {
            'listing': self.listing.pk,
            'reported_user': self.owner.pk,
            'reason': 'spam',
        }, format='json')
        self.assertEqual(r.status_code, 400)

    def test_cannot_report_self(self):
        _auth(self.client, self.reporter)
        r = self.client.post('/api/v1/reports/', {
            'reported_user': self.reporter.pk,
            'reason': 'fraud',
        }, format='json')
        self.assertEqual(r.status_code, 400)
