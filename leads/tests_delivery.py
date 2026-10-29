"""Задача 2.12: надёжность доставки заявки брокеру (резервный email, досыл, предупреждение админам).

Telegram и SMTP замоканы (locmem), сети нет. Данные заявок - через сервис, пользователи - tests.factories.
"""
import re
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.messages import get_messages
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.utils import timezone

from leads import notify
from leads.models import Lead, LeadNotificationSettings, NotifyStatus
from leads.tasks import notify_broker_email, notify_broker_new_lead, resend_journal, resend_undelivered_leads
from notifications.models import Notification
from telegram_bot.sender import SendResult
from tests.factories import make_admin_role, make_staff

from .tests_notify import NotifyBase

SEND = 'telegram_bot.sender.send_message'
OK = SendResult(ok=True, message_id=7)
BROKER_MAIL = 'broker@afy-mail.test'
PHONE = '0671234567'
NAME = 'Іван'
TOKEN = '123456:ABCdef'


def age(lead, minutes=30):
    """Заявка «давно создана, давно пробовали»."""
    past = timezone.now() - timedelta(minutes=minutes)
    Lead.objects.filter(pk=lead.pk).update(created_at=past, last_notify_attempt_at=past)
    lead.refresh_from_db()


class EmailBase(NotifyBase):
    def setUp(self):
        super().setUp()
        self.cfg.broker_emails = BROKER_MAIL
        self.cfg.save()


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
class EmailFallbackTests(EmailBase):
    def test_telegram_sent_no_email(self):
        with mock.patch(SEND, return_value=OK):
            lead = self.create_via_api()
        self.assertEqual(len(mail.outbox), 0)
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.PENDING)

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_telegram_not_configured_sends_one_email(self):
        with mock.patch(SEND) as send:
            lead = self.create_via_api()
        send.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [BROKER_MAIL])
        self.assertIn(lead.public_id, mail.outbox[0].subject)
        self.assertIn(PHONE, mail.outbox[0].body)
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.SENT)
        self.assertIsNotNone(lead.email_sent_at)
        self.assertEqual(lead.notify_attempts, 0)

    def test_telegram_disabled_sends_email(self):
        self.cfg.telegram_enabled = False
        self.cfg.save()
        with mock.patch(SEND):
            self.create_via_api()
        self.assertEqual(len(mail.outbox), 1)

    def test_every_address_gets_the_email(self):
        self.cfg.broker_emails = f'{BROKER_MAIL}\n\n second@afy-mail.test \n'
        self.cfg.save()
        with mock.patch(SEND, return_value=SendResult(ok=False, reason='TelegramBadRequest')):
            self.create_via_api()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), [BROKER_MAIL, 'second@afy-mail.test'])

    @override_settings(BROKER_NOTIFY_EMAIL='env@afy-mail.test')
    def test_env_address_when_settings_empty(self):
        self.cfg.broker_emails = ''
        self.cfg.save()
        with mock.patch(SEND, return_value=SendResult(ok=False, reason='x')):
            self.create_via_api()
        self.assertEqual([m.to for m in mail.outbox], [['env@afy-mail.test']])

    @override_settings(BROKER_NOTIFY_EMAIL='')
    def test_no_addresses_skipped(self):
        self.cfg.broker_emails = ''
        self.cfg.save()
        with mock.patch(SEND, return_value=SendResult(ok=False, reason='x')):
            lead = self.create_via_api()
        self.assertEqual(len(mail.outbox), 0)
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.SKIPPED)

    def test_telegram_connection_error_falls_back_to_email(self):
        with mock.patch(SEND, side_effect=ConnectionError('boom')):
            lead = self.create_via_api()
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.FAILED)
        self.assertEqual(lead.email_status, NotifyStatus.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(lead.notify_attempts, 0)

    def test_smtp_failure_does_not_break_lead_creation(self):
        boom = OSError('smtp down')
        with mock.patch(SEND, side_effect=ConnectionError('x')), \
                mock.patch('django.core.mail.EmailMessage.send', side_effect=boom), \
                self.assertLogs(level='WARNING') as logs:
            lead = self.create_via_api()  # внутри проверяется 201
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.FAILED)
        self.assertEqual(lead.email_error, 'EmailDeliveryError')
        for secret in (PHONE, NAME, BROKER_MAIL):
            self.assertNotIn(secret, lead.email_error)
            self.assertNotIn(secret, ''.join(logs.output))
        self.assertEqual(lead.notify_attempts, 1)
        self.assertIsNotNone(lead.last_notify_attempt_at)

    def test_send_email_raising_is_failed_with_class_only(self):
        with mock.patch(SEND, return_value=SendResult(ok=False, reason='x')), \
                mock.patch('integrations.email.send_email', side_effect=RuntimeError(f'{PHONE} {NAME}')):
            lead = self.create_via_api()
        lead.refresh_from_db()
        self.assertEqual((lead.email_status, lead.email_error), (NotifyStatus.FAILED, 'RuntimeError'))

    def test_email_task_idempotent_and_force(self):
        lead = self.create_lead()
        self.assertEqual(notify_broker_email.delay(lead.pk).result, {'status': NotifyStatus.SENT})
        self.assertEqual(notify_broker_email.delay(lead.pk).result, {'status': 'already_sent'})
        self.assertEqual(len(mail.outbox), 1)
        notify_broker_email.delay(lead.pk, force=True)
        self.assertEqual(len(mail.outbox), 2)

    def test_email_goes_only_through_send_email_service(self):
        lead = self.create_lead()
        with mock.patch('integrations.email.send_email', return_value={'configured': True, 'queued': True}) as svc, \
                mock.patch('django.core.mail.send_mail') as direct:
            notify_broker_email.delay(lead.pk)
        svc.assert_called_once()
        direct.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.SENT)

    def test_email_not_configured_in_adapter_is_skipped(self):
        lead = self.create_lead()
        res = {'configured': False, 'queued': False, 'reason': 'x'}
        with mock.patch('integrations.email.send_email', return_value=res):
            notify_broker_email.delay(lead.pk)
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.SKIPPED)

    def test_task_arguments_contain_only_lead_id(self):
        lead = self.create_lead()
        with mock.patch('leads.tasks.notify_broker_email.delay') as delay, \
                mock.patch(SEND, return_value=SendResult(ok=False, reason='x')):
            notify_broker_new_lead(lead.pk)
        delay.assert_called_once_with(lead.pk, force=False)


class EmailRenderTests(EmailBase):
    def test_header_injection_stripped_from_subject(self):
        self.cfg.email_subject_template = '{id} {name}'
        lead = self.create_lead(name='Ivan\r\nBcc: x@y')
        subject, body = notify.render_new_lead_email(lead, self.cfg)
        self.assertNotRegex(subject, r'[\r\n]')
        self.assertIn('Ivan Bcc: x@y', subject)
        self.assertIn('Ivan\r\nBcc: x@y', body)

    def test_unicode_line_separators_stripped(self):
        lead = self.create_lead(name='A B\x0bC')
        subject, _ = notify.render_new_lead_email(lead, self.cfg)
        self.assertNotRegex(subject, '[ \x0b]')

    def test_unknown_placeholder_is_empty(self):
        self.cfg.email_subject_template = 'S{foo}'
        self.cfg.email_body_template = 'a{foo}b {id}'
        lead = self.create_lead()
        self.assertEqual(notify.render_new_lead_email(lead, self.cfg), ('S', f'ab {lead.public_id}'))

    def test_values_are_not_html_escaped(self):
        self.cfg.email_body_template = '{comment}'
        lead = self.create_lead(comment='<b>&')
        self.assertEqual(notify.render_new_lead_email(lead, self.cfg)[1], '<b>&')

    def test_empty_templates_use_fallback(self):
        self.cfg.email_subject_template = ''
        self.cfg.email_body_template = ''
        lead = self.create_lead()
        subject, body = notify.render_new_lead_email(lead, self.cfg)
        self.assertEqual(subject, f'Нова заявка {lead.public_id}')
        self.assertIn(PHONE, body)

    def test_default_templates_come_from_migration(self):
        cfg = LeadNotificationSettings.get_solo()
        self.assertIn('{phone}', cfg.email_body_template)
        self.assertIn('{id}', cfg.email_subject_template)

    def test_settings_validation(self):
        cfg = LeadNotificationSettings.get_solo()
        for field, value in (('broker_emails', 'ok@afy-mail.test\nnot-an-email'),
                             ('email_body_template', '{name.__class__}'),
                             ('email_subject_template', '{0}')):
            with self.subTest(field=field):
                setattr(cfg, field, value)
                with self.assertRaises(ValidationError) as cm:
                    cfg.full_clean()
                self.assertIn(field, cm.exception.message_dict)
                setattr(cfg, field, '')

    def test_invalid_env_address_ignored(self):
        self.cfg.broker_emails = ''
        self.cfg.save()
        with override_settings(BROKER_NOTIFY_EMAIL='bad, good@afy-mail.test ;GOOD@afy-mail.test'):
            self.assertEqual(notify.broker_emails(), ['good@afy-mail.test'])

    def test_settings_addresses_win_over_env(self):
        with override_settings(BROKER_NOTIFY_EMAIL='env@afy-mail.test'):
            self.assertEqual(notify.broker_emails(), [BROKER_MAIL])


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
class ResendTests(EmailBase):
    def failed_lead(self, minutes=30, **fields):
        lead = self.create_lead()
        Lead.objects.filter(pk=lead.pk).update(
            telegram_status=NotifyStatus.FAILED, email_status=NotifyStatus.FAILED, **fields)
        age(lead, minutes)
        return lead

    def test_resend_repeats_both_channels(self):
        lead = self.failed_lead()
        with mock.patch(SEND, side_effect=ConnectionError('x')) as send:
            result = resend_undelivered_leads()
        self.assertEqual(result, {'resent': 1, 'alerted': 0})
        self.assertEqual(send.call_count, 4)
        self.assertEqual(len(mail.outbox), 1)
        lead.refresh_from_db()
        self.assertEqual(lead.email_status, NotifyStatus.SENT)

    def test_resend_telegram_ok_means_no_email(self):
        lead = self.failed_lead()
        with mock.patch(SEND, return_value=OK):
            resend_undelivered_leads()
        self.assertEqual(len(mail.outbox), 0)
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SENT)

    def test_delivered_leads_are_not_resent(self):
        by_email = self.failed_lead()
        Lead.objects.filter(pk=by_email.pk).update(email_status=NotifyStatus.SENT)
        by_tg = self.failed_lead()
        Lead.objects.filter(pk=by_tg.pk).update(telegram_status=NotifyStatus.SENT)
        with mock.patch(SEND) as send:
            result = resend_undelivered_leads()
        self.assertEqual(result['resent'], 0)
        send.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    def test_fresh_attempt_is_not_touched(self):
        self.failed_lead(minutes=2)
        with mock.patch(SEND) as send:
            result = resend_undelivered_leads()
        self.assertEqual(result['resent'], 0)
        send.assert_not_called()

    def test_never_attempted_lead_uses_created_at(self):
        lead = self.failed_lead()
        Lead.objects.filter(pk=lead.pk).update(last_notify_attempt_at=None)
        with mock.patch(SEND, return_value=OK):
            self.assertEqual(resend_undelivered_leads()['resent'], 1)

    def test_two_runs_do_not_duplicate(self):
        self.failed_lead()
        with mock.patch(SEND, side_effect=ConnectionError('x')) as send:
            resend_undelivered_leads()
            resend_undelivered_leads()
        self.assertEqual(send.call_count, 4)
        self.assertEqual(len(mail.outbox), 1)

    def test_claimed_leads_are_not_taken_by_second_worker(self):
        self.failed_lead()
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            first = resend_undelivered_leads()
            second = resend_undelivered_leads()
        self.assertEqual((first['resent'], second['resent']), (1, 0))
        delay.assert_called_once()

    def test_failed_round_counts_attempt(self):
        lead = self.failed_lead(notify_attempts=1)
        with mock.patch(SEND, side_effect=ConnectionError('x')), \
                mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError('x')):
            resend_undelivered_leads()
        lead.refresh_from_db()
        self.assertEqual(lead.notify_attempts, 2)

    @override_settings(LEAD_NOTIFY_MAX_ATTEMPTS=2)
    def test_exhausted_attempts_alert_admins_once(self):
        lead = self.failed_lead(notify_attempts=2)
        admin = make_admin_role()
        superuser = make_staff(superuser=True)
        other = make_staff()  # staff без роли admin
        with mock.patch(SEND) as send, self.assertLogs('leads.tasks', 'WARNING') as logs:
            first = resend_undelivered_leads()
            second = resend_undelivered_leads()
        send.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual((first['alerted'], second['alerted']), (1, 0))
        notes = Notification.objects.filter(type='lead_undelivered')
        self.assertEqual(sorted(notes.values_list('user_id', flat=True)), sorted([admin.pk, superuser.pk]))
        self.assertFalse(notes.filter(user=other).exists())
        note = notes.get(user=superuser)
        self.assertIn(lead.public_id, note.title)
        self.assertIn(f'/admin/leads/lead/{lead.pk}/change/', note.link)
        self.assertNotIn(PHONE, note.title + note.text + note.link)
        self.assertEqual(sum(f'lead_id={lead.pk}' in line for line in logs.output), 1)
        self.assertNotIn(PHONE, ''.join(logs.output))
        lead.refresh_from_db()
        self.assertIsNotNone(lead.undelivered_alerted_at)

    @override_settings(LEAD_NOTIFY_MAX_ATTEMPTS=2)
    def test_below_limit_no_alert(self):
        self.failed_lead(notify_attempts=1)
        make_staff(superuser=True)
        with mock.patch(SEND, return_value=OK):
            self.assertEqual(resend_undelivered_leads()['alerted'], 0)
        self.assertEqual(Notification.objects.filter(type='lead_undelivered').count(), 0)

    @override_settings(TELEGRAM_BOT_TOKEN='', BROKER_NOTIFY_EMAIL='')
    def test_nothing_configured_does_not_loop(self):
        self.cfg.broker_emails = ''
        self.cfg.save()
        lead = self.create_lead()
        notify_broker_new_lead.delay(lead.pk)
        age(lead)
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.email_status), (NotifyStatus.SKIPPED,) * 2)
        self.assertEqual(lead.notify_attempts, 0)
        make_staff(superuser=True)
        with mock.patch(SEND) as send:
            result = resend_undelivered_leads()
        self.assertEqual(result, {'resent': 0, 'alerted': 0})
        send.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual(lead.notify_attempts, 0)

    def test_locks_rows_with_skip_locked(self):
        self.failed_lead()
        with mock.patch('django.db.models.query.QuerySet.select_for_update',
                        autospec=True, side_effect=lambda qs, **kw: qs) as locker:
            with mock.patch(SEND, return_value=OK):
                resend_undelivered_leads()
        self.assertEqual(locker.call_args.kwargs, {'skip_locked': True})

    def test_beat_schedule_registered(self):
        entry = settings.CELERY_BEAT_SCHEDULE['resend-undelivered-leads']
        self.assertEqual(entry['task'], 'leads.tasks.resend_undelivered_leads')
        self.assertEqual(entry['schedule'], settings.LEAD_NOTIFY_RETRY_MINUTES * 60)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, LEAD_JOURNAL_CHAT_ID='-900')
class JournalIndependenceTests(EmailBase):
    """Журнал в группу и личное уведомление - разные каналы с отдельным повтором."""

    @staticmethod
    def chat_router(fail_chat=None, calls=None):
        def fake(chat_id, text, **kwargs):
            calls.append((chat_id, text))
            if chat_id == fail_chat:
                raise ConnectionError('boom')
            return SendResult(ok=True, message_id=11)
        return fake

    def calls_to(self, calls, chat):
        return [text for chat_id, text in calls if chat_id == chat]

    def test_journal_failure_resends_only_journal(self):
        calls = []
        with mock.patch(SEND, side_effect=self.chat_router('-900', calls)):
            lead = self.create_via_api()
            lead.refresh_from_db()
            self.assertEqual(lead.telegram_status, NotifyStatus.SENT)
            self.assertIsNone(lead.journal_message_id)
            personal_before = len(self.calls_to(calls, '-555'))
            age(lead)
            calls.clear()
        with mock.patch(SEND, side_effect=self.chat_router(None, calls)):
            resend_journal()
            resend_undelivered_leads()
        self.assertEqual(len(self.calls_to(calls, '-900')), 1)
        self.assertEqual(self.calls_to(calls, '-555'), [])
        self.assertEqual(personal_before, 1)
        journal_text = self.calls_to(calls, '-900')[0]
        self.assertNotIn(NAME, journal_text)
        self.assertNotIn(PHONE, journal_text)
        lead.refresh_from_db()
        self.assertEqual(lead.journal_message_id, 11)

    def test_personal_failure_resends_only_personal(self):
        calls = []
        with mock.patch(SEND, side_effect=self.chat_router('-555', calls)):
            lead = self.create_via_api()
        lead.refresh_from_db()
        self.assertEqual(lead.journal_message_id, 11)
        Lead.objects.filter(pk=lead.pk).update(email_status=NotifyStatus.FAILED)
        age(lead)
        calls.clear()
        with mock.patch(SEND, side_effect=self.chat_router(None, calls)):
            resend_undelivered_leads()
            resend_journal()
        self.assertEqual(self.calls_to(calls, '-900'), [])
        self.assertEqual(len(self.calls_to(calls, '-555')), 1)
        self.assertIn(PHONE, self.calls_to(calls, '-555')[0])

    def test_after_success_nothing_is_sent(self):
        calls = []
        with mock.patch(SEND, side_effect=self.chat_router(None, calls)):
            lead = self.create_via_api()
            age(lead)
            calls.clear()
            resend_journal()
            resend_undelivered_leads()
        self.assertEqual(calls, [])
        self.assertEqual(len(mail.outbox), 0)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
class AdminTests(EmailBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(make_staff(superuser=True))

    def test_changelist_shows_number_and_both_statuses(self):
        lead = self.create_lead()
        Lead.objects.filter(pk=lead.pk).update(telegram_status=NotifyStatus.SENT, email_status=NotifyStatus.FAILED)
        resp = self.client.get('/admin/leads/lead/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn(lead.public_id, html)
        self.assertIn('column-telegram_status', html)
        self.assertIn('column-email_status', html)
        row = re.search(rf'<tr[^>]*>(?:(?!</tr>).)*{lead.public_id}.*?</tr>', html, re.S).group(0)
        self.assertIn('Надіслано', row)
        self.assertIn('Помилка', row)

    def banner(self, resp):
        return [str(m) for m in get_messages(resp.wsgi_request)]

    @override_settings(TELEGRAM_BOT_TOKEN='', BROKER_NOTIFY_EMAIL='')
    def test_banner_when_no_channel(self):
        self.cfg.broker_emails = ''
        self.cfg.save()
        resp = self.client.get('/admin/leads/lead/')
        self.assertIn('Жоден канал сповіщення брокера не налаштовано', self.banner(resp))

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_no_banner_when_email_configured(self):
        resp = self.client.get('/admin/leads/lead/')
        self.assertNotIn('Жоден канал сповіщення брокера не налаштовано', self.banner(resp))

    def test_no_banner_when_telegram_configured(self):
        self.cfg.broker_emails = ''
        self.cfg.save()
        resp = self.client.get('/admin/leads/lead/')
        self.assertNotIn('Жоден канал сповіщення брокера не налаштовано', self.banner(resp))

    def test_resend_action_repeats_both_channels(self):
        lead = self.create_lead()
        Lead.objects.filter(pk=lead.pk).update(telegram_status=NotifyStatus.SENT, email_status=NotifyStatus.SENT)
        with mock.patch(SEND, return_value=OK) as send:
            resp = self.client.post(
                '/admin/leads/lead/', {'action': 'resend_to_broker', '_selected_action': [lead.pk]})
        self.assertEqual(resp.status_code, 302)
        send.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)

    def test_settings_form_shows_email_fields(self):
        resp = self.client.get('/admin/leads/leadnotificationsettings/1/change/')
        self.assertEqual(resp.status_code, 200)
        for name in ('broker_emails', 'email_subject_template', 'email_body_template'):
            self.assertContains(resp, f'name="{name}"')


class SourceHygieneTests(EmailBase):
    def test_no_direct_send_mail_or_new_bot_in_leads(self):
        offenders = []
        for path in Path(settings.BASE_DIR, 'leads').glob('*.py'):
            if path.name.startswith('tests'):
                continue
            text = path.read_text(encoding='utf-8')
            if 'send_mail(' in text or 'aiogram.Bot(' in text or re.search(r'\bBot\(', text):
                offenders.append(path.name)
        self.assertEqual(offenders, [])


@override_settings(TELEGRAM_BOT_TOKEN='', EMAIL_MODE='demo')
class SubjectPrivacyTests(EmailBase):
    def test_default_subject_has_no_client_name_in_demo_log(self):
        with self.assertLogs('integrations.email', 'INFO') as logs:
            lead = self.create_via_api()
        output = ''.join(logs.output)
        self.assertIn(lead.public_id, output)
        self.assertNotIn(NAME, output)
        self.assertNotIn(PHONE, output)
        self.assertEqual(LeadNotificationSettings.get_solo().email_subject_template, 'Нова заявка {id}')


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, LEAD_NOTIFY_MAX_ATTEMPTS=2)
class StuckSendingTests(EmailBase):
    def stuck_lead(self):
        lead = self.create_lead()
        Lead.objects.filter(pk=lead.pk).update(
            telegram_status=NotifyStatus.SENDING, email_status=NotifyStatus.SENDING)
        age(lead)
        return lead

    def test_stuck_sending_counts_attempts_then_alerts_admins(self):
        lead = self.stuck_lead()
        make_staff(superuser=True)
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            first = resend_undelivered_leads()
            lead.refresh_from_db()
            self.assertEqual((lead.notify_attempts, lead.telegram_status, lead.email_status),
                             (1, NotifyStatus.PENDING, NotifyStatus.PENDING))
            Lead.objects.filter(pk=lead.pk).update(telegram_status=NotifyStatus.SENDING)  # снова завис
            age(lead)
            second = resend_undelivered_leads()
            Lead.objects.filter(pk=lead.pk).update(email_status=NotifyStatus.SENDING)
            age(lead)
            third = resend_undelivered_leads()
        self.assertEqual((first['resent'], second['resent'], third['resent']), (1, 1, 0))
        self.assertEqual((first['alerted'], second['alerted'], third['alerted']), (0, 1, 0))
        self.assertEqual(delay.call_count, 2)
        self.assertEqual(Notification.objects.filter(type='lead_undelivered').count(), 1)

    def test_recent_sending_is_not_touched(self):
        lead = self.stuck_lead()
        Lead.objects.filter(pk=lead.pk).update(last_notify_attempt_at=timezone.now())
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            self.assertEqual(resend_undelivered_leads()['resent'], 0)
        delay.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual((lead.notify_attempts, lead.telegram_status), (0, NotifyStatus.SENDING))

    def test_released_stuck_lead_is_delivered_by_resend(self):
        lead = self.stuck_lead()
        with mock.patch(SEND, return_value=OK):
            resend_undelivered_leads()
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SENT)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
class PartialAndLimitTests(EmailBase):
    def test_partial_delivery_recorded(self):
        self.cfg.broker_emails = f'{BROKER_MAIL}\nsecond@afy-mail.test'
        self.cfg.save()
        lead = self.create_lead()
        results = [{'configured': True, 'queued': True},
                   {'configured': True, 'queued': False, 'error': 'EmailDeliveryError'}]
        with mock.patch('integrations.email.send_email', side_effect=results):
            notify_broker_email.delay(lead.pk)
        lead.refresh_from_db()
        self.assertEqual((lead.email_status, lead.email_error), (NotifyStatus.SENT, 'partial:EmailDeliveryError'))

    def test_full_success_has_empty_error(self):
        lead = self.create_lead()
        notify_broker_email.delay(lead.pk)
        lead.refresh_from_db()
        self.assertEqual((lead.email_status, lead.email_error), (NotifyStatus.SENT, ''))

    def test_resend_action_limit(self):
        from leads.admin import RESEND_ACTION_LIMIT
        ids = [self.create_lead().pk for _ in range(RESEND_ACTION_LIMIT + 1)]
        client = Client()
        client.force_login(make_staff(superuser=True))
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            resp = client.post('/admin/leads/lead/', {'action': 'resend_to_broker', '_selected_action': ids}, follow=True)
            self.assertEqual(delay.call_count, 0)
            self.assertIn(str(RESEND_ACTION_LIMIT), ''.join(str(m) for m in resp.context['messages']))
            client.post('/admin/leads/lead/', {'action': 'resend_to_broker', '_selected_action': ids[:RESEND_ACTION_LIMIT]})
        self.assertEqual(delay.call_count, RESEND_ACTION_LIMIT)
