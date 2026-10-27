"""Страницы моделей «Пригон з США» (задача 2.16a): расчёт, публикация, API, seed, заявка с landing_slug."""
import io
import json
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from landings.models import LandingSettings, ModelLandingPage
from landings.services import build_landing_calculation, bump_cache_version, can_publish
from leads.models import Lead
from pricing import cache as pricing_cache
from pricing.cache import invalidate_all
from pricing.calculator import (
    LandedCostInputs,
    build_rate_snapshot_from_db,
    calc_auction_fees,
    calculate_landed_cost,
    select_rates,
)
from pricing.models import Calculation, OceanFreightRate
from pricing.views import FORM_DEFAULTS
from site_settings.models import SiteSettings
from tests.base import CleanCacheTestCase
from tests.factories import make_admin_role, make_broker, make_moderator, make_staff, make_user

LIST_URL = '/api/v1/landings/'
LEADS_URL = '/api/v1/leads/'
PAGE_FIELDS = dict(
    make='Toyota', model='Camry', year_from=2015, year_to=2020, calc_year=2018,
    auction_price_usd=Decimal('5000'), fuel_type='petrol', engine_cc=2000,
    auction='copart', auction_location='general', us_port='houston', eu_port='klaipeda',
)


def make_page(slug='toyota-camry', **kw):
    return ModelLandingPage.objects.create(**{**PAGE_FIELDS, 'slug': slug, **kw})


def detail_url(slug):
    return f'{LIST_URL}{slug}/'


class SeededCase(CleanCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_rates', verbosity=0)
        call_command('seed_auction_fees', '--clear', verbosity=0)

    def expire_rates(self):
        """Все морские ставки закончились вчера: активных нет."""
        yesterday = timezone.localdate() - timedelta(days=1)
        OceanFreightRate.objects.update(valid_from=yesterday - timedelta(days=30), valid_to=yesterday)
        invalidate_all()


class CalculationServiceTests(SeededCase):
    def test_matches_direct_calculator_call(self):
        page = make_page()
        calc = build_landing_calculation(page)
        # Эталон: тот же подбор ставок и чистая функция напрямую.
        today = timezone.localdate()
        inputs = {'auction_price_usd': Decimal('5000'), 'engine_cc': 2000, 'fuel_type': 'petrol',
                  'vehicle_year': 2018, 'auction': 'copart', 'auction_location': 'general', 'us_port': 'houston',
                  'eu_port': 'klaipeda', **FORM_DEFAULTS}
        sel = select_rates(pricing_cache.get_catalog(), inputs, today)
        rates = build_rate_snapshot_from_db(
            calc_auction_fees(bid=Decimal('5000'), tier=sel.tier, fixed_fees=sel.fixed_fees), sel.us_land, sel.ocean,
            sel.eu_to_ua, sel.usd_to_uah, sel.usd_to_eur, sel.excise, 2018, today.year, rule=sel.rule, on_date=today)
        rates.broker_services = []
        expected = calculate_landed_cost(
            LandedCostInputs(Decimal('5000'), 2000, 'petrol', 2018, today.year), rates, sel.pension_brackets, sel.rule)
        self.assertEqual(calc['total_usd'], str(expected.total_usd))
        self.assertEqual(calc['total_uah'], str(expected.total_uah))
        self.assertIs(calc['is_estimate'], True)
        self.assertEqual(calc['rates_valid_from'], sel.rates_updated_on.isoformat())

    def test_incomplete_inputs_give_none(self):
        for field, value in (('auction_price_usd', None), ('fuel_type', ''), ('engine_cc', None),
                             ('calc_year', None), ('us_port', ''), ('eu_port', ''), ('auction_location', '')):
            with self.subTest(field=field):
                self.assertIsNone(build_landing_calculation(make_page(slug=f'p-{field}'.replace('_', '-'),
                                                                      **{field: value})))

    def test_electric_needs_battery(self):
        page = make_page(fuel_type='electric', engine_cc=None, battery_capacity_kwh=None)
        self.assertIsNone(build_landing_calculation(page))
        page.battery_capacity_kwh = Decimal('75.0')
        self.assertIsNotNone(build_landing_calculation(page))

    def test_expired_rates_give_none(self):
        page = make_page()
        self.expire_rates()
        self.assertIsNone(build_landing_calculation(page))
        self.assertFalse(can_publish(page))

    def test_rate_change_changes_total_without_code_change(self):
        page = make_page()
        before = Decimal(build_landing_calculation(page)['total_usd'])
        OceanFreightRate.objects.filter(us_port='houston', eu_port='klaipeda').update(cost_usd=Decimal('9300'))
        invalidate_all()
        after = Decimal(build_landing_calculation(page)['total_usd'])
        self.assertGreater(after, before)


class PublishValidationTests(SeededCase):
    def test_publish_without_calculation_rejected(self):
        page = make_page(auction_price_usd=None, is_published=True)
        with self.assertRaisesMessage(ValidationError, 'Не можна опублікувати без розрахунку'):
            page.full_clean()

    def test_publish_with_calculation_ok(self):
        page = make_page(is_published=True)
        page.full_clean()

    def test_publish_with_expired_rates_rejected(self):
        page = make_page(is_published=True)
        self.expire_rates()
        with self.assertRaisesMessage(ValidationError, 'Не можна опублікувати без розрахунку'):
            page.full_clean()

    def test_publish_with_draft_marker_rejected(self):
        page = make_page(is_published=True, typical_term_text='[ПЕРЕВІРИТИ ЗІ ВЛАСНИКОМ: термін]')
        with self.assertRaisesMessage(ValidationError, 'Приберіть позначку'):
            page.full_clean()

    def test_draft_with_no_calculation_is_ok(self):
        make_page(auction_price_usd=None).full_clean()

    def test_slug_unique_and_charset(self):
        make_page()
        with self.assertRaisesMessage(ValidationError, 'вже існує'):
            ModelLandingPage(slug='toyota-camry', make='A', model='B').full_clean()
        for bad in ('Toyota-Camry', 'тойота', 'a b', '-a', 'a--b', 'a_b'):
            with self.subTest(slug=bad), self.assertRaisesMessage(ValidationError, 'Лише малі латинські'):
                ModelLandingPage(slug=bad, make='A', model='B').full_clean()

    def test_year_range_validation(self):
        page = ModelLandingPage(slug='x', make='A', model='B', year_from=2020, year_to=2015)
        with self.assertRaisesMessage(ValidationError, 'не може бути меншим'):
            page.full_clean()
        page = ModelLandingPage(slug='x', make='A', model='B', year_from=2015, year_to=2020, calc_year=2024)
        with self.assertRaisesMessage(ValidationError, 'поза діапазоном'):
            page.full_clean()


class LandingApiTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_detail_ok_and_matches_service(self):
        page = make_page(is_published=True, typical_term_text='два-три місяці')
        resp = self.client.get(detail_url(page.slug))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        calc = build_landing_calculation(page)
        self.assertIs(data['calculation']['is_estimate'], True)
        self.assertEqual(data['calculation']['total_usd'], calc['total_usd'])
        self.assertEqual(data['calculation']['total_uah'], calc['total_uah'])
        self.assertIsInstance(data['calculation']['total_usd'], str)
        Decimal(data['calculation']['total_usd'])
        self.assertEqual(data['calculation']['rates_valid_from'], calc['rates_valid_from'])
        self.assertEqual(data['calculation']['currency'], 'USD')
        self.assertEqual(data['typical_term_text'], 'два-три місяці')
        self.assertEqual(data['h1'], 'Пригон Toyota Camry з США — ціна під ключ')

    def test_custom_h1_used(self):
        page = make_page(is_published=True, h1='Свій заголовок')
        self.assertEqual(self.client.get(detail_url(page.slug)).json()['h1'], 'Свій заголовок')

    def test_no_service_fields_leaked(self):
        page = make_page(is_published=True)
        data = self.client.get(detail_url(page.slug)).json()
        self.assertEqual(set(data) & {'id', 'is_published', 'sort_order', 'created_at', 'rates_snapshot'}, set())
        self.assertNotIn('rates_snapshot', data['calculation'])
        self.assertNotIn('meta', str(data['calculation'].keys()))

    def test_unpublished_is_404_and_not_in_list(self):
        page = make_page()
        self.assertEqual(self.client.get(detail_url(page.slug)).status_code, 404)
        self.assertEqual(self.client.get(LIST_URL).json()['results'], [])

    def test_unknown_slug_is_404(self):
        self.assertEqual(self.client.get(detail_url('no-such')).status_code, 404)

    def test_published_without_calculation_is_404_and_not_in_list(self):
        page = make_page(is_published=True)
        ModelLandingPage.objects.filter(pk=page.pk).update(auction_price_usd=None)  # в обход clean()
        bump_cache_version()
        self.assertEqual(self.client.get(detail_url(page.slug)).status_code, 404)
        self.assertEqual(self.client.get(LIST_URL).json()['results'], [])

    def test_rates_expired_after_publication_is_404(self):
        page = make_page(is_published=True)
        self.assertEqual(self.client.get(detail_url(page.slug)).status_code, 200)
        self.expire_rates()
        self.assertEqual(self.client.get(detail_url(page.slug)).status_code, 404)
        self.assertEqual(self.client.get(LIST_URL).json()['results'], [])

    def test_draft_marker_hides_page_published_by_bypass(self):
        page = make_page(is_published=True)
        ModelLandingPage.objects.filter(pk=page.pk).update(intro='[ПЕРЕВІРИТИ ЗІ ВЛАСНИКОМ: вступ]')
        bump_cache_version()
        self.assertEqual(self.client.get(detail_url(page.slug)).status_code, 404)

    def test_list_fields(self):
        page = make_page(is_published=True)
        make_page(slug='hidden')
        results = self.client.get(LIST_URL).json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(set(results[0]), {'slug', 'make', 'model', 'total_usd', 'total_uah', 'updated_at'})
        self.assertEqual(results[0]['slug'], page.slug)

    def test_get_writes_nothing(self):
        page = make_page(is_published=True)
        updated = page.updated_at
        for url in (detail_url(page.slug), LIST_URL):
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(url).status_code, 200)
            writes = [q['sql'] for q in queries if q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE'))]
            self.assertEqual(writes, [])
        self.assertEqual(Calculation.objects.count(), 0)
        page.refresh_from_db()
        self.assertEqual(page.updated_at, updated)

    def test_post_not_allowed(self):
        page = make_page(is_published=True)
        self.assertEqual(self.client.post(detail_url(page.slug), {}, format='json').status_code, 405)


class CacheTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.page = make_page(is_published=True)

    def get(self):
        return self.client.get(detail_url(self.page.slug))

    def test_second_request_uses_cache(self):
        with mock.patch('landings.services.build_landing_calculation',
                        wraps=build_landing_calculation) as spy:
            self.assertEqual(self.get().status_code, 200)
            self.assertEqual(self.get().status_code, 200)
        self.assertEqual(spy.call_count, 1)

    def test_rate_save_resets_cache(self):
        first = self.get().json()['calculation']['total_usd']
        rate = OceanFreightRate.objects.get(us_port='houston', eu_port='klaipeda')
        rate.cost_usd = Decimal('9300')
        rate.save()
        self.assertNotEqual(self.get().json()['calculation']['total_usd'], first)

    def test_page_save_resets_cache(self):
        self.assertEqual(self.get().json()['intro'], '')
        self.page.intro = 'Новий вступ'
        self.page.save()
        self.assertEqual(self.get().json()['intro'], 'Новий вступ')

    def test_save_without_updated_at_still_resets_cache(self):
        first = self.get().json()['calculation']['total_usd']
        self.page.auction_price_usd = Decimal('9000')
        self.page.save(update_fields=['auction_price_usd'])  # updated_at в БД не меняется: сбрасывает сигнал
        self.assertNotEqual(self.get().json()['calculation']['total_usd'], first)

    def test_page_delete_resets_cache(self):
        self.assertEqual(self.get().status_code, 200)
        self.page.delete()
        self.assertEqual(self.get().status_code, 404)

    def test_expired_rates_reset_cache(self):
        self.assertEqual(self.get().status_code, 200)
        self.expire_rates()
        self.assertEqual(self.get().status_code, 404)

    def test_cache_cleared_externally_recomputes(self):
        self.get()
        cache.clear()
        self.assertEqual(self.get().status_code, 200)


class MaxPublishedTests(SeededCase):
    def test_warning_only_above_limit_and_limit_is_data(self):
        from landings.services import publication_warning
        for i in range(3):
            make_page(slug=f'm-{i}', is_published=True)
        self.assertIsNone(publication_warning())
        LandingSettings.objects.update_or_create(pk=1, defaults={'max_published': 2})
        self.assertIn('3', publication_warning())
        LandingSettings.objects.update_or_create(pk=1, defaults={'max_published': 50})
        self.assertIsNone(publication_warning())

    def test_publish_above_limit_is_not_blocked(self):
        LandingSettings.objects.update_or_create(pk=1, defaults={'max_published': 1})
        for i in range(2):
            make_page(slug=f'm-{i}', is_published=True).full_clean()
        self.assertEqual(ModelLandingPage.objects.filter(is_published=True).count(), 2)

    def test_default_limit_is_a_field_default(self):
        self.assertEqual(LandingSettings.get_solo().max_published, 30)


class AdminTests(SeededCase):
    URL = '/admin/landings/modellandingpage/'

    def post_action(self, user, pages):
        client = APIClient()
        client.force_login(user)
        return client.post(self.URL, {'action': 'publish_selected', '_selected_action': [p.pk for p in pages]},
                           follow=True)

    def test_action_publishes_only_pages_with_calculation(self):
        good = make_page(slug='good')
        no_price = make_page(slug='no-price', auction_price_usd=None)
        marked = make_page(slug='marked', intro='[ПЕРЕВІРИТИ ЗІ ВЛАСНИКОМ: вступ]')
        resp = self.post_action(make_staff(superuser=True), [good, no_price, marked])
        self.assertEqual(resp.status_code, 200)
        for p in (good, no_price, marked):
            p.refresh_from_db()
        self.assertEqual((good.is_published, no_price.is_published, marked.is_published), (True, False, False))
        text = resp.content.decode()
        self.assertIn('Toyota Camry: немає розрахунку', text)
        self.assertIn('позначка', text)

    def test_only_admin_sees_module(self):
        for user, code in ((make_staff(), 403), (make_broker(is_staff=True), 403), (make_staff(superuser=True), 200)):
            client = APIClient()
            client.force_login(user)
            self.assertEqual(client.get(self.URL).status_code, code)

    def staff_with_all_perms(self, user, group_name):
        perms = Permission.objects.filter(content_type__app_label='landings')
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.add(*perms)
        user.groups.add(group)
        user.user_permissions.add(*perms)
        return user

    def not_admin_users(self):
        return {
            'moderator': self.staff_with_all_perms(make_moderator(), 'Модератори'),
            'admins-group-not-admin-role': self.staff_with_all_perms(
                make_user(role='buyer', is_staff=True), 'Адміністратори'),
        }

    def test_staff_with_all_perms_but_not_admin_role_gets_403(self):
        for name, user in self.not_admin_users().items():
            with self.subTest(user=name):
                self.assertNotEqual(user.role, 'admin')
                client = APIClient()
                client.force_login(user)
                self.assertEqual(client.get(self.URL).status_code, 403)

    def test_admin_role_without_superuser_gets_200(self):
        user = make_admin_role()
        self.assertFalse(user.is_superuser)
        client = APIClient()
        client.force_login(user)
        self.assertEqual(client.get(self.URL).status_code, 200)

    def test_moderator_cannot_change_or_publish(self):
        page = make_page(slug='mod-target')
        client = APIClient()
        client.force_login(self.not_admin_users()['moderator'])
        change = client.post(f'{self.URL}{page.pk}/change/', {
            'slug': page.slug, 'make': 'X', 'model': 'Y', 'is_published': 'on', 'auction': 'copart'})
        self.assertEqual(change.status_code, 403)
        action = client.post(self.URL, {'action': 'publish_selected', '_selected_action': [page.pk]})
        self.assertEqual(action.status_code, 403)
        page.refresh_from_db()
        self.assertEqual((page.is_published, page.make), (False, 'Toyota'))

    def test_list_shows_hidden_warning(self):
        page = make_page(is_published=True)
        ModelLandingPage.objects.filter(pk=page.pk).update(auction_price_usd=None)
        client = APIClient()
        client.force_login(make_staff(superuser=True))
        self.assertIn('сторінка прихована', client.get(self.URL).content.decode())

    def test_limit_warning_in_changelist(self):
        LandingSettings.objects.update_or_create(pk=1, defaults={'max_published': 1})
        make_page(slug='a', is_published=True)
        make_page(slug='b', is_published=True)
        client = APIClient()
        client.force_login(make_staff(superuser=True))
        self.assertIn('рекомендована межа', client.get(self.URL).content.decode())


class SeedCommandTests(SeededCase):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_seed(self, *args):
        out = io.StringIO()
        call_command('seed_landing_pages', *args, stdout=out)
        return out.getvalue()

    def test_creates_drafts_without_prices_and_is_idempotent(self):
        self.run_seed()
        count = ModelLandingPage.objects.count()
        self.assertGreater(count, 0)
        self.assertFalse(ModelLandingPage.objects.filter(is_published=True).exists())
        self.assertFalse(ModelLandingPage.objects.exclude(auction_price_usd=None).exists())
        for page in ModelLandingPage.objects.all():
            self.assertTrue(page.has_draft_marker())
            self.assertIsNone(build_landing_calculation(page))
        ModelLandingPage.objects.filter(slug='toyota-camry').update(intro='Правка власника', auction_price_usd=1)
        self.run_seed()
        self.assertEqual(ModelLandingPage.objects.count(), count)
        camry = ModelLandingPage.objects.get(slug='toyota-camry')
        self.assertEqual((camry.intro, camry.auction_price_usd), ('Правка власника', Decimal('1')))

    def test_file_keys_are_whitelisted(self):
        path = Path(self.tmp.name) / 'm.json'
        path.write_text(json.dumps({'models': [
            {'slug': 'evil-car', 'make': 'Evil', 'model': 'Car', 'is_published': True, 'auction_price_usd': '1',
             'intro': 'без позначки', 'calc_year': 2018, 'year_from': 2015, 'year_to': 2020}]}), encoding='utf-8')
        self.run_seed('--file', str(path))
        page = ModelLandingPage.objects.get(slug='evil-car')
        self.assertFalse(page.is_published)
        self.assertIsNone(page.auction_price_usd)
        self.assertTrue(page.has_draft_marker())
        self.assertEqual((page.calc_year, page.year_from, page.year_to), (2018, 2015, 2020))

    def test_invalid_item_aborts_whole_run(self):
        path = Path(self.tmp.name) / 'bad.json'
        path.write_text(json.dumps({'models': [
            {'slug': 'good-one', 'make': 'A', 'model': 'B'},
            {'slug': 'Bad Slug', 'make': 'A', 'model': 'B'}]}), encoding='utf-8')
        with self.assertRaisesMessage(CommandError, 'Bad Slug'):
            self.run_seed('--file', str(path))
        self.assertEqual(ModelLandingPage.objects.count(), 0)

    def test_dry_run_writes_nothing(self):
        out = self.run_seed('--dry-run')
        self.assertIn('dry-run', out)
        self.assertEqual(ModelLandingPage.objects.count(), 0)

    def test_draft_texts_have_no_digits(self):
        self.run_seed()
        for page in ModelLandingPage.objects.all():
            text = (page.intro + page.included_text + page.typical_term_text).replace(page.title, '')
            self.assertFalse(any(ch.isdigit() for ch in text))


class LeadWithLandingSlugTests(SeededCase):
    def setUp(self):
        super().setUp()
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = APIClient()
        self.page = make_page(is_published=True)

    def post(self, **kw):
        body = {'name': 'Іван', 'phone': '0671234567', 'contact_method': 'telegram',
                'consent': True, 'partner_consent': True, 'landing_slug': self.page.slug, **kw}
        return self.client.post(LEADS_URL, body, format='json')

    def test_creates_lead_with_server_snapshot(self):
        resp = self.post()
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get()
        calc = build_landing_calculation(self.page)
        self.assertEqual(lead.source, 'landing')
        self.assertEqual(lead.landing_slug, 'toyota-camry')
        self.assertEqual(lead.entry_page_url, '/prigon/toyota-camry')
        self.assertEqual(lead.vehicle_label, 'Toyota Camry')
        snap = lead.calculation_snapshot
        self.assertEqual(snap['inputs_snapshot']['make'], 'Toyota')
        self.assertEqual(snap['inputs_snapshot']['auction_price_usd'], '5000.00')
        self.assertIs(snap['is_estimate'], True)
        self.assertEqual(snap['rates_valid_from'], calc['rates_valid_from'])
        self.assertIn('excise_eur_per_100cc', snap['rates_snapshot'])
        self.assertEqual(snap['breakdown']['total_usd'], calc['total_usd'])
        self.assertEqual(lead.total_usd, Decimal(calc['total_usd']))
        self.assertEqual(lead.total_uah, Decimal(calc['total_uah']))
        self.assertEqual(Calculation.objects.count(), 0)

    def test_client_supplied_amounts_and_urls_are_ignored(self):
        resp = self.post(total_usd='1', total_uah='1', calculation_snapshot={'total_usd': '1'},
                         entry_page_url='/evil', source='calculator', vehicle_label='Подмена')
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get()
        self.assertEqual(lead.source, 'landing')
        self.assertEqual(lead.entry_page_url, '/prigon/toyota-camry')
        self.assertEqual(lead.vehicle_label, 'Toyota Camry')
        calc = build_landing_calculation(self.page)
        self.assertEqual(lead.total_usd, Decimal(calc['total_usd']))
        self.assertEqual(lead.calculation_snapshot['total_usd'], calc['total_usd'])

    def test_unknown_or_unpublished_slug_is_400(self):
        make_page(slug='draft')
        for slug in ('no-such', 'draft'):
            with self.subTest(slug=slug):
                resp = self.post(landing_slug=slug)
                self.assertEqual(resp.status_code, 400)
                self.assertIn('landing_slug', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    def test_blank_slug_creates_lead_without_amounts(self):
        resp = self.post(landing_slug='', source='landing')
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get()
        self.assertEqual((lead.total_usd, lead.total_uah, lead.calculation_snapshot), (None, None, {}))
        self.assertEqual(lead.landing_slug, '')

    def test_published_page_with_draft_marker_is_400(self):
        ModelLandingPage.objects.filter(pk=self.page.pk).update(intro='[ПЕРЕВІРИТИ ЗІ ВЛАСНИКОМ: вступ]')
        bump_cache_version()
        resp = self.post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('landing_slug', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    def test_page_without_calculation_is_400(self):
        self.expire_rates()
        resp = self.post()
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Lead.objects.count(), 0)

    def test_consents_still_required(self):
        resp = self.post(consent=False)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Lead.objects.count(), 0)

    def test_slug_with_calculation_id_is_400(self):
        calc = Calculation.objects.create(inputs_snapshot={}, rates_snapshot={}, breakdown={},
                                          total_usd=Decimal('1'), total_uah=Decimal('1'))
        resp = self.post(calculation_id=calc.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('landing_slug', resp.json())
