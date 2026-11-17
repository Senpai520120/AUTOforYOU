from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from tests.base import CleanCacheTestCase
from tests.factories import make_staff

from .models import SiteSettings
from .serializers import PublicSiteSettingsSerializer

URL = '/api/v1/site-settings/'

OWNER = dict(owner_legal_form='fop', owner_legal_name='ФОП Іваненко І. І.',
             owner_code='1234567890', owner_address='м. Київ, вул. Тестова, 1')


class SingletonTests(TestCase):
    def test_migration_creates_row_pk1(self):
        self.assertEqual(list(SiteSettings.objects.values_list('pk', flat=True)), [1])

    def test_second_instance_saved_into_pk1(self):
        SiteSettings(phone='+380501112233').save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.objects.get().phone, '+380501112233')

    def test_defaults(self):
        for s in (SiteSettings.load(), SiteSettings()):
            self._check_defaults(s)

    def _check_defaults(self, s):
        self.assertEqual(s.log_retention_days, 90)
        self.assertEqual(s.account_deletion_grace_days, 14)
        self.assertIsNone(s.data_retention_years)
        self.assertEqual(s.legal_docs_version, '')
        self.assertFalse(s.legal_docs_reconsent_required)
        self.assertFalse(s.legal_docs_approved)
        self.assertEqual(s.partner_name, '')


class AdminTests(TestCase):
    def setUp(self):
        self.staff = make_staff(superuser=True)
        self.client.force_login(self.staff)

    def test_changelist_redirects_to_form(self):
        r = self.client.get('/admin/site_settings/sitesettings/')
        self.assertRedirects(r, reverse('admin:site_settings_sitesettings_change', args=[1]),
                             fetch_redirect_response=False)

    def test_changelist_forbidden_without_perms(self):
        self.client.force_login(make_staff())
        r = self.client.get('/admin/site_settings/sitesettings/')
        self.assertEqual(r.status_code, 403)

    def test_delete_forbidden(self):
        r = self.client.post(reverse('admin:site_settings_sitesettings_delete', args=[1]), {'post': 'yes'})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(SiteSettings.objects.filter(pk=1).exists())

    def test_add_forbidden_when_row_exists(self):
        r = self.client.get(reverse('admin:site_settings_sitesettings_add'))
        self.assertEqual(r.status_code, 403)


class ValidationTests(TestCase):
    def _clean(self, **kw):
        SiteSettings(**kw).full_clean()

    def test_owner_code_8_and_10_digits_ok(self):
        self._clean(owner_code='12345678')
        self._clean(owner_code='1234567890')

    def test_owner_code_letters_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._clean(owner_code='12ab')
        self.assertIn('owner_code', ctx.exception.message_dict)

    def test_owner_code_wrong_length_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self._clean(owner_code='123456789')
        self.assertIn('owner_code', ctx.exception.message_dict)

    def test_zero_and_negative_terms_rejected(self):
        for field in ('data_retention_years', 'log_retention_days', 'account_deletion_grace_days'):
            for value in (0, -1):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValidationError) as ctx:
                        self._clean(**{field: value})
                    self.assertIn(field, ctx.exception.message_dict)


class PublicApiTests(CleanCacheTestCase):
    def test_anonymous_gets_whitelist_only(self):
        r = APIClient().get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), set(PublicSiteSettingsSerializer.Meta.fields))
        self.assertNotIn('id', r.json())
        self.assertNotIn('updated_at', r.json())

    def test_not_throttled_for_regular_visitor(self):
        # Баннер cookie дёргает endpoint на каждой загрузке страницы: анонимный лимит не должен срабатывать.
        client = APIClient()
        codes = {client.get(URL).status_code for _ in range(80)}
        self.assertEqual(codes, {200})

    def test_new_fields_public(self):
        data = APIClient().get(URL).json()
        self.assertEqual(data['log_retention_days'], 90)
        self.assertEqual(data['account_deletion_grace_days'], 14)
        self.assertIsNone(data['data_retention_years'])
        self.assertEqual(data['legal_docs_version'], '')
        self.assertIs(data['legal_docs_reconsent_required'], False)

    def test_owner_configured_false_when_empty(self):
        self.assertIs(APIClient().get(URL).json()['owner_configured'], False)

    def test_owner_configured_false_when_partial(self):
        SiteSettings.objects.update(owner_legal_name='ФОП', owner_code='12345678')
        SiteSettings.load().save()
        self.assertIs(APIClient().get(URL).json()['owner_configured'], False)

    def test_owner_configured_true_when_filled(self):
        s = SiteSettings.load()
        for k, v in OWNER.items():
            setattr(s, k, v)
        s.save()
        self.assertIs(APIClient().get(URL).json()['owner_configured'], True)

    def test_partner_name_in_public_response(self):
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()
        self.assertEqual(APIClient().get(URL).json()['partner_name'], 'Партнер Тест')

    def test_partner_consent_text_is_single_source(self):
        from leads.services import PARTNER_CONSENT_TEMPLATE
        self.assertEqual(APIClient().get(URL).json()['partner_consent_text'], '')
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()
        self.assertEqual(APIClient().get(URL).json()['partner_consent_text'],
                         PARTNER_CONSENT_TEMPLATE.format(partner='Партнер Тест'))

    def test_cache_invalidated_after_direct_save(self):
        self.assertEqual(APIClient().get(URL).json()['phone'], '')  # прогрев кэша
        s = SiteSettings.load()
        s.phone = '+380501234567'
        s.save()
        self.assertEqual(APIClient().get(URL).json()['phone'], '+380501234567')

    def test_cache_invalidated_after_admin_change(self):
        self.assertEqual(APIClient().get(URL).json()['phone'], '')  # прогрев кэша
        staff = make_staff(superuser=True)
        self.client.force_login(staff)
        form = {f: '' for f in ('owner_legal_form', 'owner_legal_name', 'owner_code', 'owner_address',
                                'support_email', 'privacy_email', 'manager_contact',
                                'telegram_channel_url', 'partner_name', 'partner_legal_name',
                                'data_retention_years', 'legal_docs_updated_at', 'legal_docs_version')}
        form.update(phone='+380509998877', log_retention_days=90, account_deletion_grace_days=14)
        r = self.client.post(reverse('admin:site_settings_sitesettings_change', args=[1]), form)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(APIClient().get(URL).json()['phone'], '+380509998877')


class CarverticalPartnerUrlTests(CleanCacheTestCase):
    def _url(self):
        return APIClient().get(URL).json()['carvertical_partner_url']

    @override_settings(CARVERTICAL_PARTNER_URL='')
    def test_empty_means_no_link(self):
        self.assertEqual(self._url(), '')

    @override_settings(CARVERTICAL_PARTNER_URL='https://partner.example/ref?id=1')
    def test_https_url_is_passed(self):
        self.assertEqual(self._url(), 'https://partner.example/ref?id=1')

    @override_settings(CARVERTICAL_PARTNER_URL='javascript:alert(1)')
    def test_non_https_is_dropped(self):
        self.assertEqual(self._url(), '')

    @override_settings(CARVERTICAL_PARTNER_URL='http://partner.example/ref')
    def test_plain_http_is_dropped(self):
        self.assertEqual(self._url(), '')

    @override_settings(CARVERTICAL_PARTNER_URL='your_partner_url')
    def test_placeholder_is_dropped(self):
        self.assertEqual(self._url(), '')

    def test_url_is_not_stuck_in_cache(self):
        with override_settings(CARVERTICAL_PARTNER_URL='https://partner.example/a'):
            self.assertEqual(self._url(), 'https://partner.example/a')
        with override_settings(CARVERTICAL_PARTNER_URL=''):
            self.assertEqual(self._url(), '')


class PublicConfigTests(CleanCacheTestCase):
    """Задача 6.4: лимиты объявлений и имя бота для текстов фронта; без секретов, не залипают в кэше."""

    def _get(self):
        r = APIClient().get(URL)
        self.assertEqual(r.status_code, 200)
        return r.json()

    @override_settings(LOCAL_LISTING_MAX_ACTIVE=7, LOCAL_LISTING_EXPIRY_DAYS=45,
                       LOCAL_LISTING_MAX_PHOTOS=9, LOCAL_LISTING_PHOTO_MAX_SIZE_MB=4)
    def test_limits_from_settings(self):
        data = self._get()
        self.assertEqual(data['local_listing_max_active'], 7)
        self.assertEqual(data['local_listing_expiry_days'], 45)
        self.assertEqual(data['local_listing_max_photos'], 9)
        self.assertEqual(data['local_listing_photo_max_size_mb'], 4)

    @override_settings(LOCAL_LISTING_PHOTO_MAX_SIZE_MB=None, UPLOAD_IMAGE_MAX_SIZE_MB=6)
    def test_photo_size_falls_back_to_common_limit(self):
        self.assertEqual(self._get()['local_listing_photo_max_size_mb'], 6)

    def test_limits_not_stuck_in_cache(self):
        with override_settings(LOCAL_LISTING_MAX_ACTIVE=3):
            self.assertEqual(self._get()['local_listing_max_active'], 3)
        with override_settings(LOCAL_LISTING_MAX_ACTIVE=12):
            self.assertEqual(self._get()['local_listing_max_active'], 12)

    @override_settings(TELEGRAM_BOT_USERNAME='@test_bot')
    def test_bot_username_without_at(self):
        self.assertEqual(self._get()['telegram_bot_username'], 'test_bot')

    @override_settings(TELEGRAM_BOT_USERNAME='')
    def test_bot_username_empty_when_not_set(self):
        self.assertEqual(self._get()['telegram_bot_username'], '')

    @override_settings(TELEGRAM_BOT_USERNAME='bad name!')
    def test_bot_username_invalid_is_dropped(self):
        self.assertEqual(self._get()['telegram_bot_username'], '')

    @override_settings(PAYMENTS_ENABLED=False)
    def test_payments_enabled_false(self):
        self.assertIs(self._get()['payments_enabled'], False)

    @override_settings(PAYMENTS_ENABLED=True)
    def test_payments_enabled_true(self):
        self.assertIs(self._get()['payments_enabled'], True)

    @override_settings(TELEGRAM_BOT_TOKEN='1234:placeholder', LIQPAY_PRIVATE_KEY='placeholder')
    def test_no_secret_keys_in_response(self):
        for key in self._get():
            for bad in ('token', 'secret', 'private', 'password', 'api_key'):
                self.assertNotIn(bad, key)


class PublicAnalyticsTests(CleanCacheTestCase):
    """Задача 3.5: публичный объект analytics содержит только непустые валидные ID."""

    def _analytics(self):
        return APIClient().get(URL).json()['analytics']

    @override_settings(GA4_MEASUREMENT_ID='', CLOUDFLARE_ANALYTICS_TOKEN='')
    def test_empty_by_default(self):
        self.assertEqual(self._analytics(), {})

    @override_settings(GA4_MEASUREMENT_ID='G-TEST000000', CLOUDFLARE_ANALYTICS_TOKEN='')
    def test_only_ga4(self):
        self.assertEqual(self._analytics(), {'ga4_id': 'G-TEST000000'})

    @override_settings(GA4_MEASUREMENT_ID='', CLOUDFLARE_ANALYTICS_TOKEN='CFTEST0000000000')
    def test_only_cloudflare(self):
        self.assertEqual(self._analytics(), {'cloudflare_token': 'CFTEST0000000000'})

    @override_settings(GA4_MEASUREMENT_ID='G-"><script>', CLOUDFLARE_ANALYTICS_TOKEN='bad token"')
    def test_invalid_format_is_dropped(self):
        self.assertEqual(self._analytics(), {})

    @override_settings(GA4_MEASUREMENT_ID='G-TEST000000')
    def test_not_stuck_in_cache(self):
        self.assertEqual(self._analytics(), {'ga4_id': 'G-TEST000000'})
        with override_settings(GA4_MEASUREMENT_ID=''):
            self.assertEqual(self._analytics(), {})
