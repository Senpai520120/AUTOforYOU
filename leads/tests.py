import threading
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from leads import services
from leads.models import Lead, LeadCounter, LeadStatus, LeadStatusChange
from leads.services import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    PartnerNotConfigured,
    change_status,
    create_lead,
)
from leads.validators import clean_attribution, normalize_ua_phone
from pricing.models import Calculation
from site_settings.models import SiteSettings
from tests.factories import (
    make_admin_role,
    make_broker,
    make_listing,
    make_moderator,
    make_staff,
    make_user,
    make_vehicle,
)
from users.services import assign_role


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


def data(**kw):
    d = {'name': 'Іван', 'phone': '0671234567', 'contact_method': 'telegram'}
    d.update(kw)
    return d


class NormalizePhoneTests(TestCase):
    def test_formats(self):
        for raw in ('+380671234567', '380671234567', '0671234567', '+38 (067) 123-45-67'):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_ua_phone(raw), '+380671234567')

    def test_invalid(self):
        for raw in ('12345', '', None, '+48671234567', '067123456', '06712345678', '+380abc1234567', '+380067123456', '+380٦٧١٢٣٤٥٦٧'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    normalize_ua_phone(raw)


class CleanAttributionTests(TestCase):
    def test_utm_garbage_dropped(self):
        for bad in ('abc', ['a'], 5, None, {'source': {'a': 1}}, {'source': ['x']}):
            with self.subTest(bad=bad):
                self.assertEqual(clean_attribution({'utm': bad})['utm'], {})

    def test_utm_whitelist_and_truncate(self):
        r = clean_attribution({'utm': {'term': 'x', 'source': 'tiktok', 'medium': '', 'campaign': 'c' * 300,
                                       'content': 'c' * 100}})
        self.assertEqual(r['utm'], {'source': 'tiktok', 'content': 'c' * 100})

    def test_utm_value_charset(self):
        r = clean_attribution({'utm': {'source': 'my-src_1.2', 'medium': '<script>', 'campaign': 'весна_2026',
                                       'content': 'a b'}})
        self.assertEqual(r['utm'], {'source': 'my-src_1.2', 'campaign': 'весна_2026'})

    def test_referrer(self):
        self.assertEqual(clean_attribution({'referrer': 'https://t.me/x?startapp=secret#frag'})['referrer'],
                         'https://t.me')
        self.assertEqual(clean_attribution({'referrer': 'javascript:alert(1)'})['referrer'], '')
        self.assertEqual(clean_attribution({'referrer': 'data:text/html,x'})['referrer'], '')
        self.assertEqual(clean_attribution({'referrer': 123})['referrer'], '')

    def test_pages(self):
        r = clean_attribution({'page_url': 'https://evil.test/calculator?x=1', 'entry_page_url': '//evil.test'})
        self.assertEqual(r['page_url'], '/calculator')
        self.assertEqual(r['entry_page_url'], '')
        self.assertEqual(clean_attribution({'page_url': '/lot/5?a=b#c'})['page_url'], '/lot/5')
        self.assertEqual(clean_attribution({'page_url': 'javascript:alert(1)'})['page_url'], '')
        self.assertEqual(clean_attribution({'page_url': 'calculator'})['page_url'], '')

    def test_non_dict_input(self):
        self.assertEqual(clean_attribution('x'),
                         {'utm': {}, 'referrer': '', 'entry_page_url': '', 'page_url': ''})


class CreateLeadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_partner()

    def test_guest_with_calculation_snapshot(self):
        calc = make_calc()
        lead = create_lead(user=None, data=data(), calculation=calc)
        self.assertEqual(lead.status, LeadStatus.NEW)
        self.assertEqual(lead.phone, '+380671234567')
        self.assertEqual(lead.source, 'calculator')
        snap = lead.calculation_snapshot
        self.assertEqual(snap['inputs_snapshot'], calc.inputs_snapshot)
        self.assertEqual(snap['rates_snapshot'], calc.rates_snapshot)
        self.assertEqual(snap['breakdown'], calc.breakdown)
        self.assertEqual(snap['calculation_id'], calc.pk)
        self.assertEqual(lead.total_usd, Decimal('9000.50'))
        self.assertEqual(lead.total_uah, Decimal('373520.75'))
        changes = list(lead.status_changes.all())
        self.assertEqual(len(changes), 1)
        self.assertEqual((changes[0].from_status, changes[0].to_status), ('', 'new'))
        self.assertIsNotNone(lead.consent_at)
        self.assertIsNotNone(lead.partner_consent_at)

    def test_user_attached(self):
        user = make_user()
        lead = create_lead(user=user, data=data())
        self.assertEqual(lead.user, user)

    def test_listing_source_and_vehicle_label(self):
        listing = make_listing(make_vehicle(make='Honda', model='Civic'), make_staff())
        lead = create_lead(user=None, data=data(), listing=listing)
        self.assertEqual(lead.source, 'listing')
        self.assertEqual(lead.vehicle_label, 'Honda Civic')

    def test_vehicle_label_from_listing_ignores_client_value(self):
        listing = make_listing(make_vehicle(make='Honda', model='Civic'), make_staff())
        lead = create_lead(user=None, data=data(vehicle_label='Ferrari Fake'), listing=listing)
        self.assertEqual(lead.vehicle_label, 'Honda Civic')

    def test_attribution_cleaned(self):
        lead = create_lead(user=None, data=data(
            utm={'term': 'x', 'source': 'tiktok'}, referrer='https://t.me/x?a=1', page_url='https://e.test/calc?x=1',
        ))
        self.assertEqual(lead.utm, {'source': 'tiktok'})
        self.assertEqual(lead.referrer, 'https://t.me')
        self.assertEqual(lead.page_url, '/calc')

    def test_partner_name_is_snapshot(self):
        lead = create_lead(user=None, data=data())
        set_partner('Інша назва')
        lead.refresh_from_db()
        self.assertEqual(lead.partner_name, 'Партнер Тест')
        self.assertIn('Партнер Тест', lead.partner_consent_text)

    def test_empty_partner_name_rejected(self):
        set_partner('')
        with self.assertRaises(PartnerNotConfigured):
            create_lead(user=None, data=data())
        self.assertEqual(Lead.objects.count(), 0)

    def test_snapshot_survives_calculation_delete(self):
        calc = make_calc()
        lead = create_lead(user=None, data=data(), calculation=calc)
        calc.delete()
        lead.refresh_from_db()
        self.assertIsNone(lead.calculation)
        self.assertEqual(lead.calculation_snapshot['inputs_snapshot']['make'], 'Toyota')
        self.assertEqual(lead.total_usd, Decimal('9000.50'))

    def test_on_commit_hooks_once(self):
        with mock.patch.object(services, 'notify_new_lead') as notify, \
                mock.patch.object(services, 'record_metric') as metric:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                lead = create_lead(user=None, data=data())
            self.assertEqual(len(callbacks), 1)
            notify.assert_called_once_with(lead.pk)
            metric.assert_called_once_with('lead_created')

    def test_no_hooks_without_commit(self):
        with mock.patch.object(services, 'notify_new_lead') as notify, \
                mock.patch.object(services, 'record_metric') as metric:
            with self.captureOnCommitCallbacks(execute=False):
                create_lead(user=None, data=data())
            notify.assert_not_called()
            metric.assert_not_called()

    def test_notify_enqueues_task_with_id_only(self):
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            services.notify_new_lead(7)
        delay.assert_called_once_with(7)


class PublicIdTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_partner()

    def test_sequential_format(self):
        year = timezone.now().year
        ids = [create_lead(user=None, data=data()).public_id for _ in range(3)]
        self.assertEqual(ids, [f'AFY-{year}-000{i}' for i in (1, 2, 3)])

    def test_resets_by_year(self):
        for year in (2030, 2031):
            self.assertEqual(services._next_public_id(year), f'AFY-{year}-0001')
        self.assertEqual(services._next_public_id(2030), 'AFY-2030-0002')

    def test_unique_constraint(self):
        a = create_lead(user=None, data=data())
        b = create_lead(user=None, data=data())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lead.objects.filter(pk=b.pk).update(public_id=a.public_id)


class PublicIdConcurrencyTests(TransactionTestCase):
    def test_parallel_unique(self):
        if connection.vendor == 'sqlite':
            self.skipTest('SQLite: нет построчных блокировок; проверяется в CI на PostgreSQL')
        set_partner()
        errors = []

        def worker():
            try:
                create_lead(user=None, data=data())
            except Exception as exc:  # pragma: no cover
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        ids = list(Lead.objects.values_list('public_id', flat=True))
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(LeadCounter.objects.get().last_number, 8)


class ChangeStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_partner()
        cls.broker = make_staff()

    def setUp(self):
        self.lead = create_lead(user=None, data=data())

    def test_full_path(self):
        path = ['in_progress', 'contract', 'car_bought', 'in_transit', 'customs', 'delivered']
        for st in path:
            change_status(self.lead, st, by=self.broker)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'delivered')
        self.assertEqual(self.lead.status_changes.count(), 1 + len(path))

    def test_invalid_transition(self):
        with self.assertRaises(InvalidTransition):
            change_status(self.lead, 'delivered', by=self.broker)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'new')
        self.assertEqual(self.lead.status_changes.count(), 1)

    def test_unknown_status(self):
        with self.assertRaises(InvalidTransition):
            change_status(self.lead, 'bogus', by=self.broker)

    def test_final_states_have_no_transitions(self):
        for st in ('delivered', 'rejected', 'spam'):
            self.assertEqual(ALLOWED_TRANSITIONS[st], set())

    def test_journal_entry(self):
        change_status(self.lead, 'in_progress', by=self.broker, note='дзвінок')
        ch = self.lead.status_changes.last()
        self.assertEqual((ch.from_status, ch.to_status, ch.changed_by, ch.note),
                         ('new', 'in_progress', self.broker, 'дзвінок'))

    def test_force_reopen(self):
        change_status(self.lead, 'rejected', by=self.broker)
        with self.assertRaises(InvalidTransition):
            change_status(self.lead, 'new', by=self.broker)
        change_status(self.lead, 'new', by=self.broker, force=True)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'new')

    def test_first_response_set_once(self):
        self.assertIsNone(self.lead.first_response_at)
        change_status(self.lead, 'in_progress', by=self.broker)
        first = self.lead.first_response_at
        self.assertIsNotNone(first)
        change_status(self.lead, 'contract', by=self.broker)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.first_response_at, first)

    def test_spam_does_not_set_first_response(self):
        change_status(self.lead, 'spam', by=self.broker)
        self.assertIsNone(self.lead.first_response_at)
        change_status(self.lead, 'new', by=self.broker, force=True)
        self.assertIsNone(self.lead.first_response_at)
        change_status(self.lead, 'in_progress', by=self.broker)
        self.lead.refresh_from_db()
        self.assertIsNotNone(self.lead.first_response_at)

    def test_reopen_keeps_first_response(self):
        change_status(self.lead, 'in_progress', by=self.broker)
        first = self.lead.first_response_at
        change_status(self.lead, 'new', by=self.broker, force=True)
        change_status(self.lead, 'in_progress', by=self.broker)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.first_response_at, first)

    def test_db_constraint_blocks_bad_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lead.objects.filter(pk=self.lead.pk).update(status='active')


class LeadAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_partner()
        cls.admin = make_staff(superuser=True)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin)

    def _post_data(self, lead, **over):
        d = {'status': lead.status, 'partner_status': '', 'assigned_to': '',
             'status_changes-TOTAL_FORMS': '0', 'status_changes-INITIAL_FORMS': '0',
             'status_changes-MIN_NUM_FORMS': '0', 'status_changes-MAX_NUM_FORMS': '1000'}
        d.update(over)
        return d

    def test_status_change_via_admin_writes_journal(self):
        lead = create_lead(user=None, data=data())
        url = reverse('admin:leads_lead_change', args=[lead.pk])
        resp = self.client.post(url, self._post_data(lead, status='in_progress'))
        self.assertEqual(resp.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'in_progress')
        ch = LeadStatusChange.objects.filter(lead=lead).latest('pk')
        self.assertEqual((ch.from_status, ch.to_status, ch.changed_by), ('new', 'in_progress', self.admin))
        self.assertIsNotNone(lead.first_response_at)

    def test_non_admin_invalid_transition_rejected(self):
        broker = make_staff(is_superuser=False)
        from django.contrib.auth.models import Permission
        broker.user_permissions.add(*Permission.objects.filter(content_type__app_label='leads'))
        lead = create_lead(user=None, data=data())
        c = Client()
        c.force_login(broker)
        resp = c.post(reverse('admin:leads_lead_change', args=[lead.pk]),
                      self._post_data(lead, status='delivered'), follow=True)
        self.assertEqual(resp.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'new')
        self.assertEqual(lead.status_changes.count(), 1)

    def test_source_fields_readonly(self):
        lead = create_lead(user=None, data=data(utm={'source': 'tiktok'}))
        url = reverse('admin:leads_lead_change', args=[lead.pk])
        self.client.post(url, self._post_data(lead, name='Хакер', phone='+380000000000',
                                              utm='{"source": "x"}', page_url='/x'))
        lead.refresh_from_db()
        self.assertEqual((lead.name, lead.phone, lead.utm), ('Іван', '+380671234567', {'source': 'tiktok'}))
        resp = self.client.get(url)
        self.assertNotContains(resp, 'name="utm"')
        self.assertNotContains(resp, 'name="first_response_at"')

    def test_utm_source_filter_and_column(self):
        create_lead(user=None, data=data(name='Тікток', utm={'source': 'tiktok'}))
        create_lead(user=None, data=data(name='Прямий'))
        url = reverse('admin:leads_lead_changelist')
        resp = self.client.get(url, {'utm_source': 'tiktok'})
        self.assertContains(resp, 'Тікток')
        self.assertNotContains(resp, 'Прямий')
        resp = self.client.get(url)
        self.assertContains(resp, 'пряме')
        self.assertContains(resp, 'tiktok')

    def test_add_disabled_delete_superuser_only(self):
        self.assertEqual(self.client.get(reverse('admin:leads_lead_add')).status_code, 403)
        lead = create_lead(user=None, data=data())
        staff = make_staff()
        from django.contrib.auth.models import Permission
        staff.user_permissions.add(*Permission.objects.filter(content_type__app_label='leads'))
        c = Client()
        c.force_login(staff)
        resp = c.post(reverse('admin:leads_lead_delete', args=[lead.pk]), {'post': 'yes'})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Lead.objects.filter(pk=lead.pk).exists())

    def test_change_page_shows_snapshot_summary(self):
        lead = create_lead(user=None, data=data(), calculation=make_calc())
        resp = self.client.get(reverse('admin:leads_lead_change', args=[lead.pk]))
        self.assertContains(resp, 'Toyota')
        self.assertContains(resp, '9000.50')


class HardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_partner()

    def test_invalid_source_falls_back_to_landing(self):
        lead = create_lead(user=None, data=data(source='hacked'))
        self.assertEqual(lead.source, 'landing')

    def test_db_constraint_source(self):
        lead = create_lead(user=None, data=data())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lead.objects.filter(pk=lead.pk).update(source='bogus')

    def test_db_constraint_budget(self):
        lead = create_lead(user=None, data=data())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lead.objects.filter(pk=lead.pk).update(budget_usd=-1)

    def test_budget_validator(self):
        lead = create_lead(user=None, data=data())
        lead.budget_usd = Decimal('-5')
        with self.assertRaises(ValidationError):
            lead.full_clean()

    def test_notify_failure_does_not_break_create(self):
        with mock.patch.object(services, 'notify_new_lead', side_effect=RuntimeError('boom')),                 mock.patch.object(services, 'record_metric') as metric,                 self.assertLogs('leads.services', 'ERROR') as cm:
            with self.captureOnCommitCallbacks(execute=True):
                lead = create_lead(user=None, data=data())
        self.assertTrue(Lead.objects.filter(pk=lead.pk).exists())
        metric.assert_called_once_with('lead_created')
        self.assertNotIn('Іван', ''.join(cm.output))

    def test_foreign_calculation_rejected(self):
        owner, other = make_user(), make_user()
        calc = make_calc(owner)
        for u in (other, None):
            with self.subTest(user=u):
                with self.assertRaises(ValueError):
                    create_lead(user=u, data=data(), calculation=calc)
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(create_lead(user=owner, data=data(), calculation=calc).user, owner)

    def test_force_marked_in_journal(self):
        lead = create_lead(user=None, data=data())
        change_status(lead, 'rejected', by=make_staff())
        change_status(lead, 'new', by=make_staff(), force=True, note='клієнт передумав')
        self.assertEqual(lead.status_changes.last().note, 'force: клієнт передумав')


class LeadAdminRightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        set_partner()

    def _form(self, lead, **over):
        d = {'status': lead.status, 'partner_status': '', 'assigned_to': '',
             'status_changes-TOTAL_FORMS': '0', 'status_changes-INITIAL_FORMS': '0',
             'status_changes-MIN_NUM_FORMS': '0', 'status_changes-MAX_NUM_FORMS': '1000'}
        d.update(over)
        return d

    def _client(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_broker_view_change_not_delete(self):
        broker = make_broker()
        lead = create_lead(user=None, data=data())
        c = self._client(broker)
        change = reverse('admin:leads_lead_change', args=[lead.pk])
        self.assertEqual(c.get(change).status_code, 200)
        self.assertEqual(c.post(change, self._form(lead, status='in_progress')).status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'in_progress')
        self.assertEqual(c.post(reverse('admin:leads_lead_delete', args=[lead.pk]), {'post': 'yes'}).status_code, 403)
        self.assertTrue(Lead.objects.filter(pk=lead.pk).exists())

    def test_moderator_forbidden(self):
        c = self._client(make_moderator())
        self.assertEqual(c.get(reverse('admin:leads_lead_changelist')).status_code, 403)

    def test_assigned_to_limited(self):
        broker, admin_role, buyer = make_broker(), make_admin_role(), make_user()
        moderator = make_moderator()
        lead = create_lead(user=None, data=data())
        resp = self._client(broker).get(reverse('admin:leads_lead_change', args=[lead.pk]))
        qs = resp.context['adminform'].form.fields['assigned_to'].queryset
        self.assertEqual(set(qs), {broker, admin_role})
        self.assertNotIn(buyer, qs)
        self.assertNotIn(moderator, qs)

    def test_admin_role_needs_reopen_checkbox(self):
        admin_role = make_admin_role()
        assign_role(admin_role, 'admin')
        lead = create_lead(user=None, data=data())
        change_status(lead, 'rejected', by=admin_role)
        c = self._client(admin_role)
        url = reverse('admin:leads_lead_change', args=[lead.pk])
        resp = c.post(url, self._form(lead, status='new'))
        self.assertEqual(resp.status_code, 200)  # ошибка формы
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'rejected')
        resp = c.post(url, self._form(lead, status='new', reopen='on'))
        self.assertEqual(resp.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'new')
        self.assertTrue(lead.status_changes.last().note.startswith('force'))

    def test_broker_cannot_reopen(self):
        broker = make_broker()
        lead = create_lead(user=None, data=data())
        change_status(lead, 'rejected', by=broker)
        resp = self._client(broker).post(reverse('admin:leads_lead_change', args=[lead.pk]),
                                         self._form(lead, status='new', reopen='on'))
        self.assertEqual(resp.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, 'rejected')


class LeadConsentLogTests(TestCase):
    """Журнал согласий (1.14): lead_processing + partner_transfer пишутся в create_lead."""

    @classmethod
    def setUpTestData(cls):
        set_partner('Партнер А')

    def test_guest_lead_writes_records(self):
        from users.models import ConsentDocument, ConsentMethod, ConsentRecord
        s = SiteSettings.load()
        s.legal_docs_version = '2026-10-01'
        s.save()
        lead = create_lead(user=None, data=data())
        records = {r.document: r for r in ConsentRecord.objects.filter(lead=lead)}
        self.assertEqual(set(records), {ConsentDocument.LEAD_PROCESSING, ConsentDocument.PARTNER_TRANSFER})
        for r in records.values():
            self.assertIsNone(r.user)
            self.assertEqual(r.method, ConsentMethod.LEAD_FORM)
            self.assertEqual(r.doc_version, '2026-10-01')
        self.assertEqual(records[ConsentDocument.PARTNER_TRANSFER].partner_name, 'Партнер А')
        self.assertEqual(records[ConsentDocument.LEAD_PROCESSING].partner_name, '')
        for r in records.values():
            self.assertEqual(r.lead_public_id, lead.public_id)

    def test_logged_in_lead_has_user(self):
        from users.models import ConsentRecord
        user = make_user()
        lead = create_lead(user=user, data=data())
        self.assertEqual(ConsentRecord.objects.filter(lead=lead, user=user).count(), 2)

    def test_old_record_keeps_partner_after_rename(self):
        from users.models import ConsentDocument, ConsentRecord
        create_lead(user=None, data=data())
        set_partner('Партнер Б')
        create_lead(user=None, data=data())
        names = sorted(ConsentRecord.objects.filter(
            document=ConsentDocument.PARTNER_TRANSFER).values_list('partner_name', flat=True))
        self.assertEqual(names, ['Партнер А', 'Партнер Б'])

    def test_rollback_leaves_no_dangling_records(self):
        from users.models import ConsentRecord
        # Падение ПОСЛЕ записи согласий: внешняя транзакция откатывает и заявку, и журнал.
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                create_lead(user=None, data=data())
                self.assertEqual(ConsentRecord.objects.count(), 2)  # записи уже есть
                raise RuntimeError('boom')
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_failure_after_consents_inside_create_lead_rolls_back(self):
        from users.models import ConsentRecord

        def fail_after_write(*args, **kwargs):
            from users.consents import record_consents as real
            real(*args, **kwargs)
            raise RuntimeError('boom')

        with mock.patch('leads.services.record_consents', side_effect=fail_after_write):
            with self.assertRaises(RuntimeError):
                create_lead(user=None, data=data())
        self.assertEqual(Lead.objects.count(), 0)
        self.assertEqual(ConsentRecord.objects.count(), 0)

    def test_failed_consent_write_rolls_back_lead(self):
        with mock.patch('leads.services.record_consents', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                create_lead(user=None, data=data())
        self.assertEqual(Lead.objects.count(), 0)

    def test_no_contact_data_in_record(self):
        from users.models import ConsentRecord
        create_lead(user=None, data=data())
        blob = ' '.join(str(v) for r in ConsentRecord.objects.values() for v in r.values())
        self.assertNotIn('0671234567', blob)
        self.assertNotIn('Іван', blob)

    def test_backfill_migration_function(self):
        from importlib import import_module

        from django.apps import apps

        from users.models import ConsentRecord
        lead = create_lead(user=None, data=data())
        ConsentRecord._base_manager.all().delete()  # журнал неизменяем через обычный менеджер
        import_module('users.migrations.0014_backfill_lead_consents').backfill(apps, None)
        self.assertEqual(ConsentRecord.objects.filter(lead=lead).count(), 2)
        import_module('users.migrations.0014_backfill_lead_consents').backfill(apps, None)
        self.assertEqual(ConsentRecord.objects.filter(lead=lead).count(), 2)  # идемпотентно
