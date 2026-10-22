"""Задача 8.7: дневные счётчики без ПДн (DailyMetric, record_metric, публичный эндпоинт, хуки, админка)."""
from datetime import UTC, date, datetime
from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from leads.services import create_lead
from local_listings.models import LocalListing
from local_listings.tests import _listing_payload, _make_city, _make_region
from metrics import services
from metrics.admin import DailyMetricAdmin
from metrics.models import DailyMetric, MetricKey
from pricing import tests_config as pt
from pricing.models import Calculation
from pricing.tasks import purge_anonymous_calculations
from site_settings.models import SiteSettings
from tests.factories import (
    auth_client,
    make_admin_role,
    make_broker,
    make_local_listing,
    make_moderator,
    make_staff,
    make_user,
)

EVENT_URL = '/api/v1/metrics/event/'
REGISTER_URL = '/api/v1/auth/register/'


def value(key, day=None):
    row = DailyMetric.objects.filter(key=key, date=day or services.timezone.localdate()).first()
    return row.value if row else 0


class RecordMetricTests(TestCase):
    def record(self, *args, **kw):
        with self.captureOnCommitCallbacks(execute=True):
            services.record_metric(*args, **kw)

    def test_three_calls_one_row_value_three(self):
        for _ in range(3):
            self.record(MetricKey.LEAD)
        self.assertEqual(DailyMetric.objects.filter(key='lead').count(), 1)
        self.assertEqual(value('lead'), 3)

    def test_amount(self):
        self.record(MetricKey.LEAD, amount=5)
        self.assertEqual(value('lead'), 5)

    def test_new_day_new_row(self):
        self.record(MetricKey.LEAD, day=date(2026, 1, 1))
        self.record(MetricKey.LEAD, day=date(2026, 1, 2))
        self.assertEqual(DailyMetric.objects.filter(key='lead').count(), 2)

    def test_day_uses_kyiv_midnight_boundary(self):
        # 22:30 UTC 31 декабря = 00:30 1 января по Киеву (зима, UTC+2)
        moment = datetime(2026, 12, 31, 22, 30, tzinfo=UTC)
        with mock.patch('django.utils.timezone.now', return_value=moment):
            self.record(MetricKey.LEAD)
        self.assertEqual(value('lead', date(2027, 1, 1)), 1)
        self.assertEqual(value('lead', date(2026, 12, 31)), 0)

    def test_unknown_key_ignored(self):
        with self.assertLogs('metrics.services', 'WARNING'):
            self.record('hacked')
        self.assertEqual(DailyMetric.objects.count(), 0)

    def test_race_integrity_error_retried(self):
        real = DailyMetric.objects.get_or_create
        calls = {'n': 0}

        def flaky(*a, **kw):
            calls['n'] += 1
            if calls['n'] == 1:
                raise IntegrityError('duplicate')
            return real(*a, **kw)

        with mock.patch.object(type(DailyMetric.objects), 'get_or_create', side_effect=flaky):
            self.record(MetricKey.LEAD)
        self.assertEqual(calls['n'], 2)
        self.assertEqual(value('lead'), 1)

    def test_rollback_not_counted(self):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    services.record_metric(MetricKey.LEAD)
                    raise RuntimeError('rollback')
            except RuntimeError:
                pass
        self.assertEqual(value('lead'), 0)

    def test_written_only_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            services.record_metric(MetricKey.LEAD)
            self.assertEqual(DailyMetric.objects.count(), 0)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(DailyMetric.objects.count(), 0)

    def test_db_error_not_raised_and_log_without_data(self):
        with mock.patch.object(DailyMetric.objects, 'get_or_create', side_effect=RuntimeError('db down')), \
                self.assertLogs('metrics.services', 'WARNING') as cm:
            self.record(MetricKey.LEAD)
        self.assertEqual(DailyMetric.objects.count(), 0)
        self.assertIn('metrics.record_failed key=lead', cm.output[0])

    def test_unique_constraint(self):
        DailyMetric.objects.create(date=date(2026, 1, 1), key='lead', value=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyMetric.objects.create(date=date(2026, 1, 1), key='lead', value=1)

    def test_model_has_no_identifier_fields(self):
        names = {f.name for f in DailyMetric._meta.get_fields()}
        self.assertEqual(names, {'id', 'date', 'key', 'value'})
        self.assertFalse([f for f in DailyMetric._meta.get_fields() if f.is_relation])

    def test_plural_name(self):
        self.assertEqual(DailyMetric._meta.verbose_name_plural, 'Щоденні метрики')


class MetricEventApiTests(APITestCase):
    def post(self, body, **kw):
        return self.client.post(EVENT_URL, body, format='json', **kw)

    def test_calculator_visit_204_and_plus_one(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.post({'key': 'calculator_visit'})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b'')
        self.assertEqual(value('calculator_visit'), 1)

    def test_mobile_bar_click(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.post({'key': 'mobile_bar_click'})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(value('mobile_bar_click'), 1)

    def test_rejected_payloads_400_and_no_change(self):
        bad = [
            {'key': 'registration'}, {'key': 'lead'}, {'key': ''}, {}, {'key': ['calculator_visit']},
            {'key': 'calculator_visit', 'user': 1}, {'key': 'calculator_visit', 'extra': 'x'},
            ['calculator_visit'], 'calculator_visit',
        ]
        for body in bad:
            with self.subTest(body=body), self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(DailyMetric.objects.count(), 0)

    def test_throttle_429(self):
        with mock.patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
                mock.patch.object(ScopedRateThrottle, 'wait', return_value=None), \
                self.captureOnCommitCallbacks(execute=True):
            resp = self.post({'key': 'calculator_visit'})
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(DailyMetric.objects.count(), 0)

    def test_throttle_scope_configured(self):
        from django.conf import settings
        self.assertIn('metrics_event', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])

    def test_no_auth_needed_and_garbage_token_ignored(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Bearer not-a-token')
        with self.captureOnCommitCallbacks(execute=True):
            resp = client.post(EVENT_URL, {'key': 'calculator_visit'}, format='json')
        self.assertEqual(resp.status_code, 204)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(EVENT_URL).status_code, 405)


class CalculationHookTests(pt.SeededCase):
    def test_calculation_plus_one_anonymous(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.calc()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value('calculation'), 1)

    def test_calculation_plus_one_user(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.calc(user=make_user())
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value('calculation'), 1)

    def test_not_counted_on_validation_error(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.calc(engine_cc=-1)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(value('calculation'), 0)

    def test_purge_does_not_decrease(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.calc()
        Calculation.objects.update(created_at=pt.timezone.now() - pt.timedelta(days=400))
        purge_anonymous_calculations()
        self.assertEqual(Calculation.objects.count(), 0)
        self.assertEqual(value('calculation'), 1)

    def test_metric_failure_does_not_break_calculation(self):
        with mock.patch.object(DailyMetric.objects, 'get_or_create', side_effect=RuntimeError('db down')), \
                self.assertLogs('metrics.services', 'WARNING'), self.captureOnCommitCallbacks(execute=True):
            resp = self.calc()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Calculation.objects.count(), 1)


class RegistrationHookTests(APITestCase):
    BODY = {
        'email': 'metric-user@test.com', 'password': 'StrongPass123!', 'password2': 'StrongPass123!',
        'agreed_to_terms': True, 'confirmed_age_18': True,
    }

    def test_registration_plus_one(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(REGISTER_URL, self.BODY, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value('registration'), 1)

    def test_failed_registration_not_counted(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(REGISTER_URL, {**self.BODY, 'agreed_to_terms': False}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(value('registration'), 0)

    def test_metric_failure_does_not_break_registration_and_log_has_no_email(self):
        with mock.patch.object(DailyMetric.objects, 'get_or_create', side_effect=RuntimeError('db down')), \
                self.assertLogs('metrics.services', 'WARNING') as cm, self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(REGISTER_URL, self.BODY, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn('metric-user@test.com', '\n'.join(cm.output))


class LeadHookTests(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()

    def lead(self):
        return create_lead(user=None, data={'name': 'Іван', 'phone': '0671234567', 'contact_method': 'telegram'})

    def test_lead_plus_one(self):
        with mock.patch('leads.services.notify_new_lead'), mock.patch('leads.services.notify_journal'), \
                self.captureOnCommitCallbacks(execute=True):
            self.lead()
        self.assertEqual(value('lead'), 1)

    def test_metric_failure_does_not_break_lead_and_log_has_no_phone(self):
        with mock.patch('leads.services.notify_new_lead'), mock.patch('leads.services.notify_journal'), \
                mock.patch.object(DailyMetric.objects, 'get_or_create', side_effect=RuntimeError('db down')), \
                self.assertLogs('metrics.services', 'WARNING') as cm, \
                self.captureOnCommitCallbacks(execute=True):
            lead = self.lead()
        self.assertIsNotNone(lead.pk)
        text = '\n'.join(cm.output)
        self.assertNotIn('0671234567', text)
        self.assertNotIn('+380671234567', text)


class LocalListingHookTests(APITestCase):
    def setUp(self):
        self.region = _make_region()
        self.city = _make_city(self.region)
        self.owner = make_user()

    def test_listing_submitted_plus_one(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = auth_client(self.owner).post(
                '/api/v1/local/listings/', _listing_payload(self.region, self.city), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value('listing_submitted'), 1)

    def test_invalid_listing_not_counted(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = auth_client(self.owner).post(
                '/api/v1/local/listings/', _listing_payload(self.region, self.city, year=1800), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(value('listing_submitted'), 0)

    def test_phone_view_plus_one_authenticated(self):
        listing = make_local_listing(self.owner, region=self.region, city=self.city, contact_phone='+380501234567')
        with self.captureOnCommitCallbacks(execute=True):
            resp = auth_client(make_user()).get(f'/api/v1/local/listings/{listing.pk}/contact/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(value('phone_view'), 1)

    def test_phone_view_anonymous_401_not_counted(self):
        listing = make_local_listing(self.owner, region=self.region, city=self.city, contact_phone='+380501234567')
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.get(f'/api/v1/local/listings/{listing.pk}/contact/')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(value('phone_view'), 0)

    def test_phone_view_not_counted_for_inactive(self):
        listing = make_local_listing(
            self.owner, status=LocalListing.Status.PENDING, region=self.region, city=self.city,
            contact_phone='+380501234567')
        with self.captureOnCommitCallbacks(execute=True):
            resp = auth_client(make_user()).get(f'/api/v1/local/listings/{listing.pk}/contact/')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(value('phone_view'), 0)


class AdminTests(TestCase):
    LIST_URL = '/admin/metrics/dailymetric/'

    def setUp(self):
        DailyMetric.objects.create(date=date(2026, 1, 1), key='lead', value=3)

    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)

    def test_registered(self):
        self.assertIsInstance(admin_site._registry[DailyMetric], DailyMetricAdmin)

    def test_superuser_sees_changelist(self):
        self.assertEqual(self.get(make_staff(superuser=True), self.LIST_URL).status_code, 200)

    def test_admin_role_sees_changelist(self):
        self.assertEqual(self.get(make_admin_role(), self.LIST_URL).status_code, 200)

    def test_add_forbidden(self):
        self.assertEqual(self.get(make_staff(superuser=True), self.LIST_URL + 'add/').status_code, 403)

    def test_change_view_forbidden_for_post(self):
        obj = DailyMetric.objects.get()
        admin = make_staff(superuser=True)
        self.client.force_login(admin)
        resp = self.client.post(f'{self.LIST_URL}{obj.pk}/change/', {'value': 999})
        self.assertEqual(resp.status_code, 403)
        obj.refresh_from_db()
        self.assertEqual(obj.value, 3)

    def test_delete_forbidden(self):
        obj = DailyMetric.objects.get()
        resp = self.get(make_staff(superuser=True), f'{self.LIST_URL}{obj.pk}/delete/')
        self.assertEqual(resp.status_code, 403)

    def test_moderator_and_broker_forbidden(self):
        for maker in (make_moderator, make_broker):
            with self.subTest(maker=maker.__name__):
                self.assertEqual(self.get(maker(), self.LIST_URL).status_code, 403)

    def test_anonymous_redirected_to_login(self):
        self.assertEqual(self.client.get(self.LIST_URL).status_code, 302)
