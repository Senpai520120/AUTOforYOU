"""Журнал заявок и атрибуция (2.15): журнал в группу, квалификация, partner_status, окно атрибуции, CSV, воронка."""
import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from leads import exports, funnel
from leads.models import (
    Lead,
    LeadExportLog,
    LeadJournalSettings,
    LeadPartnerStatusChange,
    LeadStatusChange,
)
from leads.services import (
    add_months,
    create_lead,
    journal_text,
    qualify_lead,
    send_journal_message,
    set_partner_status,
)
from site_settings.models import SiteSettings
from telegram_bot.sender import SendResult
from tests.base import CleanCacheTestCase
from tests.factories import auth_client, make_admin_role, make_broker, make_staff, make_user
from users.services import assign_role

SEND = 'telegram_bot.sender.send_message'
LIST = '/api/v1/broker/leads/'
EXPORT = f'{LIST}export.csv'


def set_partner(name='Партнер Тест'):
    s = SiteSettings.load()
    s.partner_name = name
    s.save()


def make_calc():
    from pricing.models import Calculation
    return Calculation.objects.create(
        inputs_snapshot={'make': 'Toyota', 'model': 'Camry', 'year': 2020},
        rates_snapshot={}, breakdown={}, total_usd=Decimal('9000'), total_uah=Decimal('370000'))


def make_lead(**kw):
    calc = kw.pop('calculation', 'auto')
    if calc == 'auto':
        calc = make_calc()
    data = {'name': 'Іван Секретний', 'phone': '0671234567', 'contact_method': 'telegram',
            'source': 'landing', 'email': 'secret@example.com', 'comment': 'коментар-секрет',
            'city': 'Київ', 'budget_usd': Decimal('9000'),
            'referrer': 'https://ref.example/x', 'page_url': 'https://site.example/page'}
    data.update(kw)
    return create_lead(user=None, data=data, calculation=calc)


class Base(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        set_partner()
        self.broker = make_broker()
        self.bc = auth_client(self.broker)


@override_settings(LEAD_JOURNAL_CHAT_ID='-777', TELEGRAM_BOT_TOKEN='123:abc')
class JournalMessageTests(Base):
    def test_text_has_whitelist_only(self):
        lead = make_lead(name='<script>alert(1)</script>', city='<b>Київ</b>')
        text = journal_text(lead)
        for expected in (lead.public_id, 'Toyota Camry', '$9 000', 'UTC'):
            self.assertIn(expected, text)
        for forbidden in ('script', 'secret@example.com', '0671234567', '671234567', 'коментар-секрет',
                          'Секретний', 'https://', 'telegram'):
            self.assertNotIn(forbidden, text)
        self.assertIn('&lt;b&gt;Київ&lt;/b&gt;', text)

    def test_text_has_no_name_or_phone(self):
        lead = make_lead()
        self.assertNotIn(lead.name, journal_text(lead))
        self.assertNotIn(lead.phone, journal_text(lead))

    def test_saves_message_id_and_sends_once(self):
        lead = make_lead()
        with mock.patch(SEND, return_value=SendResult(ok=True, message_id=4242)) as send:
            self.assertEqual(send_journal_message(lead.pk), 'sent')
            self.assertEqual(send_journal_message(lead.pk), 'already_sent')
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], '-777')
        lead.refresh_from_db()
        self.assertEqual(lead.journal_message_id, 4242)
        self.assertIsNotNone(lead.journal_sent_at)

    def test_failure_returns_failed_and_can_be_retried(self):
        lead = make_lead()
        with mock.patch(SEND, side_effect=ConnectionError('TelegramNetworkError')):
            self.assertEqual(send_journal_message(lead.pk), 'failed')
        with mock.patch(SEND, return_value=SendResult(ok=False, reason='TelegramAPIError')):
            self.assertEqual(send_journal_message(lead.pk), 'failed')
        lead.refresh_from_db()
        self.assertIsNone(lead.journal_message_id)
        self.assertIsNone(lead.journal_sending_at)
        with mock.patch(SEND, return_value=SendResult(ok=True, message_id=1)):
            self.assertEqual(send_journal_message(lead.pk), 'sent')

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_task_calls_retry_without_exception_object(self):
        from celery.exceptions import Retry

        from leads.tasks import send_journal_task
        lead = make_lead()
        with mock.patch(SEND, side_effect=ConnectionError('boom')), \
                mock.patch.object(send_journal_task, 'retry', side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                send_journal_task.run(lead.pk)
        retry.assert_called_once()
        self.assertNotIn('exc', retry.call_args.kwargs)

    def test_second_run_while_sending_does_not_send_twice(self):
        lead = make_lead()
        Lead.objects.filter(pk=lead.pk).update(journal_sending_at=timezone.now())
        with mock.patch(SEND) as send:
            self.assertEqual(send_journal_message(lead.pk), 'in_progress')
        send.assert_not_called()
        # Застрявшая метка (сбой воркера) снимается через несколько минут.
        Lead.objects.filter(pk=lead.pk).update(journal_sending_at=timezone.now() - timedelta(minutes=6))
        with mock.patch(SEND, return_value=SendResult(ok=True, message_id=5)):
            self.assertEqual(send_journal_message(lead.pk), 'sent')

    def test_claim_is_set_while_sending(self):
        lead = make_lead()
        seen = {}

        def fake(*args, **kwargs):
            seen['claimed'] = Lead.objects.get(pk=lead.pk).journal_sending_at is not None
            return SendResult(ok=True, message_id=3)

        with mock.patch(SEND, side_effect=fake):
            send_journal_message(lead.pk)
        self.assertTrue(seen['claimed'])

    def test_periodic_resend(self):
        from leads.tasks import resend_journal
        old, fresh, done = make_lead(), make_lead(), make_lead()
        Lead.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        Lead.objects.filter(pk=done.pk).update(
            created_at=timezone.now() - timedelta(minutes=30), journal_message_id=1)
        with mock.patch(SEND, return_value=SendResult(ok=True, message_id=77)) as send:
            result = resend_journal()
        self.assertEqual(result, {'sent': 1, 'tried': 1})
        send.assert_called_once()
        old.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(old.journal_message_id, 77)
        self.assertIsNone(fresh.journal_message_id)

    def test_periodic_resend_registered_in_beat(self):
        from django.conf import settings
        tasks = {v['task'] for v in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn('leads.tasks.resend_journal', tasks)

    def test_free_text_with_contacts_replaced(self):
        for city in ('+380671234567', '067 123 45 67', '(067)-123-45-67', '@nick', 'a@b.ua', '1 2 3 4 5'):
            with self.subTest(city=city):
                text = journal_text(make_lead(city=city))
                self.assertIn('Місто: не вказано', text)
                self.assertNotIn('nick', text)
                self.assertNotIn('b.ua', text)
                self.assertNotIn('6712', text)

    def test_client_vehicle_label_never_used(self):
        lead = make_lead(vehicle_label='Camry +380671234567')
        text = journal_text(lead)
        self.assertNotIn('380671234567', text)
        self.assertIn('Toyota Camry 2020', text)
        bare = make_lead(vehicle_label='Мій текст', calculation=None)
        self.assertNotIn('Мій текст', journal_text(bare))

    @override_settings(LEAD_JOURNAL_CHAT_ID='')
    def test_disabled_without_chat_id(self):
        lead = make_lead()
        with mock.patch(SEND) as send:
            self.assertEqual(send_journal_message(lead.pk), 'disabled')
        send.assert_not_called()

    def test_create_lead_schedules_journal_and_survives_hook_failure(self):
        with mock.patch(SEND, return_value=SendResult(ok=True, message_id=9)) as send:
            with self.captureOnCommitCallbacks(execute=True):
                lead = make_lead()
        chats = [c.args[0] for c in send.call_args_list]
        self.assertIn('-777', chats)
        lead.refresh_from_db()
        self.assertEqual(lead.journal_message_id, 9)
        with mock.patch('leads.services.notify_journal', side_effect=RuntimeError('x')):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(make_lead().pk)


class QualificationTests(Base):
    def answers(self, lead, *vals):
        keys = ('q_budget_ok', 'q_term_ok', 'q_knows_repair', 'q_ready_deposit')
        return qualify_lead(lead, dict(zip(keys, vals, strict=True)), by=self.broker)

    def test_scores(self):
        lead = make_lead(budget_usd=None)
        self.assertEqual(self.answers(lead, True, True, True, True).qualification, 'hot')
        self.assertEqual(self.answers(lead, True, True, True, False).qualification, 'hot')
        self.assertEqual(self.answers(lead, True, True, False, False).qualification, 'cold')

    def test_unrated_until_all_answered(self):
        lead = make_lead(budget_usd=None)
        self.assertEqual(self.answers(lead, True, True, True, None).qualification, 'unrated')

    def test_threshold_from_settings(self):
        cfg = LeadJournalSettings.get_solo()
        cfg.hot_min_score = 4
        cfg.save()
        lead = make_lead(budget_usd=None)
        self.assertEqual(self.answers(lead, True, True, True, False).qualification, 'cold')

    def test_budget_auto_uses_settings_threshold(self):
        lead = make_lead(budget_usd=Decimal('8000'))
        self.assertTrue(lead.q_budget_ok)
        self.assertFalse(make_lead(budget_usd=Decimal('7999.99')).q_budget_ok)
        cfg = LeadJournalSettings.get_solo()
        cfg.hot_budget_usd = Decimal('20000')
        cfg.save()
        self.assertFalse(make_lead(budget_usd=Decimal('8000')).q_budget_ok)
        fresh = make_lead(budget_usd=Decimal('9000'))
        Lead.objects.filter(pk=fresh.pk).update(q_budget_ok=None)
        fresh.refresh_from_db()
        qualify_lead(fresh, {'q_term_ok': True}, by=self.broker)
        fresh.refresh_from_db()
        self.assertFalse(fresh.q_budget_ok)

    def test_api_permissions(self):
        lead = make_lead()
        url = f'{LIST}{lead.pk}/qualification/'
        body = {'q_term_ok': True, 'q_knows_repair': True, 'q_ready_deposit': True}
        self.assertEqual(auth_client(make_user()).post(url, body, format='json').status_code, 403)
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().post(url, body, format='json').status_code, 401)
        resp = self.bc.post(url, body, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['qualification'], 'hot')

    def test_api_rejects_non_boolean(self):
        lead = make_lead()
        resp = self.bc.post(f'{LIST}{lead.pk}/qualification/', {'q_term_ok': 'maybe'}, format='json')
        self.assertEqual(resp.status_code, 400)


class PartnerStatusJournalTests(Base):
    def test_changes_journaled_and_independent(self):
        lead = make_lead()
        set_partner_status(lead, 'thinking', by=self.broker)
        set_partner_status(lead, 'thinking', by=self.broker)
        set_partner_status(lead, 'deposit', by=self.broker)
        rows = list(LeadPartnerStatusChange.objects.filter(lead=lead).values_list('from_status', 'to_status'))
        self.assertEqual(rows, [('', 'thinking'), ('thinking', 'deposit')])
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.partner_status), ('new', 'deposit'))

    def test_journal_rows_are_immutable(self):
        lead = make_lead()
        set_partner_status(lead, 'thinking', by=self.broker)
        row = LeadPartnerStatusChange.objects.get(lead=lead)
        with self.assertRaises(Exception):
            row.delete()
        row.to_status = 'bought'
        with self.assertRaises(Exception):
            row.save()
        row.refresh_from_db()
        self.assertEqual(row.to_status, 'thinking')


class AttributionTests(Base):
    def test_add_months(self):
        aug31 = datetime(2026, 8, 31, 10, 0, tzinfo=UTC)
        self.assertEqual(add_months(aug31, 6), datetime(2027, 2, 28, 10, 0, tzinfo=UTC))
        self.assertEqual(add_months(datetime(2027, 8, 31, tzinfo=UTC), 6).day, 29)
        self.assertEqual(add_months(aug31, 12), datetime(2027, 8, 31, 10, 0, tzinfo=UTC))

    def test_default_window_is_12_months_and_old_leads_unchanged(self):
        lead = make_lead()
        self.assertAlmostEqual((lead.attribution_until - add_months(lead.created_at, 12)).total_seconds(), 0, delta=1)
        cfg = LeadJournalSettings.get_solo()
        cfg.attribution_window_months = 6
        cfg.save()
        newer = make_lead()
        self.assertAlmostEqual((newer.attribution_until - add_months(newer.created_at, 6)).total_seconds(), 0, delta=1)
        before = lead.attribution_until
        lead.refresh_from_db()
        self.assertEqual(lead.attribution_until, before)

    def test_defaults_are_data(self):
        cfg = LeadJournalSettings.get_solo()
        self.assertEqual((cfg.hot_min_score, cfg.hot_budget_usd, cfg.attribution_window_months),
                         (3, Decimal('8000.00'), 12))


class DeletionTests(Base):
    def test_broker_has_no_delete_permissions(self):
        group = Group.objects.get(name='Брокери')
        codes = set(group.permissions.filter(content_type__app_label='leads').values_list('codename', flat=True))
        self.assertTrue({'view_lead', 'change_lead'} <= codes)
        self.assertEqual({c for c in codes if c.startswith('delete_')}, set())
        self.assertFalse(self.broker.has_perm('leads.delete_lead'))

    def test_api_delete_is_405(self):
        lead = make_lead()
        for url in (f'{LIST}{lead.pk}/', LIST):
            self.assertEqual(self.bc.delete(url).status_code, 405)
        self.assertTrue(Lead.objects.filter(pk=lead.pk).exists())

    def test_admin_delete_only_superuser(self):
        lead = make_lead()
        url = reverse('admin:leads_lead_delete', args=[lead.pk])
        for user in (self.broker, make_admin_role()):
            c = Client()
            c.force_login(user)
            self.assertEqual(c.post(url, {'post': 'yes'}).status_code, 403)
        self.assertTrue(Lead.objects.filter(pk=lead.pk).exists())
        c = Client()
        c.force_login(make_staff(superuser=True))
        self.assertEqual(c.post(url, {'post': 'yes'}).status_code, 302)
        self.assertFalse(Lead.objects.filter(pk=lead.pk).exists())

    def test_status_journal_not_deletable_in_admin(self):
        lead = make_lead()
        entry = LeadStatusChange.objects.get(lead=lead)
        self.assertEqual(entry.lead_id, lead.pk)
        from django.contrib.admin.sites import site

        from leads.admin import LeadStatusChangeInline
        inline = LeadStatusChangeInline(Lead, site)
        self.assertFalse(inline.can_delete)


class CsvSafeTests(Base):
    def test_csv_safe_leading_whitespace(self):
        for raw in (' =1', '\n=1', '\r\n@x', ' \t-2', '  +3'):
            self.assertTrue(exports.csv_safe(raw).startswith("'"), repr(raw))

    def test_csv_safe(self):
        for raw in ('=HYPERLINK("x")', '+1', '-1', '@a', '\tx', '\rx'):
            self.assertTrue(exports.csv_safe(raw).startswith("'"), raw)
        self.assertEqual(exports.csv_safe('Київ'), 'Київ')
        self.assertEqual(exports.csv_safe(None), '')


class ExportTests(Base):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead_export': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, client=None, **params):
        resp = (client or self.bc).get(EXPORT, params)
        body = b''.join(resp.streaming_content).decode('utf-8-sig') if resp.status_code == 200 else ''
        return resp, body

    def test_access_matrix(self):
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().get(EXPORT).status_code, 401)
        self.assertEqual(auth_client(make_user()).get(EXPORT).status_code, 403)
        self.assertEqual(auth_client(make_staff()).get(EXPORT).status_code, 403)
        for user in (self.broker, make_admin_role()):
            resp, _ = self.get(auth_client(user))
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp['Content-Type'].startswith('text/csv'))
            self.assertIn('attachment', resp['Content-Disposition'])

    def test_no_pii_in_file(self):
        make_lead(utm={'source': 'tiktok', 'campaign': 'spring'})
        _, body = self.get()
        header = body.splitlines()[0].split(',')
        self.assertEqual(header, exports.COLUMNS)
        for forbidden in ('Секретний', '0671234567', '671234567', 'secret@example.com', 'коментар-секрет',
                          'ref.example', 'site.example', 'phone', 'email', 'comment', 'referrer'):
            self.assertNotIn(forbidden, body, forbidden)
        rows = list(csv.DictReader(io.StringIO(body)))
        self.assertEqual(rows[0]['utm_source'], 'tiktok')
        self.assertEqual(rows[0]['city'], 'Київ')
        self.assertEqual(rows[0]['partner_name'], 'Партнер Тест')
        self.assertEqual(rows[0]['budget_usd'], '9000.00')

    def test_formula_injection_escaped(self):
        lead = make_lead(city='=HYPERLINK("http://evil")')
        Lead.objects.filter(pk=lead.pk).update(utm={'source': '@cmd', 'campaign': '+1'})
        _, body = self.get()
        row = next(csv.DictReader(io.StringIO(body)))
        self.assertEqual(row['city'], '\'=HYPERLINK("http://evil")')
        self.assertEqual(row['utm_source'], "'@cmd")
        self.assertEqual(row['utm_campaign'], "'+1")

    def test_filters_status_and_period(self):
        a, b = make_lead(), make_lead()
        Lead.objects.filter(pk=b.pk).update(status='spam', created_at=datetime(2026, 1, 15, 12, tzinfo=UTC))
        _, body = self.get(status='spam')
        self.assertEqual([r['public_id'] for r in csv.DictReader(io.StringIO(body))], [b.public_id])
        _, body = self.get(date_from='2026-01-15', date_to='2026-01-15')
        self.assertEqual([r['public_id'] for r in csv.DictReader(io.StringIO(body))], [b.public_id])
        today = timezone.now().date().isoformat()
        _, body = self.get(date_from=today)
        self.assertEqual([r['public_id'] for r in csv.DictReader(io.StringIO(body))], [a.public_id])

    def test_bad_filters_400(self):
        self.assertEqual(self.bc.get(EXPORT, {'status': 'zzz'}).status_code, 400)
        self.assertEqual(self.bc.get(EXPORT, {'date_from': '15.01.2026'}).status_code, 400)

    def test_audit_written(self):
        make_lead()
        make_lead()
        self.get(status='new')
        log = LeadExportLog.objects.get()
        self.assertEqual((log.user, log.channel, log.row_count), (self.broker, 'api', 2))
        self.assertEqual(log.filters['status'], 'new')

    def test_throttle_429(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead_export': '2/hour'}):
            codes = [self.bc.get(EXPORT).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_admin_action(self):
        lead = make_lead()
        c = Client()
        c.force_login(self.broker)
        resp = c.post(reverse('admin:leads_lead_changelist'),
                      {'action': 'export_csv', '_selected_action': [lead.pk]})
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content).decode('utf-8-sig')
        self.assertIn(lead.public_id, body)
        self.assertNotIn('0671234567', body)
        self.assertEqual(LeadExportLog.objects.get().channel, 'admin')


class FunnelTests(Base):
    def test_numbers(self):
        month = datetime(2026, 3, 10, 12, tzinfo=UTC)
        leads = [make_lead(utm={'source': 'tiktok'} if i < 4 else {}) for i in range(10)]
        for i, lead in enumerate(leads):
            Lead.objects.filter(pk=lead.pk).update(
                created_at=month, qualification='hot' if i < 3 else 'cold',
                partner_status='deposit' if i < 2 else ('' if i < 7 else 'bought'))
        outsider = make_lead()
        Lead.objects.filter(pk=outsider.pk).update(created_at=datetime(2026, 4, 1, 0, 0, tzinfo=UTC))
        data = funnel.funnel(2026, 3)
        self.assertEqual((data['total'], data['hot']), (10, 3))
        self.assertEqual(dict(data['by_source']), {'tiktok': 4, funnel.DIRECT: 6})
        partner = dict(data['by_partner_status'])
        self.assertEqual((partner[funnel.NOT_SET], partner['Депозит'], partner['Куплено']), (5, 2, 3))

    def test_parse_month_fallback(self):
        now = timezone.now()
        for raw in (None, '', 'abc', '2026-13', '1999-01', '2026-1'):
            self.assertEqual(funnel.parse_month(raw), (now.year, now.month), raw)
        self.assertEqual(funnel.parse_month('2026-03'), (2026, 3))

    def test_page_access_and_no_pii(self):
        make_lead()
        url = reverse('admin:leads_lead_funnel')
        admin_user = make_staff()
        assign_role(admin_user, 'admin')
        c = Client()
        c.force_login(admin_user)
        resp = c.get(url, {'month': 'bad'})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for forbidden in ('Секретний', '0671234567', 'secret@example.com'):
            self.assertNotIn(forbidden, html)
        c = Client()
        c.force_login(self.broker)
        self.assertEqual(c.get(url).status_code, 403)
        self.assertEqual(Client().get(url).status_code, 302)
        c = Client()
        c.force_login(make_staff(superuser=True))
        self.assertEqual(c.get(url).status_code, 200)


class AdminFieldsTests(Base):
    def test_readonly_and_columns(self):
        from django.contrib.admin.sites import site

        from leads.admin import LeadAdmin
        ma = LeadAdmin(Lead, site)
        for field in ('public_id', 'attribution_until', 'journal_message_id', 'partner_name', 'created_at',
                      'qualification'):
            self.assertIn(field, ma.readonly_fields)
        self.assertIn('qualification', ma.list_filter)
        self.assertIn('partner_status', ma.list_filter)
        self.assertIn('qualification', ma.list_display)

    def test_admin_partner_status_change_is_journaled(self):
        lead = make_lead()
        c = Client()
        c.force_login(make_staff(superuser=True))
        form = {'status': lead.status, 'partner_status': 'thinking', 'assigned_to': '',
                'status_changes-TOTAL_FORMS': '0', 'status_changes-INITIAL_FORMS': '0',
                'partner_status_changes-TOTAL_FORMS': '0', 'partner_status_changes-INITIAL_FORMS': '0',
                'q_budget_ok': 'true', 'q_term_ok': 'true', 'q_knows_repair': 'true', 'q_ready_deposit': 'false'}
        resp = c.post(reverse('admin:leads_lead_change', args=[lead.pk]), form)
        self.assertEqual(resp.status_code, 302, getattr(resp, 'context', None) and resp.context['errors'])
        lead.refresh_from_db()
        self.assertEqual((lead.partner_status, lead.qualification), ('thinking', 'hot'))
        self.assertEqual(LeadPartnerStatusChange.objects.filter(lead=lead).count(), 1)


class AdminSecurityTests(Base):
    def form(self, lead, **over):
        d = {'status': lead.status, 'partner_status': '', 'assigned_to': '',
             'status_changes-TOTAL_FORMS': '0', 'status_changes-INITIAL_FORMS': '0',
             'partner_status_changes-TOTAL_FORMS': '0', 'partner_status_changes-INITIAL_FORMS': '0'}
        d.update(over)
        return d

    def test_broker_cannot_edit_foreign_lead_in_admin(self):
        other = make_broker()
        lead = make_lead()
        Lead.objects.filter(pk=lead.pk).update(assigned_to=other)
        c = Client()
        c.force_login(self.broker)
        resp = c.post(reverse('admin:leads_lead_change', args=[lead.pk]),
                      self.form(lead, partner_status='deposit', assigned_to=str(other.pk)))
        self.assertEqual(resp.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.partner_status, '')
        self.assertFalse(LeadPartnerStatusChange.objects.filter(lead=lead).exists())

    def test_broker_can_edit_own_lead_in_admin(self):
        lead = make_lead()
        Lead.objects.filter(pk=lead.pk).update(assigned_to=self.broker)
        c = Client()
        c.force_login(self.broker)
        resp = c.post(reverse('admin:leads_lead_change', args=[lead.pk]),
                      self.form(lead, partner_status='thinking', assigned_to=str(self.broker.pk)))
        self.assertEqual(resp.status_code, 302)
        lead.refresh_from_db()
        self.assertEqual(lead.partner_status, 'thinking')

    def test_admin_export_shares_throttle_and_logs_changelist_filters(self):
        lead = make_lead()
        url = reverse('admin:leads_lead_changelist') + '?status=new&q=0671234567'
        c = Client()
        c.force_login(self.broker)
        post = {'action': 'export_csv', '_selected_action': [lead.pk]}
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead_export': '2/hour'}):
            self.bc.get(EXPORT)  # API-запрос занимает общий счётчик
            codes = [c.post(url, post).status_code for _ in range(2)]
        self.assertEqual(codes, [200, 302])
        log = LeadExportLog.objects.get(channel='admin')
        self.assertEqual(log.filters, {'status': 'new', 'selected': 1})

    def test_journal_settings_admin_superuser_only(self):
        from django.contrib.admin.sites import site

        from leads.admin import LeadJournalSettingsAdmin
        ma = LeadJournalSettingsAdmin(LeadJournalSettings, site)
        req = mock.Mock()
        for user, expected in ((make_admin_role(), False), (self.broker, False), (make_staff(superuser=True), True)):
            req.user = user
            self.assertEqual(ma.has_change_permission(req), expected)
            self.assertFalse(ma.has_delete_permission(req))
            self.assertFalse(ma.has_add_permission(req))  # singleton уже создан

    def test_export_log_is_append_only(self):
        log = LeadExportLog.objects.create(channel='api', row_count=1)
        with self.assertRaises(Exception):
            log.delete()
        log.row_count = 5
        with self.assertRaises(Exception):
            log.save()
        with self.assertRaises(Exception):
            LeadExportLog.objects.all().delete()
        with self.assertRaises(Exception):
            LeadExportLog.objects.all().update(row_count=9)
        with self.assertRaises(Exception):
            LeadPartnerStatusChange.objects.all().update(to_status='x')
        self.assertEqual(LeadExportLog.objects.get().row_count, 1)
