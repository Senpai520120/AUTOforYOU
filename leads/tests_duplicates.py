"""Защита от дубля заявки (10.13): Idempotency-Key, повтор по телефону в окне, гонка, метки и счётчик «без ответа»."""
import uuid
from datetime import timedelta
from unittest import mock

from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone

from leads import notify, services
from leads.models import Lead, LeadNotificationSettings
from leads.serializers import BrokerLeadDetailSerializer, LeadCreatedSerializer
from leads.tasks import _in_app_once
from leads.tests_api import TURNSTILE, URL, LeadApiBase, body, make_calc, siteverify
from metrics.reports import unanswered_leads
from site_settings.models import SiteSettings
from tests.factories import auth_client, make_broker
from users.models import ConsentDocument, ConsentRecord

HOOKS = ('leads.services.notify_new_lead', 'leads.services.notify_journal', 'leads.services.record_metric')
KEY_HEADER = 'HTTP_IDEMPOTENCY_KEY'


class DupBase(LeadApiBase):
    def setUp(self):
        super().setUp()
        self.calc = make_calc()
        self.notify_mock = self.patch(HOOKS[0])
        self.journal_mock = self.patch(HOOKS[1])
        self.metric_mock = self.patch(HOOKS[2])

    def patch(self, target):
        patcher = mock.patch(target)
        m = patcher.start()
        self.addCleanup(patcher.stop)
        return m

    def send(self, key=None, **kw):
        extra = {KEY_HEADER: str(key)} if key is not None else {}
        kw.setdefault('calculation_id', self.calc.pk)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(URL, body(**kw), format='json', **extra)

    def lead_of(self, resp):
        return Lead.objects.select_related('duplicate_of').get(public_id=resp.json()['public_id'])


@override_settings(LEAD_DUPLICATE_WINDOW_MINUTES=60)
class IdempotencyKeyTests(DupBase):
    def test_same_key_same_phone_returns_first_lead(self):
        key = uuid.uuid4()
        first = self.send(key)
        second = self.send(key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(second.json()['public_id'], first.json()['public_id'])

    def test_replay_header_only_on_replay(self):
        key = uuid.uuid4()
        first = self.send(key)
        second = self.send(key)
        self.assertNotIn('Idempotent-Replay', first.headers)
        self.assertEqual(second.headers['Idempotent-Replay'], 'true')

    def test_replay_has_no_side_effects(self):
        key = uuid.uuid4()
        self.send(key)
        self.send(key)
        self.assertEqual(self.notify_mock.call_count, 1)
        self.assertEqual(self.journal_mock.call_count, 1)
        self.assertEqual(self.metric_mock.call_count, 1)

    def test_replay_without_valid_captcha_is_200(self):
        key = uuid.uuid4()
        with override_settings(**TURNSTILE), siteverify(True):
            first = self.send(key, captcha_token='tok')
        with override_settings(**TURNSTILE), siteverify(False):
            second = self.send(key, captcha_token='used')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)

    def test_new_key_with_bad_captcha_is_400(self):
        with override_settings(**TURNSTILE), siteverify(False):
            resp = self.send(uuid.uuid4(), captcha_token='bad')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Lead.objects.count(), 0)

    def test_same_key_other_phone_is_409_without_data(self):
        key = uuid.uuid4()
        first = self.send(key)
        resp = self.send(key, phone='0509998877')
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(Lead.objects.count(), 1)
        text = resp.content.decode() + str(dict(resp.headers))
        self.assertNotIn(first.json()['public_id'], text)
        self.assertNotIn('380671234567', text)

    def test_invalid_header_is_ignored(self):
        resp = self.send('abc')
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(Lead.objects.get().idempotency_key)

    def test_key_is_saved(self):
        key = uuid.uuid4()
        self.send(key)
        self.assertEqual(Lead.objects.get().idempotency_key, key)

    def test_key_is_not_bound_to_user(self):
        key = uuid.uuid4()
        self.send(key)
        resp = auth_client(make_broker()).post(
            URL, body(calculation_id=self.calc.pk), format='json', **{KEY_HEADER: str(key)})
        self.assertEqual(resp.status_code, 200)

    def test_invalid_phone_with_existing_key_is_400(self):
        key = uuid.uuid4()
        self.send(key)
        resp = self.send(key, phone='12')
        self.assertEqual(resp.status_code, 400)

    def test_race_integrity_error_returns_first_lead(self):
        key = uuid.uuid4()
        first = self.send(key)
        with mock.patch('leads.views.create_lead', side_effect=IntegrityError), \
                mock.patch('leads.views.find_replay', side_effect=[None, Lead.objects.get()]):
            resp = self.send(key)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['public_id'], first.json()['public_id'])
        self.assertEqual(Lead.objects.count(), 1)

    def test_integrity_error_without_key_is_not_swallowed(self):
        with mock.patch('leads.views.create_lead', side_effect=IntegrityError):
            with self.assertRaises(IntegrityError):
                self.send()

    def test_honeypot_skips_key_lookup(self):
        with mock.patch('leads.views.find_replay') as find:
            resp = self.send(uuid.uuid4(), website='http://spam')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(find.call_count, 0)
        self.assertEqual(Lead.objects.count(), 0)

    def test_partner_not_configured_is_503_before_key_lookup(self):
        s = SiteSettings.load()
        s.partner_name = ''
        s.save()
        with mock.patch('leads.views.find_replay') as find:
            resp = self.send(uuid.uuid4())
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(find.call_count, 0)

    def test_logs_have_no_phone_or_key(self):
        key = uuid.uuid4()
        self.send(key)
        with self.assertLogs('leads', level='INFO') as logs:
            self.send(key)
            self.send(phone='0671234567')
        text = '\n'.join(logs.output)
        self.assertIn('lead.dedup reason=key', text)
        self.assertIn('lead.dedup reason=phone_window', text)
        self.assertNotIn('380671234567', text)
        self.assertNotIn('0671234567', text)
        self.assertNotIn(str(key), text)


@override_settings(LEAD_DUPLICATE_WINDOW_MINUTES=60)
class PhoneWindowTests(DupBase):
    def test_same_phone_in_window_creates_duplicate(self):
        first = self.send(uuid.uuid4())
        second = self.send(uuid.uuid4(), comment='інший лот')
        self.assertEqual(second.status_code, 201)
        self.assertEqual(Lead.objects.count(), 2)
        self.assertEqual(self.lead_of(second).duplicate_of.public_id, first.json()['public_id'])

    def test_duplicate_without_key(self):
        self.send()
        second = self.send()
        self.assertEqual(second.status_code, 201)
        self.assertIsNotNone(self.lead_of(second).duplicate_of_id)

    def test_duplicate_notifies_broker_and_writes_partner_journal_without_metric(self):
        self.send()
        self.send()
        self.assertEqual(self.notify_mock.call_count, 2)
        self.assertEqual(self.journal_mock.call_count, 2)
        self.assertEqual(self.metric_mock.call_count, 1)

    def test_duplicate_records_partner_consent(self):
        self.send()
        dup = self.lead_of(self.send())
        self.assertEqual(
            ConsentRecord.objects.filter(lead=dup, document=ConsentDocument.PARTNER_TRANSFER).count(), 1)

    def test_public_response_hides_duplicate(self):
        first = self.send()
        second = self.send()
        self.assertEqual(set(second.json()), {'public_id', 'status', 'created_at'})
        self.assertNotIn(first.json()['public_id'], second.content.decode())
        self.assertNotIn('duplicate_of', LeadCreatedSerializer.Meta.fields)

    def test_chain_points_to_root(self):
        first = self.send()
        self.send()
        dup = self.lead_of(self.send())
        self.assertEqual(dup.duplicate_of.public_id, first.json()['public_id'])
        self.assertIsNone(dup.duplicate_of.duplicate_of_id)

    def test_phone_formats_are_one_phone(self):
        self.send(phone='0501234567')
        second = self.send(phone='+380 50 123 45 67')
        self.assertIsNotNone(self.lead_of(second).duplicate_of_id)

    def test_different_phones_not_duplicate(self):
        self.send(phone='0501234567')
        second = self.send(phone='0509876543')
        self.assertIsNone(self.lead_of(second).duplicate_of_id)
        self.assertEqual(self.metric_mock.call_count, 2)

    def test_just_inside_window_is_duplicate(self):
        t0 = timezone.now()
        with mock.patch('django.utils.timezone.now', return_value=t0):
            self.send()
        with mock.patch('django.utils.timezone.now', return_value=t0 + timedelta(minutes=60, seconds=-1)):
            inside = self.send()
        self.assertEqual(self.lead_of(inside).duplicate_of.created_at, t0)

    def test_exactly_window_is_not_duplicate(self):
        t0 = timezone.now()
        with mock.patch('django.utils.timezone.now', return_value=t0):
            self.send()
        with mock.patch('django.utils.timezone.now', return_value=t0 + timedelta(minutes=60)):
            outside = self.send()
        self.assertIsNone(self.lead_of(outside).duplicate_of_id)
        self.assertEqual(self.notify_mock.call_count, 2)
        self.assertEqual(self.metric_mock.call_count, 2)

    @override_settings(LEAD_DUPLICATE_WINDOW_MINUTES=0)
    def test_window_zero_disables_phone_check(self):
        self.send()
        second = self.send()
        self.assertIsNone(self.lead_of(second).duplicate_of_id)

    @override_settings(LEAD_DUPLICATE_WINDOW_MINUTES=0)
    def test_window_zero_keeps_key_replay(self):
        key = uuid.uuid4()
        self.send(key)
        self.assertEqual(self.send(key).status_code, 200)

    def test_original_deleted_keeps_duplicate(self):
        first = self.send()
        dup = self.lead_of(self.send())
        Lead.objects.get(public_id=first.json()['public_id']).delete()
        dup.refresh_from_db()
        self.assertIsNone(dup.duplicate_of_id)


@override_settings(LEAD_DUPLICATE_WINDOW_MINUTES=60)
class DuplicateTextsTests(DupBase):
    def make_pair(self):
        first = self.send()
        return self.lead_of(first), self.lead_of(self.send())

    def test_telegram_text_has_note_with_first_number(self):
        first, dup = self.make_pair()
        self.assertIn(f'Повтор заявки {first.public_id}', notify.render_new_lead_text(dup, '{id} {phone}'))

    def test_telegram_text_of_ordinary_lead_has_no_note(self):
        first, _ = self.make_pair()
        self.assertNotIn('Повтор', notify.render_new_lead_text(first, '{id} {phone}'))

    def test_telegram_text_fits_limit_with_note(self):
        _, dup = self.make_pair()
        dup.comment = 'я' * 1000
        text = notify.render_new_lead_text(dup, '{comment}' * 5)
        self.assertLessEqual(notify.tg_len(text), notify.TELEGRAM_LIMIT)
        self.assertIn('Повтор заявки', text)

    def test_email_has_note_without_pii(self):
        first, dup = self.make_pair()
        subject, text = notify.render_new_lead_email(dup, LeadNotificationSettings.get_solo())
        self.assertIn(first.public_id, subject)
        self.assertIn('Повтор', text)
        self.assertNotIn('380671234567', subject + text)

    def test_journal_text_has_note_without_pii(self):
        first, dup = self.make_pair()
        text = services.journal_text(dup)
        self.assertIn(f'Повтор заявки {first.public_id}', text)
        self.assertNotIn('380671234567', text)
        self.assertNotIn('Повтор', services.journal_text(first))

    def test_in_app_title_for_duplicate(self):
        _, dup = self.make_pair()
        with mock.patch('leads.notify.notify_brokers_in_app') as in_app:
            _in_app_once(dup, LeadNotificationSettings.get_solo())
        self.assertEqual(in_app.call_args.args[0], f'Повторна заявка {dup.public_id}')


@override_settings(LEAD_DUPLICATE_WINDOW_MINUTES=60)
class BrokerAndAlertsTests(DupBase):
    def test_unanswered_excludes_duplicates(self):
        first = self.send()
        self.send()
        Lead.objects.update(created_at=timezone.now() - timedelta(hours=5))
        warn, _ = unanswered_leads()
        self.assertEqual(warn, [self.lead_of(first).pk])

    def test_broker_serializer_returns_public_id_only(self):
        first = self.send()
        dup = self.lead_of(self.send())
        data = BrokerLeadDetailSerializer(dup, context={'request': None}).data
        self.assertEqual(data['duplicate_of'], first.json()['public_id'])

    def test_broker_api_returns_duplicate_of(self):
        first = self.send()
        dup = self.lead_of(self.send())
        resp = auth_client(make_broker()).get(f'/api/v1/broker/leads/{dup.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['duplicate_of'], first.json()['public_id'])
