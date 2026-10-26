"""Задача 6.4: публичная конфигурация в GET /api/v1/site-settings/ (лимиты, имя бота, признак демо-тарифов)."""
import re

from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from pricing import cache as pricing_cache
from pricing.models import (
    AuctionFeeTier,
    AuctionFixedFee,
    CustomsCalcRule,
    CustomsExciseRate,
    EuToUaDeliveryRate,
    ExchangeRate,
    OceanFreightRate,
    PensionFundBracket,
    UsLandRoute,
)
from site_settings.models import SiteSettings
from tests.base import CleanCacheTestCase

URL = '/api/v1/site-settings/'
SECRET_HINTS = re.compile(r'token|secret|key|password|admin_email', re.I)


def get():
    resp = APIClient().get(URL)
    assert resp.status_code == 200, resp.status_code
    return resp.json()


class PublicConfigTests(CleanCacheTestCase):
    @override_settings(LOCAL_LISTING_MAX_ACTIVE=7, LOCAL_LISTING_EXPIRY_DAYS=45, LOCAL_LISTING_MAX_PHOTOS=9)
    def test_limits_from_settings(self):
        body = get()
        self.assertEqual((body['local_listing_max_active'], body['local_listing_expiry_days'],
                          body['local_listing_max_photos']), (7, 45, 9))

    @override_settings(TELEGRAM_BOT_USERNAME='@test_bot')
    def test_bot_username_without_at(self):
        self.assertEqual(get()['telegram_bot_username'], 'test_bot')

    def test_no_secret_fields(self):
        leaked = [k for k in get() if SECRET_HINTS.search(k)]
        self.assertEqual(leaked, [])

    def test_admin_save_refreshes_cached_answer(self):
        self.assertNotEqual(get()['phone'], '+380671112233')  # прогрели кэш
        obj = SiteSettings.load()
        obj.phone = '+380671112233'
        obj.save()
        self.assertEqual(get()['phone'], '+380671112233')

    @override_settings(PAYMENTS_ENABLED=False)
    def test_payments_disabled(self):
        self.assertIs(get()['payments_enabled'], False)

    @override_settings(PAYMENTS_ENABLED=True)
    def test_payments_enabled(self):
        self.assertIs(get()['payments_enabled'], True)


class TariffsDemoTests(CleanCacheTestCase):
    """«Тестові тарифи» у підвалі й на головній — той самий признак, що в демо-банера калькулятора (2.6)."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def test_seed_is_demo(self):
        self.assertIs(get()['tariffs_demo'], True)

    def test_all_verified_not_demo(self):
        for model in (AuctionFeeTier, AuctionFixedFee, UsLandRoute, OceanFreightRate, EuToUaDeliveryRate,
                      CustomsExciseRate, PensionFundBracket, CustomsCalcRule):
            model.objects.update(is_verified=True)
        ExchangeRate.objects.update(source='nbu')
        pricing_cache.invalidate_all()
        self.assertIs(get()['tariffs_demo'], False)
