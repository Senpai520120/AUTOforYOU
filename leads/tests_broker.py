"""Кабинет брокера (задача 2.4): права, фильтры, статусы, take, источник, число запросов."""
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from leads.models import Lead, LeadStatus, LeadStatusChange
from leads.services import ALLOWED_TRANSITIONS, change_status, create_lead
from site_settings.models import SiteSettings
from tests.base import CleanCacheTestCase
from tests.factories import (
    auth_client,
    make_admin_role,
    make_broker,
    make_dealer,
    make_listing,
    make_moderator,
    make_user,
    make_vehicle,
)

LIST = '/api/v1/broker/leads/'
MINE = '/api/v1/leads/mine/'


def detail(pk):
    return f'{LIST}{pk}/'


def status_url(pk):
    return f'{LIST}{pk}/status/'


def take_url(pk):
    return f'{LIST}{pk}/take/'


def partner_url(pk):
    return f'{LIST}{pk}/partner-status/'


class BrokerBase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()
        self.broker = make_broker()
        self.bc = auth_client(self.broker)

    def lead(self, user=None, **kw):
        data = {'name': 'Іван', 'phone': '0671234567', 'contact_method': 'telegram', 'source': 'landing'}
        data.update(kw)
        return create_lead(user=user, data=data)


class AccessMatrixTests(BrokerBase):
    def setUp(self):
        super().setUp()
        self.lead_obj = self.lead()
        self.endpoints = [
            ('get', LIST), ('get', detail(self.lead_obj.pk)),
            ('post', status_url(self.lead_obj.pk)), ('post', take_url(self.lead_obj.pk)),
            ('post', partner_url(self.lead_obj.pk)),
        ]

    def call(self, client, method, url):
        if method == 'get':
            return client.get(url)
        return getattr(client, method)(url, {'status': 'in_progress', 'partner_status': 'thinking'}, format='json')

    def test_anonymous_401(self):
        for method, url in self.endpoints:
            with self.subTest(url=url):
                self.assertEqual(self.call(APIClient(), method, url).status_code, 401)

    def test_non_broker_roles_403(self):
        users = {
            'buyer': make_user(),
            'dealer': make_dealer(),
            'moderator': make_moderator(),
            'staff_buyer': make_user(is_staff=True),
        }
        for name, user in users.items():
            for method, url in self.endpoints:
                with self.subTest(user=name, url=url):
                    self.assertEqual(self.call(auth_client(user), method, url).status_code, 403)
        lead = Lead.objects.get(pk=self.lead_obj.pk)
        self.assertEqual(lead.status, LeadStatus.NEW)
        self.assertIsNone(lead.assigned_to)

    def test_broker_and_admin_200(self):
        for user in (self.broker, make_admin_role()):
            with self.subTest(user=user.role):
                c = auth_client(user)
                self.assertEqual(c.get(LIST).status_code, 200)
                self.assertEqual(c.get(detail(self.lead_obj.pk)).status_code, 200)

    def test_missing_lead_404(self):
        self.assertEqual(self.bc.get(detail(999999)).status_code, 404)

    def test_buyer_filter_param_403(self):
        self.assertEqual(auth_client(make_user()).get(LIST, {'utm_source': 'tiktok'}).status_code, 403)

    def test_delete_not_allowed_for_buyer(self):
        self.assertEqual(auth_client(make_user()).delete(detail(self.lead_obj.pk)).status_code, 403)
        self.assertTrue(Lead.objects.filter(pk=self.lead_obj.pk).exists())


class ListFilterTests(BrokerBase):
    def test_status_filter(self):
        a = self.lead()
        b = self.lead()
        change_status(b, 'in_progress', by=self.broker)
        r = self.bc.get(LIST, {'status': 'new'})
        self.assertEqual([x['id'] for x in r.data['results']], [a.pk])
        self.assertEqual(r.data['new_count'], 1)

    def test_unknown_status_400(self):
        self.assertEqual(self.bc.get(LIST, {'status': 'nope'}).status_code, 400)

    def test_source_and_assigned_filters(self):
        a = self.lead(source='landing')
        b = self.lead(source='landing', name='Інша')
        b.assigned_to = self.broker
        b.save()
        self.assertEqual([x['id'] for x in self.bc.get(LIST, {'assigned_to': 'me'}).data['results']], [b.pk])
        self.assertEqual(self.bc.get(LIST, {'assigned_to': 'someone'}).status_code, 400)
        self.assertEqual(self.bc.get(LIST, {'source': 'listing'}).data['count'], 0)
        self.assertEqual(self.bc.get(LIST, {'source': 'landing'}).data['count'], 2)
        self.assertIn(a.pk, [x['id'] for x in self.bc.get(LIST).data['results']])

    def test_search_phone_variants_and_name(self):
        lead = self.lead(name='Олексій Коваль')
        self.lead(name='Інший', phone='0509876543')
        for q in ('0671234567', '+380671234567', '067 123 45 67'):
            with self.subTest(q=q):
                r = self.bc.get(LIST, {'search': q})
                self.assertEqual([x['id'] for x in r.data['results']], [lead.pk])
        # регістр кирилиці залежить від СУБД (SQLite icontains — лише ASCII), тому перевіряємо відсутність підрядка
        self.assertEqual(self.bc.get(LIST, {'search': 'Петренко'}).data['count'], 0)
        self.assertEqual(self.bc.get(LIST, {'search': 'Коваль'}).data['count'], 1)

    def test_search_wildcards_literal(self):
        self.lead()
        self.assertEqual(self.bc.get(LIST, {'search': '%'}).data['count'], 0)

    def test_utm_source_exact(self):
        tiktok = self.lead(utm={'source': 'tiktok'})
        self.lead(utm={'source': 'tiktok2'})
        self.lead()
        r = self.bc.get(LIST, {'utm_source': 'tiktok'})
        self.assertEqual([x['id'] for x in r.data['results']], [tiktok.pk])
        self.assertEqual(self.bc.get(LIST, {'utm_source': 'tik'}).data['count'], 0)
        r = self.bc.get(LIST, {'utm_source': 'nonexistent'})
        self.assertEqual((r.status_code, r.data['results']), (200, []))

    def test_too_long_param_400(self):
        self.assertEqual(self.bc.get(LIST, {'utm_source': 'a' * 101}).status_code, 400)
        self.assertEqual(self.bc.get(LIST, {'search': 'a' * 101}).status_code, 400)

    def test_ordering_and_pagination(self):
        leads = [self.lead() for _ in range(3)]
        r = self.bc.get(LIST, {'ordering': 'created_at', 'page_size': 2})
        self.assertEqual(r.data['count'], 3)
        self.assertEqual(len(r.data['results']), 2)
        self.assertEqual([x['id'] for x in r.data['results']], [leads[0].pk, leads[1].pk])
        r = self.bc.get(LIST, {'ordering': 'created_at', 'page_size': 2, 'page': 2})
        self.assertEqual([x['id'] for x in r.data['results']], [leads[2].pk])
        self.assertEqual(self.bc.get(LIST).data['results'][0]['id'], leads[2].pk)
        self.assertEqual(self.bc.get(LIST, {'ordering': 'phone'}).status_code, 400)

    def test_source_column(self):
        self.lead(utm={'source': 'tiktok'})
        self.lead()
        rows = {x['utm_source'] for x in self.bc.get(LIST).data['results']}
        self.assertEqual(rows, {'tiktok', ''})

    def test_query_count_constant(self):
        user = make_user()
        self.lead(user=user)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                r = self.bc.get(LIST)
            self.assertEqual(r.status_code, 200)
            return len(ctx)

        one = count()
        for i in range(9):
            lead = self.lead(utm={'source': f's{i}'})
            lead.assigned_to = self.broker
            lead.save()
        self.assertEqual(count(), one)


class StatusTests(BrokerBase):
    def test_new_to_in_progress_logged(self):
        lead = self.lead()
        r = self.bc.post(status_url(lead.pk), {'status': 'in_progress', 'note': 'Дзвонив'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['status'], 'in_progress')
        entry = LeadStatusChange.objects.filter(lead=lead).latest('pk')
        self.assertEqual((entry.changed_by, entry.note), (self.broker, 'Дзвонив'))
        self.assertEqual(r.data['history'][-1]['changed_by']['id'], self.broker.pk)

    def test_invalid_transition_400(self):
        lead = self.lead()
        r = self.bc.post(status_url(lead.pk), {'status': 'delivered'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.data['detail'])
        self.assertEqual(Lead.objects.get(pk=lead.pk).status, 'new')

    def test_unknown_status_and_long_note_400(self):
        lead = self.lead()
        self.assertEqual(self.bc.post(status_url(lead.pk), {'status': 'bogus'}, format='json').status_code, 400)
        self.assertEqual(self.bc.post(status_url(lead.pk), {}, format='json').status_code, 400)
        r = self.bc.post(status_url(lead.pk), {'status': 'in_progress', 'note': 'x' * 501}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Lead.objects.get(pk=lead.pk).status, 'new')

    def test_same_status_400(self):
        lead = self.lead()
        self.assertEqual(self.bc.post(status_url(lead.pk), {'status': 'new'}, format='json').status_code, 400)

    def test_full_chain(self):
        lead = self.lead()
        chain = ['in_progress', 'contract', 'car_bought', 'in_transit', 'customs', 'delivered']
        for st in chain:
            with self.subTest(st=st):
                r = self.bc.post(status_url(lead.pk), {'status': st}, format='json')
                self.assertEqual((r.status_code, r.data['status']), (200, st))
        self.assertEqual(r.data['allowed_transitions'], [])
        self.assertEqual(len(r.data['history']), 7)
        self.assertEqual(self.bc.post(status_url(lead.pk), {'status': 'rejected'}, format='json').status_code, 400)

    def test_client_sees_status_but_not_broker_data(self):
        client_user = make_user()
        lead = self.lead(user=client_user)
        self.bc.post(take_url(lead.pk))
        self.bc.post(status_url(lead.pk), {'status': 'contract', 'note': 'внутрішня нотатка'}, format='json')
        r = auth_client(client_user).get(MINE)
        row = r.data['results'][0]
        self.assertEqual(row['status'], 'contract')
        self.assertNotIn('assigned_to', row)
        self.assertNotIn('history', row)
        self.assertNotIn('внутрішня нотатка', r.content.decode())


class TakeTests(BrokerBase):
    def test_take_free(self):
        lead = self.lead()
        r = self.bc.post(take_url(lead.pk))
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual((lead.assigned_to, lead.status), (self.broker, 'in_progress'))
        self.assertIsNotNone(lead.first_response_at)
        self.assertEqual(r.data['assigned_to']['email'], self.broker.email)

    def test_take_taken_by_other_409(self):
        lead = self.lead()
        other = make_broker()
        self.assertEqual(auth_client(other).post(take_url(lead.pk)).status_code, 200)
        self.assertEqual(self.bc.post(take_url(lead.pk)).status_code, 409)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to, other)

    def test_take_idempotent(self):
        lead = self.lead()
        self.assertEqual(self.bc.post(take_url(lead.pk)).status_code, 200)
        self.assertEqual(self.bc.post(take_url(lead.pk)).status_code, 200)
        self.assertEqual(LeadStatusChange.objects.filter(lead=lead).count(), 2)

    def test_take_closed_lead_400(self):
        lead = self.lead()
        change_status(lead, 'rejected', by=self.broker)
        self.assertEqual(self.bc.post(take_url(lead.pk)).status_code, 400)
        lead.refresh_from_db()
        self.assertIsNone(lead.assigned_to)


class DetailTests(BrokerBase):
    def test_detail_fields_and_allowed_transitions(self):
        lead = self.lead(utm={'source': 'tiktok', 'campaign': 'c1'}, referrer='https://t.co/x',
                         entry_page_url='https://autoforyou.ua/', page_url='https://autoforyou.ua/calculator',
                         email='a@example.com', contact_handle='@ivan', comment='Привіт')
        r = self.bc.get(detail(lead.pk))
        d = r.data
        self.assertEqual(d['utm'], {'source': 'tiktok', 'campaign': 'c1'})
        for key in ('referrer', 'entry_page_url', 'page_url', 'first_response_at', 'email', 'contact_handle',
                    'comment', 'calculation_snapshot', 'history', 'public_id'):
            self.assertIn(key, d)
        self.assertEqual(d['allowed_transitions'], ['in_progress', 'rejected', 'spam'])
        for st in LeadStatus.values:
            lead.status = st
            lead.save()
            got = self.bc.get(detail(lead.pk)).data['allowed_transitions']
            self.assertEqual(set(got), {str(x) for x in ALLOWED_TRANSITIONS[st]})

    def test_mine_hides_attribution(self):
        user = make_user()
        self.lead(user=user, utm={'source': 'tiktok'}, referrer='https://t.co/x', page_url='https://x.ua/p')
        row = auth_client(user).get(MINE).data['results'][0]
        for key in ('utm', 'referrer', 'entry_page_url', 'page_url', 'first_response_at', 'phone', 'comment'):
            self.assertNotIn(key, row)

    def test_listing_in_detail(self):
        seller = make_user()
        listing = make_listing(make_vehicle(), seller)
        lead = create_lead(user=None, data={'name': 'Л', 'phone': '0671234567', 'source': 'listing'}, listing=listing)
        self.assertEqual(self.bc.get(detail(lead.pk)).data['listing']['id'], listing.pk)

    def test_first_response_matches_first_status_change(self):
        lead = self.lead()
        self.assertIsNone(self.bc.get(detail(lead.pk)).data['first_response_at'])
        self.bc.post(status_url(lead.pk), {'status': 'in_progress'}, format='json')
        change = LeadStatusChange.objects.filter(lead=lead).latest('pk')
        d = self.bc.get(detail(lead.pk)).data
        lead.refresh_from_db()
        self.assertLessEqual(lead.first_response_at, change.created_at)
        self.assertGreaterEqual(lead.first_response_at, lead.created_at)
        self.assertIsNotNone(d['first_response_at'])
        listed = self.bc.get(LIST).data['results'][0]
        self.assertEqual(listed['first_response_at'], d['first_response_at'])

    def test_spam_without_reaction_null(self):
        lead = self.lead()
        self.bc.post(status_url(lead.pk), {'status': 'spam'}, format='json')
        self.assertIsNone(self.bc.get(detail(lead.pk)).data['first_response_at'])

    def test_calculation_snapshot_exposed(self):
        from pricing.models import Calculation
        calc = Calculation.objects.create(
            inputs_snapshot={'make': 'Toyota', 'year': 2020}, rates_snapshot={'usd_uah': '41.5'},
            breakdown={'customs': '1000'}, total_usd=Decimal('9000.50'), total_uah=Decimal('373520.75'),
            is_estimate=True)
        lead = create_lead(user=None, data={'name': 'К', 'phone': '0671234567', 'source': 'calculator'},
                           calculation=calc)
        d = self.bc.get(detail(lead.pk)).data
        self.assertEqual(d['calculation_snapshot']['breakdown'], {'customs': '1000'})
        self.assertEqual(d['car'], 'Toyota 2020')


class PartnerStatusTests(BrokerBase):
    def test_partner_status_independent_of_status(self):
        lead = self.lead()
        r = self.bc.post(partner_url(lead.pk), {'partner_status': 'thinking'}, format='json')
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual((lead.partner_status, lead.status), ('thinking', 'new'))
        self.bc.post(status_url(lead.pk), {'status': 'in_progress'}, format='json')
        lead.refresh_from_db()
        self.assertEqual((lead.partner_status, lead.status), ('thinking', 'in_progress'))

    def test_partner_status_invalid_400(self):
        lead = self.lead()
        self.assertEqual(self.bc.post(partner_url(lead.pk), {'partner_status': 'zzz'}, format='json').status_code, 400)


class ModeratorTests(BrokerBase):
    def test_moderator_with_staff_403_admin_200(self):
        mod = make_moderator()
        self.assertTrue(mod.is_staff)
        self.assertEqual(auth_client(mod).get(LIST).status_code, 403)
        self.assertEqual(auth_client(make_admin_role()).get(LIST).status_code, 200)


class OwnershipTests(BrokerBase):
    def setUp(self):
        super().setUp()
        self.other = make_broker()
        self.oc = auth_client(self.other)

    def test_status_via_status_endpoint_assigns_current_broker(self):
        lead = self.lead()
        self.assertEqual(self.bc.post(status_url(lead.pk), {'status': 'in_progress'}, format='json').status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to, self.broker)

    def test_other_broker_gets_409_on_status_and_partner_status(self):
        lead = self.lead()
        self.bc.post(take_url(lead.pk))
        r = self.oc.post(status_url(lead.pk), {'status': 'contract'}, format='json')
        self.assertEqual(r.status_code, 409)
        r = self.oc.post(partner_url(lead.pk), {'partner_status': 'thinking'}, format='json')
        self.assertEqual(r.status_code, 409)
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.partner_status, lead.assigned_to), ('in_progress', '', self.broker))

    def test_admin_can_change_foreign_lead(self):
        lead = self.lead()
        self.bc.post(take_url(lead.pk))
        r = auth_client(make_admin_role()).post(status_url(lead.pk), {'status': 'contract'}, format='json')
        self.assertEqual(r.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.assigned_to), ('contract', self.broker))

    def test_force_ignored(self):
        lead = self.lead()
        for st in ('in_progress', 'contract', 'car_bought', 'in_transit', 'customs', 'delivered'):
            change_status(lead, st, by=self.broker)
        r = self.bc.post(status_url(lead.pk), {'status': 'in_progress', 'force': True}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Lead.objects.get(pk=lead.pk).status, 'delivered')

    def test_partner_status_journaled(self):
        lead = self.lead()
        self.bc.post(partner_url(lead.pk), {'partner_status': 'thinking'}, format='json')
        self.bc.post(partner_url(lead.pk), {'partner_status': 'thinking'}, format='json')  # без изменения
        self.bc.post(partner_url(lead.pk), {'partner_status': 'deposit'}, format='json')
        entries = list(LeadStatusChange.objects.filter(lead=lead).order_by('pk'))[1:]
        self.assertEqual([e.note for e in entries], ['partner: — → thinking', 'partner: thinking → deposit'])
        for e in entries:
            self.assertEqual((e.from_status, e.to_status, e.changed_by), ('new', 'new', self.broker))
        self.assertEqual(Lead.objects.get(pk=lead.pk).status, 'new')


class PrivacyTests(BrokerBase):
    def test_list_has_no_card_fields(self):
        self.lead(email='a@example.com', comment='секрет', contact_handle='@h', utm={'source': 'x'})
        row = self.bc.get(LIST).data['results'][0]
        for key in ('email', 'comment', 'contact_handle', 'utm', 'calculation_snapshot', 'history'):
            self.assertNotIn(key, row)

    def test_other_staff_email_hidden_from_broker_shown_to_self_and_admin(self):
        other = make_broker(first_name='Олена', last_name='К')
        lead = self.lead()
        auth_client(other).post(take_url(lead.pk))
        for url_data in (self.bc.get(detail(lead.pk)).data, self.bc.get(LIST).data['results'][0]):
            self.assertEqual(url_data['assigned_to'], {'id': other.pk, 'name': 'Олена К'})
        d = self.bc.get(detail(lead.pk)).data
        self.assertNotIn(other.email, str(d))
        self.assertNotIn('email', d['history'][-1]['changed_by'])
        mine = auth_client(other).get(detail(lead.pk)).data
        self.assertEqual(mine['assigned_to']['email'], other.email)
        adm = auth_client(make_admin_role()).get(detail(lead.pk)).data
        self.assertEqual(adm['assigned_to']['email'], other.email)

    def test_nameless_staff_shown_as_broker_id(self):
        lead = self.lead()
        auth_client(make_broker()).post(take_url(lead.pk))
        self.assertTrue(self.bc.get(detail(lead.pk)).data['assigned_to']['name'].startswith('Брокер #'))
