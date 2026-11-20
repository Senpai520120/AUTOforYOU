"""Заявка при недоступном Redis (задача 10.16): throttle пропускает, заявка создаётся."""
from unittest import mock

from django.test import override_settings
from rest_framework.throttling import ScopedRateThrottle

from core.tests_api_resilience import REDIS_DOWN, ThrottleBrokenCacheMixin, broken_cache
from integrations.captcha import issue_form_token
from leads.models import Lead
from leads.tests_api import LeadApiBase, make_calc


class LeadRedisDownTests(ThrottleBrokenCacheMixin, LeadApiBase):
    def test_redis_connection_error_lead_still_created(self):
        self.break_throttle_cache(REDIS_DOWN[0])
        with self.assertLogs('core.throttles', 'WARNING') as logs:
            resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertIn('кеш недоступний', logs.output[0])
        self.assertNotIn('380671234567', logs.output[0])
        self.alert.assert_called_once_with()

    def test_builtin_connection_error_lead_still_created(self):
        self.break_throttle_cache(REDIS_DOWN[1])
        resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 201)

    def test_real_429_still_works_when_cache_is_alive(self):
        from unittest import mock
        with mock.patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
                mock.patch.object(ScopedRateThrottle, 'wait', return_value=60.0):
            resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 429)

    def test_django_redis_interrupted_lead_still_created(self):
        self.break_throttle_cache(REDIS_DOWN[2])
        resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 201)


class LeadCaptchaCacheDownTests(LeadApiBase):
    """Капча без кэша НЕ fail-open: вместо 500 - 503 (на фронте это запасной контакт 10.7)."""

    @override_settings(CAPTCHA_PROVIDER='honeypot', CAPTCHA_MIN_FILL_SECONDS=0)
    def test_captcha_without_cache_is_503_not_500(self):
        token = issue_form_token('127.0.0.1')
        broken = broken_cache(REDIS_DOWN[2])
        with mock.patch('integrations.captcha.cache', broken),                 mock.patch('leads.views._alert_once') as alert,                 self.assertLogs('leads.views', 'WARNING') as logs:
            resp = self.post(calculation_id=make_calc().pk, captcha_token=token)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()['detail'], 'Тимчасово недоступно, спробуйте пізніше')
        self.assertEqual(Lead.objects.count(), 0)
        self.assertNotIn('380671234567', logs.output[0])
        alert.assert_called_once_with()
