"""Калькулятор при недоступном Redis (задача 10.16): throttle пропускает, расчёт отвечает."""
from core.tests_api_resilience import REDIS_DOWN, ThrottleBrokenCacheMixin
from pricing.tests_config import SeededCase


class CalculatorRedisDownTests(ThrottleBrokenCacheMixin, SeededCase):
    def test_redis_connection_error_calculation_ok(self):
        self.break_throttle_cache(REDIS_DOWN[0])
        with self.assertLogs('core.throttles', 'WARNING') as logs:
            resp = self.calc()
        self.assertEqual(resp.status_code, 201)
        self.assertIn('calculator', logs.output[0])
        self.alert.assert_called_once_with()

    def test_builtin_connection_error_calculation_ok(self):
        self.break_throttle_cache(REDIS_DOWN[1])
        self.assertEqual(self.calc().status_code, 201)

    def test_django_redis_interrupted_calculation_ok(self):
        self.break_throttle_cache(REDIS_DOWN[2])
        self.assertEqual(self.calc().status_code, 201)
