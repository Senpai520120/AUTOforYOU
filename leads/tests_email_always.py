"""Задача 9.56: флаг «email завжди» и письмо брокеру без ПДн. Telegram и SMTP замоканы (locmem), сети нет."""
from unittest import mock

from django.core import mail
from django.test import override_settings

from integrations.models import OutboxMessage
from leads import notify
from leads.models import Lead, LeadNotificationSettings, NotifyStatus
from leads.tasks import notify_broker_email, notify_broker_new_lead, resend_undelivered_leads
from telegram_bot.sender import SendResult

from .tests_delivery import BROKER_MAIL, EmailBase, age

SEND = 'telegram_bot.sender.send_message'
TOKEN = '123456:ABCdef'
CLIENT = dict(
    name='Зеновій Унікальний', phone='0509998877', email='zenovii.unique@client-mail.test',
    contact_method='telegram', contact_handle='@zenovii_unique_tg',
    comment='Мій секретний коментар про зарплату', vehicle_label='Toyota Camry',
)
PAGE_URL = 'https://autoforyou.ua/prigon/camry?email=zenovii.unique@client-mail.test'
REFERRER = 'https://news.example.test/private/path?token=SECRET-REF'
# Узнаваемые значения клиента: ни одно не должно попасть в письмо.
PII = ('Зеновій', 'Унікальний', '0509998877', '509998877', 'zenovii.unique', 'client-mail.test',
       'zenovii_unique_tg', 'секретний коментар', 'зарплату', 'SECRET-REF', '/private/path', 'token=')
OK = SendResult(ok=True, message_id=7)
FAIL = SendResult(ok=False, reason='TelegramBadRequest')


class AlwaysBase(EmailBase):
    def make_lead(self):
        lead = self.create_lead(**CLIENT)
        Lead.objects.filter(pk=lead.pk).update(referrer=REFERRER, page_url=PAGE_URL)
        lead.refresh_from_db()
        return lead

    def set_always(self, value):
        self.cfg.email_always = value
        self.cfg.save()

    def assertNoPii(self, text):
        for value in PII:
            self.assertNotIn(value, text)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
class FlagTests(AlwaysBase):
    def test_default_is_off(self):
        self.assertFalse(LeadNotificationSettings.get_solo().email_always)

    def test_off_telegram_sent_means_no_email(self):
        with mock.patch(SEND, return_value=OK):
            lead = self.create_via_api()
        lead.refresh_from_db()
        self.assertEqual((len(mail.outbox), lead.email_status), (0, NotifyStatus.PENDING))

    def test_on_telegram_sent_still_sends_one_email(self):
        self.set_always(True)
        with mock.patch(SEND, return_value=OK):
            lead = self.create_via_api()
        lead.refresh_from_db()
        self.assertEqual((len(mail.outbox), mail.outbox[0].to), (1, [BROKER_MAIL]))
        self.assertEqual((lead.telegram_status, lead.email_status), (NotifyStatus.SENT, NotifyStatus.SENT))

    def test_on_telegram_failed_sends_one_email_not_two(self):
        self.set_always(True)
        with mock.patch(SEND, return_value=FAIL):
            lead = self.create_via_api()
        lead.refresh_from_db()
        self.assertEqual((len(mail.outbox), lead.email_status), (1, NotifyStatus.SENT))

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_on_telegram_not_configured_sends_one_email(self):
        self.set_always(True)
        lead = self.create_via_api()
        self.assertEqual(len(mail.outbox), 1)
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SKIPPED)

    def test_on_repeated_task_run_does_not_duplicate_email(self):
        self.set_always(True)
        lead = self.make_lead()
        with mock.patch(SEND, return_value=OK):
            notify_broker_new_lead(lead.pk)
            notify_broker_new_lead(lead.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_on_email_channel_down_does_not_break_telegram_or_delivery_status(self):
        self.set_always(True)
        lead = self.make_lead()
        with mock.patch(SEND, return_value=OK), \
                mock.patch('integrations.email.send_email', side_effect=RuntimeError('smtp down')):
            notify_broker_new_lead(lead.pk)
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.email_status), (NotifyStatus.SENT, NotifyStatus.FAILED))
        # Дошёл один канал: заявка не недоставлена, досыл её не берёт, попытки не растут.
        self.assertEqual(lead.notify_attempts, 0)
        age(lead)
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            self.assertEqual(resend_undelivered_leads()['resent'], 0)
        delay.assert_not_called()

    def test_on_telegram_down_email_ok_is_delivered(self):
        self.set_always(True)
        lead = self.make_lead()
        with mock.patch(SEND, side_effect=ConnectionError('down')):
            notify_broker_new_lead(lead.pk)
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.email_status), (NotifyStatus.FAILED, NotifyStatus.SENT))
        age(lead)
        self.assertEqual(resend_undelivered_leads()['resent'], 0)

    def test_on_telegram_in_progress_does_not_queue_email(self):
        self.set_always(True)
        lead = self.make_lead()
        Lead.objects.filter(pk=lead.pk).update(telegram_status=NotifyStatus.SENDING)
        with mock.patch('leads.tasks.notify_broker_email.delay') as delay:
            notify_broker_new_lead(lead.pk)
        delay.assert_not_called()

    def test_off_force_resend_sends_email_even_if_telegram_delivered(self):
        lead = self.make_lead()
        with mock.patch(SEND, return_value=OK):
            notify_broker_new_lead(lead.pk, force=True)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_task_still_idempotent_when_always_on(self):
        self.set_always(True)
        lead = self.make_lead()
        notify_broker_email.delay(lead.pk)
        notify_broker_email.delay(lead.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_flag_is_editable_in_admin_form(self):
        from django.contrib.admin.sites import site
        fields = site._registry[LeadNotificationSettings].get_form(mock.Mock()).base_fields
        self.assertIn('email_always', fields)


@override_settings(TELEGRAM_BOT_TOKEN='')
class PiiFreeEmailTests(AlwaysBase):
    def test_default_subject_and_body_have_no_client_data(self):
        lead = self.make_lead()
        subject, body = notify.render_new_lead_email(lead, LeadNotificationSettings.get_solo())
        self.assertNoPii(subject)
        self.assertNoPii(body)
        self.assertIn(lead.public_id, subject)
        self.assertIn(lead.public_id, body)
        self.assertIn(notify.cabinet_url(lead), body)
        self.assertIn(notify.admin_url(lead), body)

    def test_sent_email_has_no_client_data(self):
        lead = self.make_lead()
        notify_broker_email.delay(lead.pk)
        message = mail.outbox[0]
        self.assertNoPii(message.subject)
        self.assertNoPii(message.body)

    def test_custom_template_cannot_bring_pii_back(self):
        self.cfg.email_subject_template = '{id} {name} {phone}'
        self.cfg.email_body_template = ('{name}|{phone}|{email}|{contact_handle}|{comment}|{referrer}|{page_url}|'
                                        '{source_details}|{utm_content}')
        lead = self.make_lead()
        subject, body = notify.render_new_lead_email(lead, self.cfg)
        self.assertNoPii(subject)
        self.assertNoPii(body)

    def test_line_breaks_in_car_cannot_add_lines_to_body(self):
        lead = self.create_lead(**{**CLIENT, 'vehicle_label': 'Camry\nТелефон: 0509998877'})
        _, body = notify.render_new_lead_email(lead, LeadNotificationSettings.get_solo())
        self.assertIn('Авто: Camry Телефон: 0509998877', body)
        self.assertEqual(body.count('Телефон:'), 1)

    def test_source_keeps_only_referrer_host(self):
        lead = self.make_lead()
        self.assertEqual(notify.email_context(lead)['source_details'], 'news.example.test')

    def test_source_prefers_utm_labels(self):
        lead = self.make_lead()
        Lead.objects.filter(pk=lead.pk).update(utm={'source': 'tg_chan', 'medium': 'partner'})
        lead.refresh_from_db()
        self.assertEqual(notify.email_context(lead)['source_details'], 'tg_chan / partner')

    def test_telegram_text_still_has_contacts(self):
        # Личный чат брокера: контакты остаются там, где их и ждут (решение 2.12 не менялось).
        lead = self.make_lead()
        text = notify.render_new_lead_text(lead, '{name} {phone}')
        self.assertIn('Унікальний', text)
        self.assertIn('0509998877', text)

    @override_settings(EMAIL_MODE='demo')
    def test_demo_outbox_has_no_client_data(self):
        lead = self.make_lead()
        notify_broker_email.delay(lead.pk)
        rows = list(OutboxMessage.objects.filter(provider='email'))
        self.assertEqual(len(rows), 1)
        self.assertNoPii(rows[0].subject)
        self.assertNoPii(rows[0].body)
        self.assertIn(lead.public_id, rows[0].subject)

    def test_logs_have_only_lead_id_and_error_class(self):
        lead = self.make_lead()
        with mock.patch('integrations.email.send_email', side_effect=RuntimeError(f'{CLIENT["phone"]} {CLIENT["name"]}')), \
                self.assertLogs('leads.tasks', level='WARNING') as logs:
            notify_broker_email.delay(lead.pk)
        output = ''.join(logs.output)
        self.assertIn(f'lead_id={lead.pk}', output)
        self.assertNoPii(output)
