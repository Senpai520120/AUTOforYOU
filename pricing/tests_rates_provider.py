"""Задача 3.4a: курс НБУ через провайдера (ExchangeRateProvider), источник курса и давность (02-C8, 02-Q13)."""
import http.client
from datetime import date, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from celery.exceptions import Retry
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from integrations.base import http_timeout
from integrations.models import IntegrationHealth
from pricing import cache as pricing_cache
from pricing.calculator import exchange_rate_info
from pricing.models import ExchangeRate
from pricing.rates_provider import (
    DemoRateProvider,
    NbuRateProvider,
    RatesUnavailable,
    get_rate_provider,
)
from pricing.tasks import fetch_nbu_rates_task
from pricing.tests_config import TARIFFS, SeededCase
from tests.base import CleanCacheTestCase
from tests.factories import make_staff, make_user

USD_BODY = b'[{"r030":840,"txt":"Dollar","rate":41.5,"cc":"USD","exchangedate":"23.06.2026"}]'
EUR_BODY = b'[{"r030":978,"txt":"Euro","rate":45.0,"cc":"EUR","exchangedate":"23.06.2026"}]'


def response(body: bytes):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def nbu_ok(url, *args, **kwargs):
    return response(USD_BODY if 'valcode=USD' in url else EUR_BODY)


def patch_nbu(side_effect):
    return patch('pricing.rates_provider.urlopen', side_effect=side_effect)


class NbuFetchTests(CleanCacheTestCase):

    def test_empty_response_records_error_and_saves_nothing(self):
        with patch_nbu(lambda url, **kw: response(b'[]')):
            with self.assertRaisesMessage(RatesUnavailable, 'пустой ответ'):
                NbuRateProvider().fetch(date(2026, 6, 23))
        from pricing.nbu import fetch_and_save_rates
        with patch_nbu(lambda url, **kw: response(b'[]')):
            with self.assertRaises(RatesUnavailable):
                fetch_and_save_rates()
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='nbu').last_error_at)
        self.assertEqual(ExchangeRate.objects.count(), 0)

    def test_task_retries_on_empty_response(self):
        with patch_nbu(lambda url, **kw: response(b'[]')), \
                patch.object(fetch_nbu_rates_task, 'retry', side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                fetch_nbu_rates_task()
        self.assertEqual(retry.call_count, 1)

    def test_task_retries_on_invalid_json(self):
        with patch_nbu(lambda url, **kw: response(b'<html>502</html>')), \
                patch.object(fetch_nbu_rates_task, 'retry', side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                fetch_nbu_rates_task()
        self.assertEqual(retry.call_count, 1)

    def test_nan_rate_is_rejected(self):
        for body in (b'[{"rate": NaN}]', b'[{"rate": "NaN"}]', b'[{"rate": Infinity}]'):
            with patch_nbu(lambda url, body=body, **kw: response(body)):
                with self.assertRaises(RatesUnavailable, msg=body):
                    NbuRateProvider().fetch(date(2026, 6, 23))
        self.assertEqual(ExchangeRate.objects.count(), 0)

    def test_oversized_response_is_rejected(self):
        big = b'[{"rate": 41.5, "pad": "' + b'x' * 1_000_001 + b'"}]'
        with patch_nbu(lambda url, **kw: response(big)):
            with self.assertRaisesMessage(RatesUnavailable, 'слишком большой'):
                NbuRateProvider().fetch(date(2026, 6, 23))

    def test_task_retries_on_network_error(self):
        with patch_nbu(URLError('timeout')), \
                patch.object(fetch_nbu_rates_task, 'retry', side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                fetch_nbu_rates_task()
        self.assertEqual(retry.call_count, 1)

    def test_task_retries_on_timeout_and_disconnect(self):
        for exc in (TimeoutError('timed out'), http.client.RemoteDisconnected('closed'), OSError('reset')):
            with patch_nbu(exc), patch.object(fetch_nbu_rates_task, 'retry', side_effect=Retry()) as retry:
                with self.assertRaises(Retry):
                    fetch_nbu_rates_task()
            self.assertEqual(retry.call_count, 1)

    def test_command_network_error_is_command_error(self):
        with patch_nbu(TimeoutError('timed out')):
            with self.assertRaisesMessage(CommandError, 'Ошибка запроса к НБУ: TimeoutError'):
                call_command('fetch_nbu_rates')

    def test_success_marks_source_nbu_and_clears_cache(self):
        pricing_cache.get_exchange_rates()
        self.assertIsNotNone(cache.get(pricing_cache.KEYS['exchange']))
        with patch_nbu(nbu_ok):
            updated = fetch_nbu_rates_task()
        self.assertEqual(len(updated), 3)
        rows = {(r.from_currency, r.to_currency): r for r in ExchangeRate.objects.all()}
        self.assertEqual({r.source for r in rows.values()}, {'nbu'})
        self.assertEqual(rows[('USD', 'UAH')].rate, D('41.5'))
        self.assertEqual(rows[('USD', 'EUR')].rate, (D('41.5') / D('45.0')).quantize(D('0.000001')))
        self.assertIsNone(cache.get(pricing_cache.KEYS['exchange']))
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='nbu').last_success_at)

    def test_url_and_timeout_come_from_settings(self):
        with override_settings(NBU_API_URL='https://nbu.example.test/api/', INTEGRATIONS_HTTP_TIMEOUT=7), \
                patch_nbu(nbu_ok) as mocked:
            NbuRateProvider().fetch(date(2026, 6, 23))
        url = mocked.call_args_list[0].args[0]
        self.assertTrue(url.startswith('https://nbu.example.test/api?valcode=USD&date=20260623'), url)
        self.assertEqual(mocked.call_args_list[0].kwargs['timeout'], 7)
        self.assertEqual(http_timeout(), 10)


class ModeTests(CleanCacheTestCase):

    def test_mode_selects_provider_class(self):
        self.assertIsInstance(get_rate_provider(), NbuRateProvider)  # auto = real, ключ не нужен
        with override_settings(NBU_MODE='demo'):
            self.assertIsInstance(get_rate_provider(), DemoRateProvider)
        with override_settings(NBU_MODE='off'):
            self.assertIsNone(get_rate_provider())

    def test_demo_mode_writes_demo_and_never_overwrites_nbu(self):
        from pricing.nbu import fetch_and_save_rates
        today = date.today()
        ExchangeRate.objects.create(from_currency='USD', to_currency='UAH', date=today, rate=D('40'), source='nbu')
        with override_settings(NBU_MODE='demo'):
            updated = fetch_and_save_rates()
        self.assertEqual(updated, ['USD/EUR = 0.92'])  # A12: настоящий USD/UAH не тронут и не заявлен «оновлено»
        usd = ExchangeRate.objects.get(from_currency='USD', to_currency='UAH', date=today)
        self.assertEqual((usd.rate, usd.source), (D('40'), 'nbu'))
        eur = ExchangeRate.objects.get(from_currency='USD', to_currency='EUR', date=today)
        self.assertEqual((eur.rate, eur.source), (D('0.92'), 'demo'))

    def test_off_mode_does_not_call_network(self):
        from pricing.nbu import fetch_and_save_rates
        with override_settings(NBU_MODE='off'), patch_nbu(nbu_ok) as mocked:
            self.assertEqual(fetch_and_save_rates(), [])
        mocked.assert_not_called()

    def test_status_follows_mode(self):
        status = NbuRateProvider().status()
        self.assertEqual((status.mode, status.configured), ('real', True))
        with override_settings(NBU_MODE='off'):
            status = NbuRateProvider().status()
        self.assertEqual((status.mode, status.configured), ('off', False))


class SeedAndCalculatorTests(SeededCase):

    def test_seed_rates_marks_demo(self):
        sources = set(ExchangeRate.objects.values_list('source', flat=True))
        self.assertEqual(sources, {'demo'})
        self.assertEqual(ExchangeRate.objects.get(from_currency='USD', to_currency='UAH').rate, D('41.50'))

    def test_manual_rate_from_admin_defaults_to_manual(self):
        row = ExchangeRate.objects.create(from_currency='EUR', to_currency='UAH', date=date.today(), rate=D('45'))
        self.assertEqual(row.source, 'manual')

    def test_demo_rate_visible_in_calculator_response(self):
        body = self.calc().json()
        self.assertEqual(body['exchange_rate_source'], 'demo')
        self.assertTrue(body['is_demo'])

    def test_real_nbu_rate_removes_demo_mark(self):
        for model in TARIFFS:
            model.objects.update(is_verified=True)
        pricing_cache.invalidate_all()
        self.assertTrue(self.calc().json()['is_demo'])  # курс всё ещё демо
        with patch_nbu(nbu_ok):
            fetch_nbu_rates_task()
        body = self.calc().json()
        self.assertEqual(body['exchange_rate_source'], 'nbu')
        self.assertFalse(body['is_demo'])

    def test_stale_rate_gives_warning(self):
        ExchangeRate.objects.update(date=date.today() - timedelta(days=4))
        pricing_cache.invalidate_all()
        body = self.calc().json()
        self.assertTrue(body['exchange_rate_stale'])
        self.assertIn('застарілий', body['exchange_rate_warning'])

    def test_rate_at_age_limit_is_not_stale(self):
        ExchangeRate.objects.update(date=date.today() - timedelta(days=3))
        pricing_cache.invalidate_all()
        body = self.calc().json()
        self.assertFalse(body['exchange_rate_stale'])
        self.assertIsNone(body['exchange_rate_warning'])

    @override_settings(EXCHANGE_RATE_MAX_AGE_DAYS=10)
    def test_age_limit_comes_from_settings(self):
        ExchangeRate.objects.update(date=date.today() - timedelta(days=5))
        pricing_cache.invalidate_all()
        self.assertFalse(self.calc().json()['exchange_rate_stale'])


class RefreshButtonTests(CleanCacheTestCase):
    URL = '/admin/integrations/status/refresh-nbu/'

    def test_superuser_refreshes_rates(self):
        admin = make_staff(superuser=True)
        self.client.force_login(admin)
        with patch_nbu(nbu_ok):
            resp = self.client.post(self.URL, follow=True)
        self.assertContains(resp, 'Курс оновлено')
        self.assertEqual(ExchangeRate.objects.filter(source='nbu').count(), 3)

    def test_failure_is_shown_without_secrets(self):
        self.client.force_login(make_staff(superuser=True))
        err = URLError('failed https://nbu.test/api?valcode=USD&apikey=sekret-key-777')
        with patch_nbu(err):
            resp = self.client.post(self.URL, follow=True)
        self.assertContains(resp, 'Не вдалося оновити курс НБУ')
        self.assertNotContains(resp, 'sekret-key-777')
        self.assertNotIn('sekret-key-777', IntegrationHealth.objects.get(provider_key='nbu').last_error)
        self.assertEqual(ExchangeRate.objects.count(), 0)

    def test_anonymous_redirected_to_admin_login(self):
        resp = self.client.post(self.URL)
        self.assertRedirects(resp, f'/admin/login/?next={self.URL}', fetch_redirect_response=False)

    def test_regular_user_redirected_to_admin_login(self):
        self.client.force_login(make_user())
        with patch_nbu(nbu_ok) as mocked:
            resp = self.client.post(self.URL)
        self.assertEqual(resp.status_code, 302)
        mocked.assert_not_called()

    def test_get_not_allowed(self):
        self.client.force_login(make_staff(superuser=True))
        self.assertEqual(self.client.get(self.URL).status_code, 405)


class SeedCommandTests(CleanCacheTestCase):
    def test_seed_twice_keeps_nbu_rate(self):
        call_command('seed_rates', verbosity=0)
        ExchangeRate.objects.filter(from_currency='USD', to_currency='UAH').update(rate=D('44'), source='nbu')
        call_command('seed_rates', verbosity=0)
        row = ExchangeRate.objects.get(from_currency='USD', to_currency='UAH')
        self.assertEqual((row.rate, row.source), (D('44'), 'nbu'))


class RefreshButtonPermissionTests(CleanCacheTestCase):
    def test_staff_without_permission_gets_403(self):
        self.client.force_login(make_staff('staff@mail.test'))
        with patch_nbu(nbu_ok) as mocked:
            resp = self.client.post('/admin/integrations/status/refresh-nbu/')
        self.assertEqual(resp.status_code, 403)
        mocked.assert_not_called()


class ReviewFixesTests(CleanCacheTestCase):
    """Аудит 2026-10-25, раздел A: A7, A10, A11, A12."""

    def test_manual_rate_not_overwritten_by_nbu(self):  # A7
        from pricing.nbu import fetch_and_save_rates
        today = date.today()
        ExchangeRate.objects.create(from_currency='USD', to_currency='UAH', date=today, rate=D('40'), source='manual')
        with patch_nbu(nbu_ok):
            updated = fetch_and_save_rates(today)
        row = ExchangeRate.objects.get(from_currency='USD', to_currency='UAH', date=today)
        self.assertEqual((row.rate, row.source), (D('40'), 'manual'))
        self.assertNotIn('USD/UAH = 41.5', updated)  # A12: ручную строку не «оновлено»
        self.assertEqual(len(updated), 2)

    def test_unchanged_rate_is_not_reported_as_updated(self):  # A12
        from pricing.nbu import fetch_and_save_rates
        with patch_nbu(nbu_ok):
            first = fetch_and_save_rates(date(2026, 6, 23))
            second = fetch_and_save_rates(date(2026, 6, 23))
        self.assertEqual(len(first), 3)
        self.assertEqual(second, [])

    def test_error_on_second_currency_rolls_back_all(self):  # A12
        from pricing import nbu
        real_save = nbu._save
        calls = []

        def flaky(quote, rate_date):
            calls.append(quote)
            if len(calls) == 2:
                raise RuntimeError('db down')
            return real_save(quote, rate_date)

        with patch_nbu(nbu_ok), patch.object(nbu, '_save', side_effect=flaky):
            with self.assertRaisesMessage(RuntimeError, 'db down'):
                nbu.fetch_and_save_rates(date(2026, 6, 23))
        self.assertEqual(ExchangeRate.objects.count(), 0)
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='nbu').last_error_at)

    def test_refresh_button_reports_zero_when_nothing_changed(self):  # A12
        self.client.force_login(make_staff(superuser=True))
        with patch_nbu(nbu_ok):
            self.client.post('/admin/integrations/status/refresh-nbu/')
            resp = self.client.post('/admin/integrations/status/refresh-nbu/', follow=True)
        self.assertContains(resp, 'Курс оновлено 0')

    def test_empty_nbu_api_url_env_falls_back_to_default(self):  # A10
        import os
        import subprocess
        import sys
        env = {**os.environ, 'NBU_API_URL': '', 'DATABASE_URL': '', 'REDIS_URL': '', 'DJANGO_SETTINGS_MODULE': 'core.settings'}
        code = 'from django.conf import settings; print(settings.NBU_API_URL)'
        out = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), 'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange')


class RateStaleTests(SeededCase):

    def test_old_eur_rate_makes_response_stale(self):  # A11
        today = date.today()
        ExchangeRate.objects.filter(from_currency='USD', to_currency='UAH').update(date=today)
        ExchangeRate.objects.filter(from_currency='USD', to_currency='EUR').update(date=today - timedelta(days=5))
        pricing_cache.invalidate_all()
        body = self.calc().json()
        self.assertTrue(body['exchange_rate_stale'])
        self.assertIn((today - timedelta(days=5)).strftime('%d.%m.%Y'), body['exchange_rate_warning'])


class ExchangeRateInfoUnitTests(SimpleTestCase):
    """A13: чистая функция калькулятора, без БД."""

    def rate(self, day, source='nbu'):
        return SimpleNamespace(date=day, source=source)

    def test_oldest_of_two_dates_decides(self):
        today = date(2026, 6, 23)
        info = exchange_rate_info(self.rate(today), self.rate(today - timedelta(days=4)), today, 3)
        self.assertTrue(info['exchange_rate_stale'])
        self.assertIn('4 дн.', info['exchange_rate_warning'])

    def test_limit_is_not_stale(self):
        today = date(2026, 6, 23)
        info = exchange_rate_info(self.rate(today), self.rate(today - timedelta(days=3)), today, 3)
        self.assertEqual(
            info, {'exchange_rate_source': 'nbu', 'exchange_rate_stale': False, 'exchange_rate_warning': None},
        )

    def test_any_demo_rate_marks_source_demo(self):
        today = date(2026, 6, 23)
        info = exchange_rate_info(self.rate(today), self.rate(today, 'demo'), today, 3)
        self.assertEqual(info['exchange_rate_source'], 'demo')


class ExchangeRateAdminSaveTests(CleanCacheTestCase):

    def _row(self, source='nbu'):
        return ExchangeRate.objects.create(
            from_currency='USD', to_currency='UAH', date=date(2026, 6, 23), rate=D('41.5'), source=source,
        )

    def _post_change(self, row, rate):
        self.client.force_login(make_staff(superuser=True))
        return self.client.post(f'/admin/pricing/exchangerate/{row.pk}/change/', {
            'from_currency': 'USD', 'to_currency': 'UAH', 'date': '2026-06-23', 'rate': rate, 'source': 'nbu',
        })

    def test_changing_rate_in_admin_marks_manual_and_nbu_keeps_it(self):
        row = self._row()
        self.assertEqual(self._post_change(row, '42.5').status_code, 302)
        row.refresh_from_db()
        self.assertEqual((row.rate, row.source), (D('42.5'), 'manual'))
        from pricing.nbu import fetch_and_save_rates
        with patch_nbu(nbu_ok):
            fetch_and_save_rates(date(2026, 6, 23))
        row.refresh_from_db()
        self.assertEqual((row.rate, row.source), (D('42.5'), 'manual'))

    def test_saving_without_rate_change_keeps_source(self):
        row = self._row()
        self.assertEqual(self._post_change(row, '41.5').status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.source, 'nbu')
