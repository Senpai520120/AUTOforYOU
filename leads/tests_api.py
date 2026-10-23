from decimal import Decimal
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle

from leads import services
from leads.models import Lead, LeadCounter, LeadStatusChange
from pricing.models import Calculation
from site_settings.models import SiteSettings
from tests.base import CleanCacheTestCase
from tests.factories import TEST_PASSWORD, auth_client, make_dealer, make_listing, make_user, make_vehicle

URL = '/api/v1/leads/'
MINE = '/api/v1/leads/mine/'
TURNSTILE = dict(CAPTCHA_PROVIDER='turnstile', TURNSTILE_SITE_KEY='pub', TURNSTILE_SECRET_KEY='sec')


def set_partner(name='Партнер Тест'):
    s = SiteSettings.load()
    s.partner_name = name
    s.save()


def make_calc(user=None):
    return Calculation.objects.create(
        user=user,
        inputs_snapshot={'make': 'Toyota', 'year': 2020, 'fuel_type': 'petrol', 'auction_price': '5000'},
        rates_snapshot={'usd_uah': '41.5'},
        breakdown={'customs': '1000'},
        total_usd=Decimal('9000.50'), total_uah=Decimal('373520.75'), is_estimate=True,
    )


def body(**kw):
    d = {'name': 'Іван Петренко', 'phone': '0671234567', 'contact_method': 'telegram',
         'consent': True, 'partner_consent': True}
    d.update(kw)
    return d


def siteverify(success):
    response = mock.Mock()
    response.json.return_value = {'success': success}
    return mock.patch('httpx.post', return_value=response)


class LeadApiBase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        set_partner()
        self.client = APIClient()
        # Лимит заявок не должен мешать тестам, которые шлют много запросов.
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, client=None, **kw):
        return (client or self.client).post(URL, body(**kw), format='json')


class LeadCreateApiTests(LeadApiBase):
    def test_guest_with_guest_calculation_creates_lead(self):
        calc = make_calc()
        resp = self.post(calculation_id=calc.pk)
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get()
        self.assertEqual(resp.json()['public_id'], lead.public_id)
        self.assertEqual(resp.json()['status'], 'new')
        self.assertEqual(lead.source, 'calculator')
        self.assertEqual(lead.phone, '+380671234567')
        self.assertEqual(lead.calculation_snapshot['calculation_id'], calc.pk)
        self.assertEqual(lead.partner_name, 'Партнер Тест')
        self.assertEqual(LeadStatusChange.objects.filter(lead=lead).count(), 1)

    def test_response_has_no_pii(self):
        resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(set(resp.json()), {'public_id', 'status', 'created_at'})
        text = resp.content.decode()
        self.assertNotIn('Петренко', text)
        self.assertNotIn('380671234567', text)

    def test_authenticated_user_with_own_calculation(self):
        user = make_user()
        resp = self.post(auth_client(user), calculation_id=make_calc(user).pk)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.get().user, user)

    def test_foreign_calculation_is_400_on_field(self):
        calc = make_calc(make_user())
        for client in (self.client, auth_client(make_user())):
            resp = self.post(client, calculation_id=calc.pk)
            self.assertEqual(resp.status_code, 400)
            self.assertIn('calculation_id', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    def test_missing_calculation_is_400(self):
        resp = self.post(calculation_id=999999)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('calculation_id', resp.json())

    def test_source_must_match_object(self):
        resp = self.post(source='calculator', listing_id=1)
        self.assertEqual(resp.status_code, 400)
        resp = self.post()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('source', resp.json())

    def test_retail_listing_ok(self):
        listing = make_listing(make_vehicle(), make_user(), channel='retail')
        resp = self.post(listing_id=listing.pk)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.get().source, 'listing')

    def test_wholesale_listing_hidden_from_regular_user_and_guest(self):
        listing = make_listing(make_vehicle(), make_user(), channel='wholesale')
        for client in (self.client, auth_client(make_user())):
            resp = self.post(client, listing_id=listing.pk)
            self.assertEqual(resp.status_code, 400)
            self.assertIn('listing_id', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    def test_wholesale_listing_ok_for_verified_dealer(self):
        listing = make_listing(make_vehicle(), make_user(), channel='wholesale')
        self.assertEqual(self.post(auth_client(make_dealer()), listing_id=listing.pk).status_code, 201)

    @override_settings(LOTS_ENABLED=False)
    def test_listing_lead_rejected_when_lots_disabled(self):
        listing = make_listing(make_vehicle(), make_user(), channel='retail')
        resp = self.post(listing_id=listing.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('listing_id', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    @override_settings(B2B_ENABLED=False)
    def test_wholesale_lead_rejected_for_dealer_when_b2b_disabled(self):
        listing = make_listing(make_vehicle(), make_user(), channel='wholesale')
        resp = self.post(auth_client(make_dealer()), listing_id=listing.pk)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('listing_id', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    def test_missing_listing_is_400(self):
        resp = self.post(listing_id=999999)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('listing_id', resp.json())

    def test_consent_required(self):
        calc = make_calc()
        for kw in ({'consent': False}, {'consent': None}):
            resp = self.post(calculation_id=calc.pk, **kw)
            self.assertEqual(resp.status_code, 400)
            self.assertIn('consent', resp.json())
        payload = body(calculation_id=calc.pk)
        del payload['consent']
        resp = self.client.post(URL, payload, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('consent', resp.json())

    def test_partner_consent_required(self):
        calc = make_calc()
        resp = self.post(calculation_id=calc.pk, partner_consent=False)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('partner_consent', resp.json())
        payload = body(calculation_id=calc.pk)
        del payload['partner_consent']
        resp = self.client.post(URL, payload, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('partner_consent', resp.json())
        self.assertEqual(Lead.objects.count(), 0)

    def test_phone_validation_and_normalization(self):
        calc = make_calc()
        resp = self.post(calculation_id=calc.pk, phone='12345')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('phone', resp.json())
        payload = body(calculation_id=calc.pk)
        del payload['phone']
        self.assertEqual(self.client.post(URL, payload, format='json').status_code, 400)
        self.assertEqual(self.post(calculation_id=calc.pk, phone='+38 (067) 123-45-67').status_code, 201)
        self.assertEqual(Lead.objects.get().phone, '+380671234567')

    def test_bad_optional_fields(self):
        calc = make_calc()
        self.assertEqual(self.post(calculation_id=calc.pk, contact_method='whatsapp').status_code, 400)
        self.assertEqual(self.post(calculation_id=calc.pk, email='nope').status_code, 400)
        self.assertEqual(self.post(calculation_id=calc.pk, budget_usd='-1').status_code, 400)
        self.assertEqual(self.post(calculation_id=calc.pk, needed_when='never').status_code, 400)
        self.assertEqual(self.post(calculation_id=calc.pk, name='x' * 101).status_code, 400)
        self.assertEqual(Lead.objects.count(), 0)

    def test_email_optional(self):
        self.assertEqual(self.post(calculation_id=make_calc().pk, email='a@b.com').status_code, 201)
        self.assertEqual(Lead.objects.get().email, 'a@b.com')

    def test_attribution_never_blocks_and_is_cleaned(self):
        resp = self.post(
            calculation_id=make_calc().pk,
            utm={'term': 'x', 'source': 'tiktok'}, referrer='https://t.me/x?startapp=secret#frag',
            page_url='https://evil.test/calculator?x=1', entry_page_url='//evil.test',
        )
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get()
        self.assertEqual(lead.utm, {'source': 'tiktok'})
        self.assertEqual(lead.referrer, 'https://t.me')
        self.assertEqual(lead.page_url, '/calculator')
        self.assertEqual(lead.entry_page_url, '')

    def test_garbage_utm_is_ignored_not_400(self):
        resp = self.post(calculation_id=make_calc().pk, utm='abc', referrer={'a': 1}, page_url=[1])
        self.assertEqual(resp.status_code, 201)
        lead = Lead.objects.get()
        self.assertEqual((lead.utm, lead.referrer, lead.page_url), ({}, '', ''))


class LeadPartnerAndHoneypotTests(LeadApiBase):
    def test_empty_partner_name_is_503_without_lead(self):
        set_partner('')
        resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json(), {'detail': 'Партнер не налаштований'})
        self.assertEqual(Lead.objects.count(), 0)

    def test_empty_partner_name_is_503_before_field_validation(self):
        set_partner('')
        self.assertEqual(self.client.post(URL, {'name': 'x'}, format='json').status_code, 503)

    def test_service_level_partner_not_configured_is_503(self):
        with mock.patch('leads.views.create_lead', side_effect=services.PartnerNotConfigured):
            resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 503)

    def test_honeypot_returns_201_without_record(self):
        resp = self.post(calculation_id=make_calc().pk, website='http://spam.test')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(set(resp.json()), {'public_id', 'status', 'created_at'})

    def test_honeypot_works_even_with_invalid_fields_and_no_partner(self):
        set_partner('')
        resp = self.client.post(URL, {'website': 'x'}, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.count(), 0)

    def test_empty_honeypot_is_normal_lead(self):
        self.assertEqual(self.post(calculation_id=make_calc().pk, website='').status_code, 201)
        self.assertEqual(Lead.objects.count(), 1)


class LeadThrottleTests(LeadApiBase):
    def test_throttled_is_429(self):
        with mock.patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
                mock.patch.object(ScopedRateThrottle, 'wait', return_value=60.0):
            resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(Lead.objects.count(), 0)

    def test_throttle_precedes_honeypot(self):
        with mock.patch.object(ScopedRateThrottle, 'allow_request', return_value=False), \
                mock.patch.object(ScopedRateThrottle, 'wait', return_value=60.0):
            resp = self.post(website='bot')
        self.assertEqual(resp.status_code, 429)

    def test_scope_rate_comes_from_settings(self):
        from django.conf import settings
        self.assertIn('lead', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])


@override_settings(**TURNSTILE)
class LeadCaptchaTests(LeadApiBase):
    def test_failed_captcha_is_400_without_lead(self):
        with siteverify(False) as post:
            resp = self.post(calculation_id=make_calc().pk, captcha_token='tok')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'captcha_failed')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(Lead.objects.count(), 0)

    def test_missing_token_is_400(self):
        with siteverify(True) as post:
            resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'captcha_failed')
        post.assert_not_called()

    def test_good_captcha_is_201(self):
        with siteverify(True) as post:
            resp = self.post(calculation_id=make_calc().pk, captcha_token='tok')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(post.call_count, 1)

    def test_authenticated_user_also_needs_captcha(self):
        user = make_user()
        with siteverify(False):
            resp = self.post(auth_client(user), calculation_id=make_calc(user).pk, captcha_token='tok')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'captcha_failed')

    def test_honeypot_goes_before_captcha(self):
        with siteverify(False) as post:
            resp = self.post(calculation_id=make_calc().pk, website='x', captcha_token='tok')
        self.assertEqual(resp.status_code, 201)
        post.assert_not_called()
        self.assertEqual(Lead.objects.count(), 0)

    def test_captcha_goes_before_field_validation(self):
        with siteverify(False):
            resp = self.client.post(URL, {'captcha_token': 'tok'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'captcha_failed')


class LeadHooksApiTests(LeadApiBase):
    def test_on_commit_hooks_fire_once_for_api_lead(self):
        with mock.patch('leads.services.notify_new_lead') as notify, \
                mock.patch('leads.services.record_metric') as metric:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self.post(calculation_id=make_calc().pk)
        self.assertEqual(resp.status_code, 201)
        notify.assert_called_once_with(Lead.objects.get().pk)
        metric.assert_called_once_with('lead_created')

    def test_hooks_not_called_on_honeypot(self):
        with mock.patch('leads.services.notify_new_lead') as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.post(website='x')
        notify.assert_not_called()


class MyLeadsApiTests(LeadApiBase):
    def test_anonymous_is_401(self):
        self.assertEqual(self.client.get(MINE).status_code, 401)

    def test_only_own_leads_without_pii(self):
        a, b = make_user(), make_user()
        self.assertEqual(self.post(auth_client(a), calculation_id=make_calc(a).pk).status_code, 201)
        self.assertEqual(self.post(auth_client(b), calculation_id=make_calc(b).pk).status_code, 201)
        lead_b = Lead.objects.get(user=b)
        resp = auth_client(a).get(MINE)
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        self.assertNotIn(lead_b.pk, [r['id'] for r in results])
        self.assertEqual(
            set(results[0]),
            {'id', 'public_id', 'status', 'status_display', 'source', 'vehicle_label',
             'total_usd', 'total_uah', 'listing_id', 'created_at'},
        )
        text = resp.content.decode()
        self.assertNotIn('Петренко', text)
        self.assertNotIn('380671234567', text)

    def test_guest_lead_not_visible_to_users(self):
        self.post(calculation_id=make_calc().pk)
        self.assertEqual(auth_client(make_user()).get(MINE).json()['results'], [])


class LeadHardeningApiTests(LeadApiBase):
    def test_non_object_body_is_400_not_500(self):
        for raw in ('[]', '"x"', '123', 'null'):
            resp = self.client.post(URL, raw, content_type='application/json')
            self.assertEqual(resp.status_code, 400, raw)
            self.assertIn('non_field_errors', resp.json())

    def test_control_characters_rejected(self):
        calc = make_calc()
        for field in ('name', 'contact_handle', 'comment'):
            for bad in ('a\x00b', 'a\x1fb', 'a\x7fb'):
                resp = self.post(calculation_id=calc.pk, **{field: bad})
                self.assertEqual(resp.status_code, 400, (field, bad))
                self.assertIn(field, resp.json())
        for bad in ('a\nb', 'a\tb'):
            self.assertEqual(self.post(calculation_id=calc.pk, name=bad).status_code, 400)
        self.assertEqual(Lead.objects.count(), 0)

    def test_comment_allows_newlines_and_tabs(self):
        resp = self.post(calculation_id=make_calc().pk, comment='рядок1\r\nрядок2\tкінець')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Lead.objects.get().comment, 'рядок1\r\nрядок2\tкінець')

    def test_honeypot_public_id_is_plausible_next_number_without_side_effects(self):
        year = timezone.now().year
        LeadCounter.objects.create(year=year, last_number=41)
        resp = self.post(website='bot')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()['public_id'], f'AFY-{year}-0042')
        self.assertNotIn('id', resp.json())
        self.assertEqual(LeadCounter.objects.get(year=year).last_number, 41)
        self.assertEqual(Lead.objects.count(), 0)

    def test_honeypot_public_id_without_counter(self):
        resp = self.post(website='bot')
        self.assertEqual(resp.json()['public_id'], f'AFY-{timezone.now().year}-0001')
        self.assertFalse(LeadCounter.objects.exists())

    def test_real_and_fake_public_id_have_same_shape(self):
        real = self.post(calculation_id=make_calc().pk).json()['public_id']
        fake = self.post(website='bot').json()['public_id']
        self.assertEqual(len(real), len(fake))
        self.assertEqual(fake, real[:-4] + f'{int(real[-4:]) + 1:04d}')


class LeadRealThrottleTests(LeadApiBase):
    def _rates(self):
        return mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead': '2/hour'})

    def test_third_request_from_same_ip_is_429(self):
        with self._rates():
            codes = [self.post(calculation_id=make_calc().pk).status_code for _ in range(3)]
        self.assertEqual(codes, [201, 201, 429])
        self.assertEqual(Lead.objects.count(), 2)

    def test_guest_and_authenticated_use_different_keys(self):
        user = make_user()
        with self._rates():
            for _ in range(2):
                self.assertEqual(self.post(calculation_id=make_calc().pk).status_code, 201)
            self.assertEqual(self.post(calculation_id=make_calc().pk).status_code, 429)
            authed = auth_client(user)
            self.assertEqual(self.post(authed, calculation_id=make_calc(user).pk).status_code, 201)


class LeadCsrfTests(LeadApiBase):
    def setUp(self):
        super().setUp()
        self.user = make_user()
        self.client = APIClient(enforce_csrf_checks=True)
        resp = self.client.post(
            '/api/v1/auth/token/', {'email': self.user.email, 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_cookie_auth_without_csrf_is_403(self):
        resp = self.post(calculation_id=make_calc(self.user).pk)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Lead.objects.count(), 0)

    def test_cookie_auth_with_csrf_is_201(self):
        self.assertEqual(self.client.get('/api/v1/auth/csrf/').status_code, 204)
        token = self.client.cookies['csrftoken'].value
        resp = self.client.post(
            URL, body(calculation_id=make_calc(self.user).pk), format='json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resp.status_code, 201, resp.content)


class MyLeadsPaginationAndMaskingTests(LeadApiBase):
    def test_pagination_page_two_excludes_foreign_leads(self):
        a, b = make_user(), make_user()
        client = auth_client(a)
        for _ in range(21):
            self.assertEqual(self.post(client, calculation_id=make_calc(a).pk).status_code, 201)
        self.post(auth_client(b), calculation_id=make_calc(b).pk)
        page1 = client.get(MINE).json()
        self.assertEqual(page1['count'], 21)
        self.assertEqual(len(page1['results']), 20)
        page2 = client.get(MINE + '?page=2').json()
        self.assertEqual(len(page2['results']), 1)
        ids = {r['id'] for r in page1['results'] + page2['results']}
        self.assertEqual(ids, set(Lead.objects.filter(user=a).values_list('pk', flat=True)))

    def test_spam_shown_as_rejected_and_null_listing(self):
        user = make_user()
        self.post(auth_client(user), calculation_id=make_calc(user).pk)
        Lead.objects.update(status='spam')
        row = auth_client(user).get(MINE).json()['results'][0]
        self.assertEqual(row['status'], 'rejected')
        self.assertEqual(row['status_display'], 'Відмова')
        self.assertIsNone(row['listing_id'])
        self.assertNotIn('spam', auth_client(user).get(MINE).content.decode().lower())
