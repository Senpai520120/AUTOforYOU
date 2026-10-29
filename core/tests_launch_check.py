"""Тесты manage.py launch_check (задача 7.7a): на каждую проверку - «плохое» и «хорошее» значение.

Команда только читает: запись в БД проверяется через CaptureQueriesContext (все запросы - SELECT).
Значения секретов здесь явно фиктивные (`test-only-...`).
"""
import os
import time
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from core import launch
from leads.models import LeadNotificationSettings
from metrics.models import DailyMetric
from pricing.models import AuctionFeeTier, CustomsCalcRule, ExchangeRate, UaDeliveryRate
from site_settings.models import SiteSettings
from task_ledger.models import FailedTask
from tests.base import CleanCacheTestCase
from tests.factories import make_broker, make_local_listing, make_moderator, make_user
from users.models import CustomUser

SECRET = 'test-only-secret-key-0123456789-abcdefghijklmnop-qrstuvwx'
PASSWORD = 'test-only-db-password'

GOOD_SETTINGS = dict(
    DEBUG=False, SECRET_KEY=SECRET,
    ALLOWED_HOSTS=['shop.example.test'], CORS_ALLOWED_ORIGINS=['https://shop.example.test'],
    CSRF_TRUSTED_ORIGINS=['https://shop.example.test'], SITE_URL='https://shop.example.test',
    EMAIL_HOST='smtp.example.test', EMAIL_HOST_USER='mailer', EMAIL_HOST_PASSWORD='test-only-mail-password',
    DEFAULT_FROM_EMAIL='noreply@shop.example.test',
    ANTISPAM_MODE='hard', C2C_ENABLED=False, C2C_PUBLIC_POSTING_ENABLED=False, PAYMENTS_ENABLED=False,
    LOTS_ENABLED=False, B2B_ENABLED=False, DEALERS_ENABLED=False, SHIPMENTS_ENABLED=False,
    VIN_REPORTS_ENABLED=False, LEGACY_CARS_API_ENABLED=False,
    CAPTCHA_PROVIDER='turnstile', TURNSTILE_SECRET_KEY='test-only-turnstile-secret',
    LOT_PHOTO_ALLOWED_HOSTS=[], CARVERTICAL_PARTNER_URL='https://partner.example.test/ref',
    TELEGRAM_BROKER_CHAT_ID='', BROKER_NOTIFY_EMAIL='',
)
GOOD_ENV = dict(
    DOMAIN='shop.example.test', DATABASE_URL=f'postgresql://app:{PASSWORD}@db:5432/app',
    POSTGRES_PASSWORD=PASSWORD, REDIS_URL='redis://:test-only-redis@redis:6379/0', REDIS_PASSWORD='test-only-redis',
    SENTRY_DSN='https://test-only-key@sentry.example.test/1',
    BACKUP_S3_BUCKET='test-only-backups', BACKUP_S3_ENDPOINT_URL='https://r2.example.test',
    BACKUP_S3_ACCESS_KEY_ID='test-only-access', BACKUP_S3_SECRET_ACCESS_KEY='test-only-s3-secret',
    BACKUP_ENCRYPTION_PASSPHRASE='test-only-passphrase', BACKUP_DIR='', C2C_SEED_THRESHOLD='',
)
SECRET_VALUES = (
    SECRET, PASSWORD, 'test-only-mail-password', 'test-only-turnstile-secret', 'test-only-redis',
    'test-only-key', 'test-only-s3-secret', 'test-only-passphrase', 'test-only-access',
)


class LaunchCheckTestCase(CleanCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0, stdout=StringIO())
        call_command('seed_auction_fees', '--clear', verbosity=0, stdout=StringIO())
        # Singleton может уже существовать (data-миграция): обновляем, а не создаём.
        SiteSettings.objects.update_or_create(pk=1, defaults=dict(
            owner_legal_form='fop', owner_legal_name='ФОП Тестовий', owner_code='1234567890',
            owner_address='м. Київ, вул. Тестова, 1', support_email='support@shop.example.test',
            privacy_email='privacy@shop.example.test', phone='+380000000000', partner_name='Партнер Тест',
            legal_docs_version='2026-10-01', legal_docs_approved=True, data_retention_years=5,
        ))
        LeadNotificationSettings.objects.update_or_create(pk=1, defaults=dict(
            telegram_chat_id='-1001234567890', broker_emails='broker@shop.example.test'))
        make_broker()
        make_moderator()

    def run_check(self, *, env=None, args=(), **overrides):
        """Запускает команду; возвращает (код, вывод). CommandError с returncode 1 = код возврата 1."""
        out = StringIO()
        with mock.patch.dict(os.environ, {**GOOD_ENV, **(env or {})}), \
                override_settings(**{**GOOD_SETTINGS, **overrides}):
            try:
                call_command('launch_check', *args, stdout=out)
                code = 0
            except CommandError as exc:
                code = exc.returncode
        return code, out.getvalue()

    def assertOk(self, code, out):
        self.assertEqual(code, 0, out)

    def assertFails(self, code, out, *texts):
        self.assertEqual(code, 1, out)
        for text in texts:
            self.assertIn(text, out)


class GoodStateTests(LaunchCheckTestCase):
    def test_good_state_returns_zero(self):
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('Підсумок: помилок 0', out)

    def test_output_never_contains_secret_values(self):
        _code, out = self.run_check()
        for secret in SECRET_VALUES:
            self.assertNotIn(secret, out)

    def test_wave_two_is_a_separate_task(self):
        with self.assertRaisesMessage(CommandError, '7.7b'):
            call_command('launch_check', '--wave', '2', stdout=StringIO())

    def test_default_wave_is_one(self):
        _code, out = self.run_check()
        self.assertIn('режим ВОЛНА-1', out)


class NoDatabaseWritesTests(LaunchCheckTestCase):
    def assertOnlySelects(self, queries):
        self.assertGreater(len(queries), 0)
        for query in queries:
            self.assertTrue(query['sql'].lstrip().upper().startswith('SELECT'), query['sql'])

    def test_only_selects_with_filled_database(self):
        with CaptureQueriesContext(connection) as queries:
            code, out = self.run_check()
        self.assertOk(code, out)
        self.assertOnlySelects(queries.captured_queries)

    def test_only_selects_with_empty_database_and_no_singletons(self):
        SiteSettings.objects.all().delete()
        LeadNotificationSettings.objects.all().delete()
        with CaptureQueriesContext(connection) as queries:
            code, out = self.run_check()
        self.assertFails(code, out)
        self.assertOnlySelects(queries.captured_queries)
        self.assertFalse(SiteSettings.objects.exists())
        self.assertFalse(LeadNotificationSettings.objects.exists())


class RequiredVarsTests(LaunchCheckTestCase):
    def test_every_required_var_is_reported_when_empty(self):
        for group, items in launch.REQUIRED_VARS.items():
            for name, source, _hint in items:
                with self.subTest(name=name):
                    if source == launch.ENV:
                        code, out = self.run_check(env={name: ''})
                    elif name == 'SECRET_KEY':
                        continue  # Django не даёт задать пустой SECRET_KEY даже в override_settings; слабый - ниже
                    else:
                        empty = [] if name in ('ALLOWED_HOSTS', 'CORS_ALLOWED_ORIGINS', 'CSRF_TRUSTED_ORIGINS') else ''
                        code, out = self.run_check(**{name: empty})
                    self.assertFails(code, out, f'{name}: не задано')

    def test_all_empty_lists_all_names(self):
        env = {name: '' for name in launch.required_var_names() if name in GOOD_ENV}
        settings_empty = {name: '' for name in launch.required_var_names()
                          if name in GOOD_SETTINGS and name != 'SECRET_KEY'}
        settings_empty['SECRET_KEY'] = 'short'
        for name in ('ALLOWED_HOSTS', 'CORS_ALLOWED_ORIGINS', 'CSRF_TRUSTED_ORIGINS'):
            settings_empty[name] = []
        code, out = self.run_check(env=env, **settings_empty)
        self.assertEqual(code, 1, out)
        for name in launch.required_var_names():
            self.assertIn(name, out)

    def test_placeholder_values_are_errors(self):
        code, out = self.run_check(env={'DATABASE_URL': 'postgres://app:<POSTGRES_PASSWORD>@db:5432/app'})
        self.assertFails(code, out, 'DATABASE_URL: заглушка')
        code, out = self.run_check(EMAIL_HOST='your-smtp-host')
        self.assertFails(code, out, 'EMAIL_HOST: заглушка')

    def test_weak_secret_key_is_error(self):
        for key in ('short', 'django-insecure-' + 'x' * 60, 'REPLACE-' + 'y' * 60):
            with self.subTest(key=key[:12]):
                code, out = self.run_check(SECRET_KEY=key)
                self.assertFails(code, out, 'SECRET_KEY: заглушка або слабке значення')

    def test_localhost_only_allowed_hosts_is_error_in_prod_only(self):
        code, out = self.run_check(ALLOWED_HOSTS=['localhost', '127.0.0.1'])
        self.assertFails(code, out, 'ALLOWED_HOSTS: лише localhost-хости')
        code, out = self.run_check(ALLOWED_HOSTS=['localhost'], DEBUG=True)
        self.assertOk(code, out)


class FlagsTests(LaunchCheckTestCase):
    def test_payments_enabled_in_prod_is_error(self):
        code, out = self.run_check(PAYMENTS_ENABLED=True)
        self.assertFails(code, out, 'PAYMENTS_ENABLED=true: платежі на ВОЛНІ-1 мають бути вимкнені')

    def test_payments_enabled_in_debug_is_warning_only_for_flag(self):
        # Тарифы из seed не подтверждены - ошибку даёт именно это, не флаг (см. TariffsTests).
        AuctionFeeTier.objects.update(is_verified=True)
        from pricing import models as pm
        for model in (pm.AuctionFixedFee, pm.UsLandRoute, pm.OceanFreightRate, pm.EuToUaDeliveryRate,
                      pm.CustomsExciseRate, pm.PensionFundBracket, pm.UaDeliveryRate, pm.BrokerServiceFee):
            model.objects.update(is_verified=True)
        CustomsCalcRule.objects.update(confirmed_by_broker=True)
        code, out = self.run_check(PAYMENTS_ENABLED=True, DEBUG=True)
        self.assertOk(code, out)
        self.assertIn('PAYMENTS_ENABLED=true (режим розробки)', out)

    def test_legacy_checkout_in_prod_is_error(self):
        code, out = self.run_check(PAYMENTS_LEGACY_CHECKOUT_ENABLED=True)
        self.assertFails(code, out, 'PAYMENTS_LEGACY_CHECKOUT_ENABLED=true')

    def test_legacy_checkout_off_is_clean(self):
        code, out = self.run_check(PAYMENTS_LEGACY_CHECKOUT_ENABLED=False)
        self.assertOk(code, out)
        self.assertNotIn('PAYMENTS_LEGACY_CHECKOUT_ENABLED', out)

    def test_sandbox_with_enabled_payments_in_prod_warns(self):
        # PAYMENTS_ENABLED=true в проде само даёт ошибку; нас интересует именно предупреждение про sandbox.
        _, out = self.run_check(PAYMENTS_ENABLED=True, LIQPAY_SANDBOX=True)
        self.assertIn('LIQPAY_SANDBOX=true при увімкнених платежах', out)

    def test_sandbox_false_with_enabled_payments_does_not_warn(self):
        _, out = self.run_check(PAYMENTS_ENABLED=True, LIQPAY_SANDBOX=False)
        self.assertNotIn('LIQPAY_SANDBOX=true', out)

    def test_real_keys_in_sandbox_mode_in_prod_is_error(self):
        code, out = self.run_check(LIQPAY_PUBLIC_KEY='i12345live', LIQPAY_PRIVATE_KEY='test-only-liqpay-private',
                                   LIQPAY_MODE='auto', LIQPAY_SANDBOX=True)
        self.assertFails(code, out, 'бойові ключі в тестовому режимі')

    def test_sandbox_keys_in_sandbox_mode_are_fine(self):
        code, out = self.run_check(LIQPAY_PUBLIC_KEY='sandbox_i123', LIQPAY_PRIVATE_KEY='test-only-liqpay-private',
                                   LIQPAY_MODE='auto', LIQPAY_SANDBOX=True)
        self.assertOk(code, out)

    def test_real_keys_in_real_mode_are_fine(self):
        code, out = self.run_check(LIQPAY_PUBLIC_KEY='i12345live', LIQPAY_PRIVATE_KEY='test-only-liqpay-private',
                                   LIQPAY_MODE='auto', LIQPAY_SANDBOX=False)
        self.assertOk(code, out)

    def test_real_keys_in_sandbox_mode_in_debug_not_error(self):
        code, out = self.run_check(LIQPAY_PUBLIC_KEY='i12345live', LIQPAY_PRIVATE_KEY='test-only-liqpay-private',
                                   LIQPAY_MODE='auto', LIQPAY_SANDBOX=True, DEBUG=True)
        self.assertNotIn('бойові ключі в тестовому режимі', out)

    def test_public_posting_in_prod_is_error(self):
        code, out = self.run_check(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=True)
        self.assertFails(code, out, 'C2C_PUBLIC_POSTING_ENABLED=true')

    def test_public_posting_in_debug_is_allowed(self):
        code, out = self.run_check(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=True, DEBUG=True)
        self.assertOk(code, out)

    def test_seeding_mode_c2c_enabled_without_posting_is_ok(self):
        code, out = self.run_check(C2C_ENABLED=True, C2C_PUBLIC_POSTING_ENABLED=False)
        self.assertOk(code, out)
        self.assertIn('режим «засів»', out)

    def test_frozen_modules_enabled_are_warnings(self):
        for name in launch.FROZEN_MODULE_FLAGS:
            with self.subTest(name=name):
                code, out = self.run_check(**{name: True})
                self.assertOk(code, out)
                self.assertIn(f'{name}=true: модуль заморожено', out)

    def test_frozen_modules_off_give_no_warning(self):
        _code, out = self.run_check()
        self.assertNotIn('модуль заморожено на ВОЛНІ-1', out)

    def test_antispam_soft_in_prod_is_error(self):
        for mode in ('soft', 'off'):
            with self.subTest(mode=mode):
                code, out = self.run_check(ANTISPAM_MODE=mode)
                self.assertFails(code, out, f'ANTISPAM_MODE={mode}: у проді має бути hard')

    def test_antispam_soft_in_debug_is_allowed(self):
        code, out = self.run_check(ANTISPAM_MODE='soft', DEBUG=True)
        self.assertOk(code, out)

    def test_antispam_hard_is_ok(self):
        _code, out = self.run_check()
        self.assertIn('ANTISPAM_MODE=hard', out)


class CaptchaTests(LaunchCheckTestCase):
    def test_empty_turnstile_secret_is_warning_not_error(self):
        code, out = self.run_check(TURNSTILE_SECRET_KEY='')
        self.assertOk(code, out)
        self.assertIn('тільки honeypot', out)

    def test_honeypot_provider_is_warning_not_error(self):
        code, out = self.run_check(CAPTCHA_PROVIDER='honeypot')
        self.assertOk(code, out)
        self.assertIn('тільки honeypot', out)

    def test_turnstile_with_secret_has_no_warning(self):
        _code, out = self.run_check()
        self.assertNotIn('тільки honeypot', out)
        self.assertIn('Капча Turnstile: ключ задано', out)

    def test_captcha_off_in_prod_is_error(self):
        code, out = self.run_check(CAPTCHA_PROVIDER='off')
        self.assertFails(code, out, 'CAPTCHA_PROVIDER=off при DEBUG=false')

    def test_captcha_off_in_debug_is_not_error(self):
        code, out = self.run_check(CAPTCHA_PROVIDER='off', DEBUG=True)
        self.assertOk(code, out)


class IntegrationsTests(LaunchCheckTestCase):
    def test_registry_statuses_are_listed(self):
        _code, out = self.run_check()
        for key in ('nbu', 'email', 'telegram', 'liqpay', 'ga4', 'cloudflare_analytics'):
            self.assertIn(f'({key}): режим', out)

    def test_disabled_analytics_is_info_not_warning(self):
        _code, out = self.run_check(GA4_MEASUREMENT_ID='', CLOUDFLARE_ANALYTICS_TOKEN='')
        self.assertIn('[ІНФО   ] Google Analytics 4 (ga4)', out)
        self.assertNotIn('[УВАГА  ] Google Analytics 4', out)

    def test_unconfigured_telegram_is_warning(self):
        code, out = self.run_check(TELEGRAM_BOT_TOKEN='')
        self.assertOk(code, out)
        self.assertIn('[УВАГА  ] Telegram (telegram)', out)

    def test_configured_telegram_is_ok(self):
        _code, out = self.run_check(TELEGRAM_BOT_TOKEN='123456789:test-only-telegram-token-0123456789ab',
                                    TELEGRAM_MODE='real')
        self.assertNotIn('[УВАГА  ] Telegram (telegram)', out)
        self.assertNotIn('test-only-telegram-token', out)

    def test_liqpay_unconfigured_is_info_while_payments_off(self):
        _code, out = self.run_check()
        self.assertIn('[ІНФО   ] LiqPay (платежі) (liqpay)', out)

    def test_frozen_vin_modules_are_info(self):
        _code, out = self.run_check()
        self.assertIn('модуль заморожено', out)
        self.assertNotIn('[УВАГА  ] VIN-звіт', out)


class CarVerticalTests(LaunchCheckTestCase):
    def test_empty_partner_url_is_warning_with_exit_zero(self):
        code, out = self.run_check(CARVERTICAL_PARTNER_URL='')
        self.assertOk(code, out)
        self.assertIn('партнерське посилання carVertical не задано, блок не показується', out)

    def test_partner_url_set_is_ok(self):
        _code, out = self.run_check()
        self.assertNotIn('партнерське посилання carVertical не задано', out)


class SiteSettingsTests(LaunchCheckTestCase):
    def test_missing_singleton_is_error(self):
        SiteSettings.objects.all().delete()
        code, out = self.run_check()
        self.assertFails(code, out, 'Налаштування сайту (адмінка) ще не створені')

    def test_each_requisite_empty_is_error(self):
        fields = ('owner_legal_form', 'owner_legal_name', 'owner_code', 'owner_address', 'support_email',
                  'privacy_email', 'phone')
        for field in fields:
            with self.subTest(field=field):
                SiteSettings.objects.filter(pk=1).update(**{field: ''})
                code, out = self.run_check()
                self.assertFails(code, out, 'не заповнено реквізити/контакти')
                SiteSettings.objects.filter(pk=1).update(owner_legal_form='fop', owner_legal_name='ФОП Тестовий',
                                                         owner_code='1234567890', owner_address='м. Київ',
                                                         support_email='s@shop.example.test',
                                                         privacy_email='p@shop.example.test', phone='+380000000000')

    def test_empty_partner_name_is_error_with_exact_text(self):
        SiteSettings.objects.filter(pk=1).update(partner_name='')
        code, out = self.run_check()
        self.assertFails(code, out, 'назва партнера не заповнена: чекбокс згоди на передачу контактів неактивний')

    def test_empty_legal_version_is_error(self):
        SiteSettings.objects.filter(pk=1).update(legal_docs_version='')
        code, out = self.run_check()
        self.assertFails(code, out, 'версія юридичних документів не задана')

    def test_unapproved_docs_and_missing_retention_are_warnings(self):
        SiteSettings.objects.filter(pk=1).update(legal_docs_approved=False, data_retention_years=None)
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('не відмічені як перевірені юристом', out)
        self.assertIn('строк зберігання платіжних документів не заданий', out)

    def test_filled_settings_give_no_site_settings_errors(self):
        _code, out = self.run_check()
        self.assertIn('реквізити й контакти заповнені', out)
        self.assertNotIn('не відмічені як перевірені юристом', out)


class TariffsTests(LaunchCheckTestCase):
    def test_missing_required_tariff_is_error(self):
        AuctionFeeTier.objects.all().delete()
        code, out = self.run_check()
        self.assertFails(code, out, 'немає активних записів «аукціонні збори»')

    def test_expired_tariff_counts_as_missing(self):
        AuctionFeeTier.objects.update(valid_to=date.today() - timedelta(days=1))
        code, out = self.run_check()
        self.assertFails(code, out, 'немає активних записів «аукціонні збори»')

    def test_missing_optional_tariff_is_warning(self):
        UaDeliveryRate.objects.all().delete()
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('немає активних записів «доставка по Україні»', out)

    def test_no_exchange_rate_is_error(self):
        ExchangeRate.objects.all().delete()
        code, out = self.run_check()
        self.assertFails(code, out, 'Курси валют: немає жодного курсу')

    def test_unconfirmed_tariffs_are_warning_when_payments_off(self):
        AuctionFeeTier.objects.update(is_verified=False)
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('[УВАГА  ] Тарифи не підтверджені', out)

    def test_unconfirmed_tariffs_are_error_when_payments_enabled(self):
        AuctionFeeTier.objects.update(is_verified=False)
        # DEBUG=true: сам флаг PAYMENTS_ENABLED тогда только предупреждение, ошибку даёт именно неподтверждённый тариф.
        code, out = self.run_check(PAYMENTS_ENABLED=True, DEBUG=True)
        self.assertFails(code, out, '[ПОМИЛКА] Тарифи не підтверджені')

    def test_unreconciled_customs_rule_is_reported(self):
        CustomsCalcRule.objects.update(confirmed_by_broker=False)
        if not CustomsCalcRule.objects.exists():
            CustomsCalcRule.objects.create(valid_from=date(2000, 1, 1))
        _code, out = self.run_check()
        self.assertIn('правило розмитнення (не звірено з брокером)', out)

    def test_all_confirmed_tariffs_have_no_warning(self):
        from pricing import models as pm
        for model in (pm.AuctionFeeTier, pm.AuctionFixedFee, pm.UsLandRoute, pm.OceanFreightRate,
                      pm.EuToUaDeliveryRate, pm.CustomsExciseRate, pm.PensionFundBracket, pm.UaDeliveryRate,
                      pm.BrokerServiceFee):
            model.objects.update(is_verified=True)
        CustomsCalcRule.objects.update(confirmed_by_broker=True)
        code, out = self.run_check(PAYMENTS_ENABLED=True, DEBUG=True)
        self.assertOk(code, out)
        self.assertIn('Усі активні тарифи підтверджені', out)


class RolesTests(LaunchCheckTestCase):
    def test_no_broker_is_warning(self):
        CustomUser.objects.filter(role='broker').delete()
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('Немає користувача з роллю брокер', out)
        self.assertNotIn('Немає користувача з роллю модератор', out)

    def test_no_moderator_is_warning(self):
        CustomUser.objects.filter(role='moderator').delete()
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('Немає користувача з роллю модератор', out)
        self.assertNotIn('Немає користувача з роллю брокер', out)

    def test_inactive_broker_does_not_count(self):
        CustomUser.objects.filter(role='broker').update(is_active=False)
        _code, out = self.run_check()
        self.assertIn('Немає користувача з роллю брокер', out)

    def test_both_roles_present_give_ok(self):
        _code, out = self.run_check()
        self.assertIn('Є користувач з роллю брокер', out)
        self.assertIn('Є користувач з роллю модератор', out)


class LeadNotificationTests(LaunchCheckTestCase):
    def test_no_chat_id_anywhere_is_error(self):
        LeadNotificationSettings.objects.filter(pk=1).update(telegram_chat_id='')
        code, out = self.run_check()
        self.assertFails(code, out, 'TELEGRAM_BROKER_CHAT_ID не задано')

    def test_env_chat_id_is_enough(self):
        LeadNotificationSettings.objects.filter(pk=1).update(telegram_chat_id='')
        code, out = self.run_check(TELEGRAM_BROKER_CHAT_ID='-1009999999999')
        self.assertOk(code, out)

    def test_no_backup_email_anywhere_is_error(self):
        LeadNotificationSettings.objects.filter(pk=1).update(broker_emails='')
        code, out = self.run_check()
        self.assertFails(code, out, 'Резервний email брокера не задано')

    def test_env_backup_email_is_enough(self):
        LeadNotificationSettings.objects.filter(pk=1).update(broker_emails='')
        code, out = self.run_check(BROKER_NOTIFY_EMAIL='broker@shop.example.test')
        self.assertOk(code, out)


class PhotoModeTests(LaunchCheckTestCase):
    def test_photo_mode_off_is_ok(self):
        _code, out = self.run_check()
        self.assertIn('Режим фото лотів: off', out)

    def test_photo_mode_on_is_warning(self):
        code, out = self.run_check(LOT_PHOTO_ALLOWED_HOSTS=['cdn.example.test'])
        self.assertOk(code, out)
        self.assertIn('Режим фото лотів: on', out)


class SeedingTests(LaunchCheckTestCase):
    def test_not_checked_when_c2c_disabled(self):
        _code, out = self.run_check(args=('--seed-threshold', '5'))
        self.assertNotIn('засіву', out)

    def test_below_threshold_is_warning(self):
        code, out = self.run_check(C2C_ENABLED=True, args=('--seed-threshold', '5'))
        self.assertOk(code, out)
        self.assertIn('активних оголошень 0 - менше порога засіву 5', out)

    def test_at_threshold_is_ok(self):
        owner = make_user()
        for _ in range(2):
            make_local_listing(owner)
        _code, out = self.run_check(C2C_ENABLED=True, args=('--seed-threshold', '2'))
        self.assertIn('Активних оголошень 2 (поріг засіву 2)', out)
        self.assertNotIn('менше порога засіву', out)

    def test_inactive_listings_do_not_count(self):
        make_local_listing(make_user(), status='draft')
        _code, out = self.run_check(C2C_ENABLED=True, args=('--seed-threshold', '1'))
        self.assertIn('активних оголошень 0 - менше порога засіву 1', out)

    def test_threshold_from_env(self):
        _code, out = self.run_check(C2C_ENABLED=True, env={'C2C_SEED_THRESHOLD': '3'})
        self.assertIn('менше порога засіву 3', out)

    def test_no_threshold_is_skipped_with_info(self):
        code, out = self.run_check(C2C_ENABLED=True)
        self.assertOk(code, out)
        self.assertIn('Поріг «засіву» не задано', out)


class BackupMarkTests(LaunchCheckTestCase):
    def test_mark_unavailable_is_info(self):
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('Мітка останнього бекапу (.last_success) недоступна', out)

    def test_fresh_mark_is_ok(self):
        with TemporaryDirectory() as tmp:
            Path(tmp, '.last_success').write_text('ok')
            code, out = self.run_check(env={'BACKUP_DIR': tmp})
        self.assertOk(code, out)
        self.assertIn('Останній успішний бекап свіжий', out)

    def test_stale_mark_is_warning(self):
        with TemporaryDirectory() as tmp:
            mark = Path(tmp, '.last_success')
            mark.write_text('ok')
            old = time.time() - 3 * 24 * 3600
            os.utime(mark, (old, old))
            code, out = self.run_check(env={'BACKUP_DIR': tmp})
        self.assertOk(code, out)
        self.assertIn('Останній успішний бекап старший', out)


class MetricsAndTasksTests(LaunchCheckTestCase):
    def test_no_metrics_is_warning(self):
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('Лічильники (8.7): записів ще немає', out)

    def test_fresh_metric_is_ok(self):
        DailyMetric.objects.create(date=date.today(), key='lead', value=1)
        _code, out = self.run_check()
        self.assertIn('Лічильники (8.7): останній запис', out)
        self.assertNotIn('записів ще немає', out)
        self.assertNotIn('запис, схоже, не працює', out)

    def test_stale_metric_is_warning(self):
        DailyMetric.objects.create(date=date.today() - timedelta(days=30), key='lead', value=1)
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('запис, схоже, не працює', out)

    def test_failed_tasks_are_counted_as_info(self):
        FailedTask.objects.create(task_name='x.y')
        FailedTask.objects.create(task_name='x.z')
        code, out = self.run_check()
        self.assertOk(code, out)
        self.assertIn('[ІНФО   ] Невдалі Celery-завдання (8.9) у журналі: 2', out)
