"""Флаг E2E_RELAX_THROTTLES (задача 9.58): работает только при E2E_SEED_ALLOWED=true, на проде launch_check ругается."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.tests_launch_check import LaunchCheckTestCase
from core.throttle_relax import KEEP_SCOPES, RELAXED_RATE, relax_rates, relax_requested

RATES = {'anon': '60/hour', 'login': '10/min', 'lead': '5/hour', 'calculator': '30/hour', 'client_errors': '20/hour',
         'metrics_event': '60/min'}
ROOT = Path(settings.BASE_DIR)


class RelaxRatesTests(SimpleTestCase):
    def test_flag_with_seed_allowed_relaxes_all_but_client_errors(self):
        rates, active = relax_rates(RATES, {'E2E_RELAX_THROTTLES': 'true', 'E2E_SEED_ALLOWED': 'true'})
        self.assertTrue(active)
        self.assertEqual(rates['client_errors'], '20/hour')
        for scope in set(RATES) - set(KEEP_SCOPES):
            self.assertEqual(rates[scope], RELAXED_RATE, scope)

    def test_flag_without_seed_allowed_keeps_production_limits(self):
        rates, active = relax_rates(RATES, {'E2E_RELAX_THROTTLES': 'true'})
        self.assertFalse(active)
        self.assertEqual(rates, RATES)

    def test_seed_allowed_without_flag_keeps_production_limits(self):
        rates, active = relax_rates(RATES, {'E2E_SEED_ALLOWED': 'true'})
        self.assertFalse(active)
        self.assertEqual(rates, RATES)

    def test_seed_allowed_false_blocks_the_flag(self):
        rates, active = relax_rates(RATES, {'E2E_RELAX_THROTTLES': 'true', 'E2E_SEED_ALLOWED': 'false'})
        self.assertFalse(active)
        self.assertEqual(rates, RATES)

    def test_seed_allowed_must_be_exactly_true_like_e2e_seed(self):
        for value in ('1', 'yes', 'on', 'tru', ''):
            with self.subTest(value=value):
                rates, active = relax_rates(RATES, {'E2E_RELAX_THROTTLES': 'true', 'E2E_SEED_ALLOWED': value})
                self.assertEqual((rates, active), (RATES, False))
        for value in ('TRUE', ' true '):
            with self.subTest(value=value):
                self.assertTrue(relax_rates(RATES, {'E2E_RELAX_THROTTLES': 'true', 'E2E_SEED_ALLOWED': value})[1])

    def test_falsy_flag_values_do_nothing(self):
        for value in ('', 'false', '0', 'no', 'off', 'tru'):
            with self.subTest(value=value):
                rates, active = relax_rates(RATES, {'E2E_RELAX_THROTTLES': value, 'E2E_SEED_ALLOWED': 'true'})
                self.assertEqual((rates, active), (RATES, False))

    def test_truthy_spellings_are_accepted(self):
        for value in ('TRUE', ' 1 ', 'yes', 'True'):
            with self.subTest(value=value):
                self.assertTrue(relax_rates(RATES, {'E2E_RELAX_THROTTLES': value, 'E2E_SEED_ALLOWED': 'true'})[1])

    def test_input_is_not_mutated_and_scopes_are_kept(self):
        original = dict(RATES)
        rates, _ = relax_rates(RATES, {'E2E_RELAX_THROTTLES': 'true', 'E2E_SEED_ALLOWED': 'true'})
        self.assertEqual(RATES, original)
        self.assertEqual(set(rates), set(RATES))

    def test_requested_is_independent_of_seed_allowed(self):
        self.assertTrue(relax_requested({'E2E_RELAX_THROTTLES': 'true'}))
        self.assertFalse(relax_requested({'E2E_SEED_ALLOWED': 'true'}))

    def test_test_settings_use_production_limits(self):
        self.assertFalse(settings.E2E_RELAX_THROTTLES)
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['lead'], '5/hour')


class SettingsWiringTests(SimpleTestCase):
    """Подключение флага в core/settings.py: настоящая загрузка settings в отдельном процессе."""

    def lead_rate(self, **env):
        import os
        import subprocess
        import sys
        code = ('import django;django.setup();from django.conf import settings as s;'
                "print(s.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['lead'], "
                "s.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['client_errors'], s.E2E_RELAX_THROTTLES)")
        base = {k: v for k, v in os.environ.items() if not k.startswith(('E2E_', 'THROTTLE_'))}
        base.update(DJANGO_SETTINGS_MODULE='core.settings', DATABASE_URL='', REDIS_URL='')
        out = subprocess.run([sys.executable, '-c', code], cwd=settings.BASE_DIR, env={**base, **env},
                             capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        return out.stdout.split()[-3:]

    def test_flag_with_seed_allowed_changes_real_settings(self):
        self.assertEqual(self.lead_rate(E2E_RELAX_THROTTLES='true', E2E_SEED_ALLOWED='true'),
                         ['100000/hour', '20/hour', 'True'])

    def test_flag_without_seed_allowed_keeps_real_limits(self):
        self.assertEqual(self.lead_rate(E2E_RELAX_THROTTLES='true'), ['5/hour', '20/hour', 'False'])


class LaunchCheckRelaxTests(LaunchCheckTestCase):
    def test_seed_allowed_on_production_is_an_error(self):
        code, out = self.run_check(env={'E2E_SEED_ALLOWED': 'true'})
        self.assertFails(code, out, 'E2E_SEED_ALLOWED=true')


    def test_flag_on_production_is_an_error(self):
        code, out = self.run_check(E2E_RELAX_THROTTLES_REQUESTED=True)
        self.assertFails(code, out, 'E2E_RELAX_THROTTLES=true')

    def test_flag_off_is_ok(self):
        code, out = self.run_check(E2E_RELAX_THROTTLES_REQUESTED=False)
        self.assertOk(code, out)
        self.assertNotIn('E2E_RELAX_THROTTLES', out)

    def test_flag_in_debug_mode_is_only_a_warning(self):
        code, out = self.run_check(E2E_RELAX_THROTTLES_REQUESTED=True, DEBUG=True)
        self.assertIn('E2E_RELAX_THROTTLES=true (режим розробки)', out)
        self.assertNotEqual(code, 1, out)


class TemplatesTests(SimpleTestCase):
    @staticmethod
    def active_lines(name):
        return [ln.strip() for ln in (ROOT / name).read_text(encoding='utf8').splitlines()
                if ln.strip() and not ln.lstrip().startswith('#')]

    def test_e2e_template_enables_the_flag_and_has_no_duplicated_rates(self):
        lines = self.active_lines('.env.e2e.example')
        self.assertIn('E2E_RELAX_THROTTLES=true', lines)
        self.assertEqual([ln for ln in lines if ln.startswith('THROTTLE_')], [])

    def test_e2e_template_keeps_login_lockout_thresholds(self):
        lines = self.active_lines('.env.e2e.example')
        self.assertIn('LOGIN_MAX_FAILURES=5', lines)
        self.assertIn('LOGIN_LOCKOUT_MINUTES=1', lines)

    def test_production_templates_do_not_enable_the_flag(self):
        for name in ('.env.example', '.env.docker.example'):
            with self.subTest(name=name):
                self.assertFalse([ln for ln in self.active_lines(name) if ln.startswith('E2E_RELAX_THROTTLES')])
                text = (ROOT / name).read_text(encoding='utf8')
                self.assertIn('# E2E_RELAX_THROTTLES=false', text)
