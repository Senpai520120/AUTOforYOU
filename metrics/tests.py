"""Задача 8.7: дневные счётчики без ПДн."""
from datetime import date, datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

from django.contrib.admin.sites import site
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from metrics.models import DailyMetric, MetricKey
from metrics.services import record_metric, record_metric_on_commit
from tests.factories import auth_client, make_admin_role, make_broker, make_local_listing, make_moderator, make_user

EVENT_URL = '/api/v1/metrics/event/'


def value(key, day=None):
    row = DailyMetric.objects.filter(key=key, date=day or timezone.localdate()).first()
    return row.value if row else 0


class RecordMetricTests(TestCase):
    def test_three_events_one_row(self):
        for _ in range(3):
            record_metric(MetricKey.CALCULATION)
        self.assertEqual(DailyMetric.objects.count(), 1)
        self.assertEqual(value(MetricKey.CALCULATION), 3)

    def test_new_day_new_row(self):
        record_metric(MetricKey.LEAD, day=date(2026, 1, 1))
        record_metric(MetricKey.LEAD, day=date(2026, 1, 2))
        self.assertEqual(DailyMetric.objects.filter(key=MetricKey.LEAD).count(), 2)

    def test_day_by_kyiv(self):
        # 2026-01-01 22:30 UTC = 2026-01-02 00:30 в Києві
        with patch('django.utils.timezone.now', return_value=datetime(2026, 1, 1, 22, 30, tzinfo=dt_timezone.utc)):
            record_metric(MetricKey.LEAD)
        self.assertEqual(value(MetricKey.LEAD, date(2026, 1, 2)), 1)

    def test_race_on_create_still_counts(self):
        DailyMetric.objects.create(date=timezone.localdate(), key=MetricKey.LEAD, value=5)
        real_filter = DailyMetric.objects.filter
        calls = {'n': 0}

        def flaky_filter(*a, **kw):  # первый update «не нашёл» строку - как будто её создал соседний запрос
            qs = real_filter(*a, **kw)
            calls['n'] += 1
            return qs.none() if calls['n'] == 1 else qs

        with patch.object(DailyMetric.objects, 'filter', side_effect=flaky_filter):
            record_metric(MetricKey.LEAD)
        self.assertEqual(value(MetricKey.LEAD), 6)

    def test_unknown_key_logged_not_raised(self):
        with self.assertLogs('metrics.services', level='WARNING'):
            record_metric('email@x.com')
        self.assertFalse(DailyMetric.objects.exists())

    def test_db_error_logged_without_data(self):
        with patch.object(DailyMetric.objects, 'filter', side_effect=IntegrityError('boom')), \
                self.assertLogs('metrics.services', level='WARNING') as logs:
            record_metric(MetricKey.LEAD)
        self.assertNotIn('@', '\n'.join(logs.output))

    def test_rollback_not_counted(self):
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    record_metric_on_commit(MetricKey.LEAD)
                    raise RuntimeError('rollback')
            except RuntimeError:
                pass
        self.assertEqual(value(MetricKey.LEAD), 0)

    def test_no_identifier_fields(self):
        names = {f.name for f in DailyMetric._meta.get_fields()}
        self.assertEqual(names, {'id', 'date', 'key', 'value'})


class EventEndpointTests(TestCase):
    def post(self, body):
        return APIClient().post(EVENT_URL, body, format='json')

    def test_calculator_visit_204(self):
        resp = self.post({'key': 'calculator_visit'})
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.content, b'')
        self.assertEqual(value(MetricKey.CALCULATOR_VISIT), 1)

    def test_mobile_bar_click_204(self):
        self.assertEqual(self.post({'key': 'mobile_bar_click'}).status_code, 204)

    def test_server_keys_rejected(self):
        for body in ({'key': 'registration'}, {'key': 'lead'}, {'key': ''}, {'key': ['calculator_visit']}, {}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertFalse(DailyMetric.objects.exists())

    def test_extra_fields_rejected(self):
        self.assertEqual(self.post({'key': 'calculator_visit', 'user': 1}).status_code, 400)
        self.assertFalse(DailyMetric.objects.exists())

    def test_throttled_429(self):
        with patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
                patch.object(ScopedRateThrottle, 'wait', return_value=None):
            self.assertEqual(self.post({'key': 'calculator_visit'}).status_code, 429)

    def test_no_csrf_or_auth_needed(self):
        from django.conf import settings
        from rest_framework_simplejwt.tokens import AccessToken
        client = APIClient(enforce_csrf_checks=True)
        # cookie access есть, CSRF-токена нет: без authentication_classes=[] был бы 403
        client.cookies[settings.AUTH_COOKIE_ACCESS_NAME] = str(AccessToken.for_user(make_user()))
        self.assertEqual(client.post(EVENT_URL, {'key': 'calculator_visit'}, format='json').status_code, 204)


class HookTests(TestCase):
    def test_registration(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = APIClient().post('/api/v1/auth/register/', {
                'email': 'metric@test.com', 'password': 'Strong-Pass-9182', 'password2': 'Strong-Pass-9182',
                'agreed_to_terms': True, 'confirmed_age_18': True}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value(MetricKey.REGISTRATION), 1)

    def test_registration_existing_email_not_counted(self):
        make_user('taken@test.com')
        with self.captureOnCommitCallbacks(execute=True):
            APIClient().post('/api/v1/auth/register/', {
                'email': 'taken@test.com', 'password': 'Strong-Pass-9182', 'password2': 'Strong-Pass-9182',
                'agreed_to_terms': True, 'confirmed_age_18': True}, format='json')
        self.assertEqual(value(MetricKey.REGISTRATION), 0)

    def test_lead(self):
        from leads.tests_api import body, make_calc, set_partner
        set_partner()
        calc = make_calc()
        with self.captureOnCommitCallbacks(execute=True):
            resp = APIClient().post('/api/v1/leads/', body(calculation_id=calc.pk), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value(MetricKey.LEAD), 1)

    def test_listing_submitted(self):
        from local_listings.tests import _listing_payload, _make_city, _make_region
        region = _make_region()
        with self.captureOnCommitCallbacks(execute=True):
            resp = auth_client(make_user()).post('/api/v1/local/listings/',
                                                 _listing_payload(region, _make_city(region)), format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(value(MetricKey.LISTING_SUBMITTED), 1)

    def test_phone_view(self):
        listing = make_local_listing(make_user())
        with self.captureOnCommitCallbacks(execute=True):
            resp = auth_client(make_user()).get(f'/api/v1/local/listings/{listing.pk}/contact/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(value(MetricKey.PHONE_VIEW), 1)

    def test_phone_view_anonymous_401_not_counted(self):
        listing = make_local_listing(make_user())
        with self.captureOnCommitCallbacks(execute=True):
            resp = APIClient().get(f'/api/v1/local/listings/{listing.pk}/contact/')
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(value(MetricKey.PHONE_VIEW), 0)


class AdminTests(TestCase):
    def setUp(self):
        self.row = DailyMetric.objects.create(date=timezone.localdate(), key=MetricKey.LEAD, value=1)

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_admin_role_sees_list(self):
        self.assertEqual(self.client_for(make_admin_role()).get('/admin/metrics/dailymetric/').status_code, 200)

    def test_add_change_delete_forbidden(self):
        client = self.client_for(make_admin_role())
        self.assertEqual(client.get('/admin/metrics/dailymetric/add/').status_code, 403)
        self.assertEqual(client.post(f'/admin/metrics/dailymetric/{self.row.pk}/change/', {'value': 9}).status_code, 403)
        self.assertEqual(client.post(f'/admin/metrics/dailymetric/{self.row.pk}/delete/', {'post': 'yes'}).status_code,
                         403)
        self.assertEqual(DailyMetric.objects.get().value, 1)

    def test_moderator_and_broker_no_access(self):
        for user in (make_moderator(), make_broker()):
            with self.subTest(role=user.role):
                self.assertEqual(self.client_for(user).get('/admin/metrics/dailymetric/').status_code, 403)

    def test_model_registered(self):
        self.assertIn(DailyMetric, site._registry)
