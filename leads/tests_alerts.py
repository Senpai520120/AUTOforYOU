"""Заявка не теряется молча (10.6): алерт владельцу о недоставке и счётчик «без ответа 2 ч / 24 ч»."""
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from itertools import count
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from leads import notify
from leads.models import Lead, LeadStatus, NotifyStatus
from leads.tasks import alert_unanswered_leads, resend_undelivered_leads
from metrics.reports import unanswered_leads
from notifications.models import Notification
from tests.base import CleanCacheTestCase
from tests.factories import make_admin_role, make_lead

TG = 'telegram_bot.sender.send_message'
MAIL = 'integrations.email.send_email'
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=dt_timezone.utc)
CHANNELS = dict(FAILED_TASK_ALERT_CHAT_ID='-100777', FAILED_TASK_ALERT_EMAIL='owner@afy-mail.test',
                SITE_URL='https://afy.example', LEAD_UNANSWERED_WARN_HOURS=2,
                LEAD_UNANSWERED_CRITICAL_HOURS=24, LEAD_UNANSWERED_ALERT_COOLDOWN_MINUTES=360)
TG_OK = mock.Mock(ok=True)
MAIL_OK = {'queued': True}
_ids = count(1)
MARKERS = dict(name='Маркерне Імя', phone='+380671112233', email='marker@pii.test', comment='маркерний коментар',
               vehicle_label='Marker Car 3000')


def lead_aged(age: timedelta, **kw):
    lead = make_lead(public_id=f'AFY-A-{next(_ids):04d}', **kw)
    Lead.objects.filter(pk=lead.pk).update(created_at=NOW - age)
    return lead


@override_settings(**CHANNELS)
class OwnerUndeliveredTests(CleanCacheTestCase):
    def exhausted(self, **kw):
        lead = make_lead(public_id=f'AFY-A-{next(_ids):04d}', **{**MARKERS, **kw})
        Lead.objects.filter(pk=lead.pk).update(
            telegram_status=NotifyStatus.FAILED, email_status=NotifyStatus.FAILED,
            notify_attempts=settings.LEAD_NOTIFY_MAX_ATTEMPTS)
        return Lead.objects.get(pk=lead.pk)

    def run_resend(self, tg=TG_OK, mail=MAIL_OK):
        with mock.patch(TG, return_value=tg) as tg_mock, mock.patch(MAIL, return_value=mail) as mail_mock:
            resend_undelivered_leads()
        return tg_mock, mail_mock

    def test_both_channels_and_in_app(self):
        make_admin_role()
        lead = self.exhausted()
        tg, mail = self.run_resend()
        self.assertEqual(tg.call_count, 1)
        self.assertEqual(mail.call_count, 1)
        self.assertEqual(Notification.objects.filter(type=Notification.Type.LEAD_UNDELIVERED).count(), 1)
        self.assertIn(lead.public_id, tg.call_args.args[1])

    def test_text_has_no_pii_but_has_id_and_link(self):
        lead = self.exhausted()
        text = notify.build_owner_undelivered_text([lead])
        for value in MARKERS.values():
            self.assertNotIn(value, text)
        self.assertIn(lead.public_id, text)
        self.assertIn(notify.unanswered_list_url(), text)

    def test_telegram_failure_does_not_block_email_and_keeps_mark(self):
        lead = self.exhausted()
        with mock.patch(TG, side_effect=ConnectionError('x')), mock.patch(MAIL, return_value=MAIL_OK) as mail, \
                self.assertLogs('core.tasks', level='WARNING'):
            resend_undelivered_leads()
        self.assertEqual(mail.call_count, 1)
        lead.refresh_from_db()
        self.assertIsNotNone(lead.undelivered_alerted_at)

    def test_email_failure_does_not_block_telegram(self):
        self.exhausted()
        with mock.patch(TG, return_value=TG_OK) as tg, mock.patch(MAIL, side_effect=OSError('x')), \
                self.assertLogs('core.tasks', level='WARNING'):
            resend_undelivered_leads()
        self.assertEqual(tg.call_count, 1)

    @override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL='')
    def test_no_channels_logs_warning_and_does_not_crash(self):
        lead = self.exhausted()
        with self.assertLogs('leads.notify', level='WARNING') as logs:
            tg, mail = self.run_resend()
        self.assertEqual(tg.call_count + mail.call_count, 0)
        self.assertIn('канал алерта владельцу не налаштовано', logs.output[0])
        lead.refresh_from_db()
        self.assertIsNotNone(lead.undelivered_alerted_at)

    def test_delivery_failure_warns_and_next_run_retries(self):
        self.exhausted()
        with self.assertLogs('leads.notify', level='WARNING') as logs:
            tg, mail = self.run_resend(tg=mock.Mock(ok=False), mail={'queued': False})
        self.assertEqual(tg.call_count, 1)
        self.assertIn('буде повтор', logs.output[0])
        tg, _ = self.run_resend()
        self.assertEqual(tg.call_count, 1)

    def test_in_app_failure_does_not_block_owner_or_resend(self):
        lead = self.exhausted()
        retry = self.exhausted()
        Lead.objects.filter(pk=retry.pk).update(
            notify_attempts=0, last_notify_attempt_at=None, created_at=timezone.now() - timedelta(hours=1))
        with mock.patch(TG, return_value=TG_OK) as tg, mock.patch(MAIL, return_value=MAIL_OK),                 mock.patch('leads.notify.alert_admins_undelivered', side_effect=RuntimeError('x')),                 mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay,                 self.assertLogs('leads.tasks', level='WARNING'):
            resend_undelivered_leads()
        self.assertEqual(tg.call_count, 1)
        delay.assert_called_once_with(retry.pk)
        self.assertIn(lead.public_id, tg.call_args.args[1])

    def test_several_leads_one_summary_alert(self):
        first, second = self.exhausted(), self.exhausted()
        tg, mail = self.run_resend()
        self.assertEqual(tg.call_count, 1)
        self.assertEqual(mail.call_count, 1)
        for lead in (first, second):
            self.assertIn(lead.public_id, tg.call_args.args[1])

    def test_second_run_does_not_alert_again(self):
        self.exhausted()
        self.run_resend()
        tg, mail = self.run_resend()
        self.assertEqual(tg.call_count + mail.call_count, 0)


@override_settings(**CHANNELS)
class UnansweredCountTests(CleanCacheTestCase):
    def counts(self):
        with mock.patch('django.utils.timezone.now', return_value=NOW):
            warn, critical = unanswered_leads()
        return len(warn), len(critical)

    def test_boundaries(self):
        lead_aged(timedelta(hours=1, minutes=59))
        self.assertEqual(self.counts(), (0, 0))
        lead_aged(timedelta(hours=2))
        self.assertEqual(self.counts(), (1, 0))
        lead_aged(timedelta(hours=23, minutes=59))
        self.assertEqual(self.counts(), (2, 0))
        lead_aged(timedelta(hours=24))
        self.assertEqual(self.counts(), (3, 1))

    def test_answered_spam_and_processed_not_counted(self):
        old = timedelta(hours=30)
        answered = lead_aged(old)
        Lead.objects.filter(pk=answered.pk).update(first_response_at=NOW)
        lead_aged(old, status=LeadStatus.SPAM)
        processed = lead_aged(old)
        Lead.objects.filter(pk=processed.pk).update(status=LeadStatus.IN_PROGRESS)
        self.assertEqual(self.counts(), (0, 0))


@override_settings(**CHANNELS)
class UnansweredAlertTests(CleanCacheTestCase):
    def run_task(self, tg=TG_OK, mail=MAIL_OK):
        with mock.patch('django.utils.timezone.now', return_value=NOW), \
                mock.patch(TG, return_value=tg) as tg_mock, mock.patch(MAIL, return_value=mail) as mail_mock:
            alert_unanswered_leads()
        return tg_mock, mail_mock

    def test_zero_sends_nothing(self):
        lead_aged(timedelta(minutes=30))
        tg, mail = self.run_task()
        self.assertEqual(tg.call_count + mail.call_count, 0)

    def test_alert_has_two_numbers_and_link_without_ids_or_pii(self):
        lead_aged(timedelta(hours=3), **MARKERS)
        lead_aged(timedelta(hours=30), **MARKERS)
        lead_aged(timedelta(hours=30), **MARKERS)
        tg, mail = self.run_task()
        self.assertEqual(tg.call_count, 1)
        self.assertEqual(mail.call_count, 1)
        text = tg.call_args.args[1]
        self.assertIn('понад 2 год: 3', text)
        self.assertIn('понад 24 год: 2', text)
        self.assertIn('https://afy.example/admin/leads/lead/', text)
        for lead in Lead.objects.all():
            self.assertNotIn(lead.public_id, text)
        for value in MARKERS.values():
            self.assertNotIn(value, text)

    def test_repeat_within_cooldown_not_sent(self):
        lead_aged(timedelta(hours=3))
        self.run_task()
        tg, mail = self.run_task()
        self.assertEqual(tg.call_count + mail.call_count, 0)

    def test_new_unanswered_lead_alerts_again(self):
        lead_aged(timedelta(hours=3))
        self.run_task()
        lead_aged(timedelta(hours=4))
        tg, _ = self.run_task()
        self.assertEqual(tg.call_count, 1)

    def test_same_counts_but_different_leads_alerts_again(self):
        first = lead_aged(timedelta(hours=3))
        self.run_task()
        Lead.objects.filter(pk=first.pk).update(first_response_at=NOW)
        lead_aged(timedelta(hours=3))
        tg, _ = self.run_task()
        self.assertEqual(tg.call_count, 1)

    def test_failed_delivery_rolls_back_key(self):
        lead_aged(timedelta(hours=3))
        self.run_task(tg=mock.Mock(ok=False), mail={'queued': False})
        tg, _ = self.run_task()
        self.assertEqual(tg.call_count, 1)

    @override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL='')
    def test_no_channels_warns_and_does_not_set_key(self):
        lead_aged(timedelta(hours=3))
        with self.assertLogs('leads.tasks', level='WARNING') as logs:
            tg, mail = self.run_task()
        self.assertEqual(tg.call_count + mail.call_count, 0)
        self.assertIn('канал алерта владельцу не настроен', logs.output[0])
        with override_settings(FAILED_TASK_ALERT_CHAT_ID='-100777'):
            tg, _ = self.run_task()
        self.assertEqual(tg.call_count, 1)

    def test_thresholds_come_from_settings(self):
        lead_aged(timedelta(hours=5))
        with override_settings(LEAD_UNANSWERED_WARN_HOURS=6):
            tg, _ = self.run_task()
        self.assertEqual(tg.call_count, 0)

    def test_beat_entry_hourly(self):
        entry = settings.CELERY_BEAT_SCHEDULE['alert-unanswered-leads']
        self.assertEqual(entry['task'], 'leads.tasks.alert_unanswered_leads')
        self.assertEqual(entry['options']['expire_seconds'], 3300)
