from unittest import mock

from django.contrib.admin.sites import site as admin_site
from django.test import Client, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from leads import services
from leads.models import Lead, LeadNotificationSettings, NotifyStatus
from leads.tasks import notify_broker_new_lead
from notifications.models import Notification
from telegram_bot.sender import SendResult
from tests.base import CleanCacheTestCase
from tests.factories import make_broker, make_staff, make_user

from .tests_api import URL, body, make_calc, set_partner

SEND = 'telegram_bot.sender.send_message'
OK = SendResult(ok=True, message_id=7)


class NotifyBase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        set_partner()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'lead': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cfg = LeadNotificationSettings.get_solo()
        self.cfg.telegram_chat_id = '-555'
        self.cfg.save()
        self.client = APIClient()

    def create_via_api(self, **kw):
        with self.captureOnCommitCallbacks(execute=True):
            kw.setdefault('source', 'landing')
            resp = self.client.post(URL, body(**kw), format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        return Lead.objects.latest('pk')

    def create_lead(self, **kw):
        data = {'name': 'Іван', 'phone': '0671234567', 'consent': True, 'partner_consent': True}
        data.update(kw)
        return services.create_lead(user=None, data=data)


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef')
class DeliveryTests(NotifyBase):
    @override_settings(SITE_URL='https://autoforyou.ua')
    def test_sent_with_admin_chat_id(self):
        with mock.patch(SEND, return_value=OK) as send:
            lead = self.create_via_api(calculation_id=make_calc().pk)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], '-555')
        self.assertEqual(send.call_args.kwargs['buttons'][0]['text'], 'Відкрити заявку')
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SENT)
        self.assertIsNotNone(lead.telegram_sent_at)
        self.assertIn(lead.public_id, send.call_args.args[1])
        self.assertIn('Toyota', send.call_args.args[1])

    @override_settings(TELEGRAM_BROKER_CHAT_ID='-100123')
    def test_env_chat_id_fallback(self):
        self.cfg.telegram_chat_id = ''
        self.cfg.save()
        with mock.patch(SEND, return_value=OK) as send:
            self.create_via_api()
        self.assertEqual(send.call_args.args[0], '-100123')

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_no_token_skipped(self):
        with mock.patch(SEND) as send, self.assertLogs('leads.tasks', 'WARNING') as logs:
            lead = self.create_via_api()
        send.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SKIPPED)
        self.assertNotIn('0671234567', ''.join(logs.output))
        self.assertNotIn('Іван', ''.join(logs.output))

    def test_disabled_skipped(self):
        self.cfg.telegram_enabled = False
        self.cfg.save()
        with mock.patch(SEND) as send:
            lead = self.create_via_api()
        send.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SKIPPED)

    def test_rollback_does_not_enqueue(self):
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            self.create_lead()
        delay.assert_not_called()

    def test_connection_error_retries_then_failed(self):
        with mock.patch(SEND, side_effect=ConnectionError('boom')) as send:
            lead = self.create_via_api()
        self.assertEqual(send.call_count, 4)
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.FAILED)
        self.assertEqual(lead.telegram_error, 'ConnectionError')

    def test_api_error_failed_without_retry(self):
        with mock.patch(SEND, return_value=SendResult(ok=False, reason='TelegramBadRequest')) as send:
            lead = self.create_via_api()
        self.assertEqual(send.call_count, 1)
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.telegram_error), ('failed', 'TelegramBadRequest'))

    def test_idempotent_and_force(self):
        with mock.patch(SEND, return_value=OK) as send:
            lead = self.create_via_api()
            notify_broker_new_lead.delay(lead.pk)
            self.assertEqual(send.call_count, 1)
            notify_broker_new_lead.delay(lead.pk, force=True)
            self.assertEqual(send.call_count, 2)

    def test_real_sender_is_awaited(self):
        # Мутация: без реального вызова bot.send_message тест красный.
        with mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock) as bot_send:
            bot_send.return_value = mock.Mock(message_id=11)
            lead = self.create_via_api()
        bot_send.assert_awaited_once()
        self.assertEqual(bot_send.await_args.kwargs['chat_id'], '-555')
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SENT)


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef')
class TextTests(NotifyBase):
    def sent_text(self, **kw):
        with mock.patch(SEND, return_value=OK) as send:
            lead = self.create_via_api(**kw)
        return lead, send.call_args.args[1]

    def test_escape_and_markup_kept(self):
        _, text = self.sent_text(name='<b>x</b>&<script>')
        self.assertIn('&lt;b&gt;x&lt;/b&gt;&amp;&lt;script&gt;', text)
        self.assertIn('<b>Нова заявка', text)
        self.assertNotIn('<script>', text)

    def test_unknown_placeholder_empty(self):
        self.cfg.new_lead_template = 'A{foo}B {name}'
        self.cfg.save()
        _, text = self.sent_text()
        self.assertTrue(text.startswith('AB '))

    def test_direct_source(self):
        _, text = self.sent_text()
        self.assertIn('Джерело: пряме', text)

    def test_utm_source_details_and_placeholders(self):
        self.cfg.new_lead_template = '{source_details}|{utm_source}|{utm_content}|{referrer}|{page_url}'
        self.cfg.save()
        _, text = self.sent_text(
            utm={'source': 'tiktok', 'medium': 'cpc', 'campaign': 'spring'},
            referrer='https://t.co/x?a=1&b=2', page_url='https://autoforyou.ua/calc')
        self.assertTrue(text.startswith('tiktok / cpc / spring|tiktok||'))
        self.assertIn('https://t.co', text)

    def test_hostile_attribution_escaped_no_links(self):
        lead = self.create_lead(utm={'source': 'x', 'campaign': '<script>a&b'}, referrer='https://e.com/<a href=1>')
        Lead.objects.filter(pk=lead.pk).update(
            utm={'source': 'x', 'campaign': '<script>a&b'}, referrer='https://e.com/<a href=1>')
        self.cfg.new_lead_template = '{utm_campaign} {referrer}'
        self.cfg.save()
        with mock.patch(SEND, return_value=OK) as send:
            notify_broker_new_lead.delay(lead.pk)
        text = send.call_args.args[1]
        self.assertNotIn('<a', text)
        self.assertNotIn('<script', text)
        self.assertIn('&lt;script&gt;a&amp;b', text)

    def test_length_limit_truncates_before_escape(self):
        lead = self.create_lead(comment='&' * 1000)
        Lead.objects.filter(pk=lead.pk).update(referrer='&' * 500, utm={'source': '&' * 300, 'campaign': '&' * 300})
        self.cfg.new_lead_template = '<b>{name}</b>\n' + '{comment}{referrer}{source_details}' * 3 + '\n<i>{id}</i>'
        self.cfg.save()
        with mock.patch(SEND, return_value=OK) as send:
            notify_broker_new_lead.delay(lead.pk)
        text = send.call_args.args[1]
        self.assertLessEqual(len(text), 4096)
        self.assertEqual(text.count('<b>'), text.count('</b>'))
        self.assertTrue(text.endswith('</i>'))

    def test_template_too_long_fails(self):
        self.cfg.new_lead_template = 'x' * 5000
        self.cfg.save()
        with mock.patch(SEND) as send:
            lead = self.create_via_api()
        send.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.telegram_error), ('failed', 'message_too_long'))


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef')
class InAppTests(NotifyBase):
    def test_brokers_notified_once(self):
        broker = make_broker()
        buyer = make_user()
        with mock.patch(SEND, return_value=OK):
            lead = self.create_via_api()
            notify_broker_new_lead.delay(lead.pk, force=True)
        n = Notification.objects.get(user=broker)
        self.assertEqual(n.type, 'new_lead')
        self.assertIn(f'/admin/leads/lead/{lead.pk}/change/', n.link)
        self.assertFalse(Notification.objects.filter(user=buyer).exists())
        self.assertEqual(Notification.objects.filter(type='new_lead').count(), 1)

    def test_disabled_in_app(self):
        self.cfg.notify_brokers_in_app = False
        self.cfg.save()
        make_broker()
        with mock.patch(SEND, return_value=OK):
            self.create_via_api()
        self.assertFalse(Notification.objects.exists())

    @override_settings(TELEGRAM_BOT_TOKEN='')
    def test_in_app_independent_of_telegram(self):
        make_broker()
        self.create_via_api()
        self.assertEqual(Notification.objects.filter(type='new_lead').count(), 1)


@override_settings(TELEGRAM_BOT_TOKEN='')
class AdminTests(NotifyBase):
    def admin_client(self):
        c = Client()
        c.force_login(make_staff(superuser=True))
        return c

    def test_changelist_shows_status_and_warning(self):
        lead = self.create_lead()
        resp = self.admin_client().get('/admin/leads/lead/', follow=True)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn(lead.public_id, html)
        self.assertIn('Очікує', html)
        self.assertIn('Telegram для заявок не налаштовано', html)

    def test_resend_action_uses_force(self):
        lead = self.create_lead()
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            self.admin_client().post(
                '/admin/leads/lead/', {'action': 'resend_to_broker', '_selected_action': [lead.pk]})
        delay.assert_called_once_with(lead.pk, force=True)

    def test_settings_singleton(self):
        model_admin = admin_site._registry[LeadNotificationSettings]
        request = mock.Mock()
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))


SETTINGS_URL = '/admin/leads/leadnotificationsettings/1/change/'


class AdminPermissionTests(NotifyBase):
    def client_for(self, user):
        c = Client()
        c.force_login(user)
        return c

    def test_settings_forbidden_for_non_superusers(self):
        from tests.factories import make_admin_role, make_moderator
        from users.services import assign_role
        admin_role = make_admin_role()
        assign_role(admin_role, 'admin')
        for user in (make_broker(), make_moderator(), admin_role):
            resp = self.client_for(user).get(SETTINGS_URL)
            self.assertEqual(resp.status_code, 403, user.role)
        self.assertEqual(self.client_for(make_staff(superuser=True)).get(SETTINGS_URL).status_code, 200)

    def test_resend_requires_change_permission(self):
        from django.contrib.auth.models import Permission
        lead = self.create_lead()
        broker = make_broker()
        broker.groups.clear()
        broker.user_permissions.add(Permission.objects.get(codename='view_lead'))
        with mock.patch('leads.tasks.notify_broker_new_lead.delay') as delay:
            self.client_for(broker).post(
                '/admin/leads/lead/', {'action': 'resend_to_broker', '_selected_action': [lead.pk]})
        delay.assert_not_called()


class SenderTests(NotifyBase):
    TOKEN = '123456:SECRETtoken'

    def run_send(self, exc):
        from telegram_bot import sender
        with override_settings(TELEGRAM_BOT_TOKEN=self.TOKEN), \
                mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock, side_effect=exc):
            return sender.send_message('-1', 'text')

    def test_network_error_becomes_connection_error_with_class_only(self):
        from aiogram.exceptions import TelegramNetworkError
        exc = TelegramNetworkError(method=mock.Mock(), message='https://api.telegram.org/bot123456:SECRETtoken/x')
        with self.assertRaises(ConnectionError) as cm:
            self.run_send(exc)
        self.assertEqual(str(cm.exception), 'TelegramNetworkError')
        self.assertNotIn('SECRET', repr(cm.exception.__cause__))

    def test_api_error_returns_result_and_logs_class_only(self):
        from aiogram.exceptions import TelegramBadRequest
        exc = TelegramBadRequest(method=mock.Mock(), message='bad Іван 0671234567 SECRETtoken')
        with self.assertLogs('telegram_bot.sender', 'WARNING') as logs:
            result = self.run_send(exc)
        self.assertEqual((result.ok, result.reason), (False, 'TelegramBadRequest'))
        out = ''.join(logs.output)
        for secret in ('SECRET', 'Іван', '0671234567'):
            self.assertNotIn(secret, out)

    def test_retry_after_retries_task_without_exc_text(self):
        from aiogram.exceptions import TelegramRetryAfter
        exc = TelegramRetryAfter(method=mock.Mock(), message='Іван 0671234567', retry_after=5)
        with override_settings(TELEGRAM_BOT_TOKEN=self.TOKEN), \
                mock.patch(SEND, side_effect=exc), \
                mock.patch('leads.tasks.notify_broker_new_lead.retry', side_effect=RuntimeError('retried')) as retry:
            lead = self.create_lead()
            with self.assertRaises(RuntimeError):
                notify_broker_new_lead(lead.pk)
        self.assertNotIn('exc', retry.call_args.kwargs)
        self.assertEqual(retry.call_args.kwargs['countdown'], 6)
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.PENDING)


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef')
class HardeningTests(NotifyBase):
    def test_chat_id_validator(self):
        from django.core.exceptions import ValidationError
        for bad in ('@channel', 'abc', '-100x', '12 3'):
            self.cfg.telegram_chat_id = bad
            with self.assertRaises(ValidationError, msg=bad):
                self.cfg.full_clean()
        for good in ('-1001234567890', '12345', ''):
            self.cfg.telegram_chat_id = good
            self.cfg.full_clean()

    def test_template_validator(self):
        from django.core.exceptions import ValidationError
        for bad in ('{name.__class__}', '{comment[0]}', '{name!r}', '{name:>10}', '{0}', '{'):
            self.cfg.new_lead_template = bad
            with self.assertRaises(ValidationError, msg=bad):
                self.cfg.full_clean()
        self.cfg.new_lead_template = '<b>{name}</b> {foo}'
        self.cfg.full_clean()

    def test_double_run_sends_once(self):
        lead = self.create_lead()
        Lead.objects.filter(pk=lead.pk).update(telegram_status=NotifyStatus.SENDING)
        with mock.patch(SEND) as send:
            notify_broker_new_lead(lead.pk, force=True)
        send.assert_not_called()

    def test_claim_marks_sending_during_send(self):
        lead = self.create_lead()
        seen = []

        def fake(*a, **kw):
            seen.append(Lead.objects.get(pk=lead.pk).telegram_status)
            return OK
        with mock.patch(SEND, side_effect=fake):
            notify_broker_new_lead(lead.pk)
        self.assertEqual(seen, ['sending'])
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SENT)

    def test_limit_counts_utf16(self):
        from leads.notify import tg_len
        lead = self.create_lead(comment='😀' * 900)
        self.cfg.new_lead_template = '{comment}{comment}{comment}'
        self.cfg.save()
        with mock.patch(SEND, return_value=OK) as send:
            notify_broker_new_lead(lead.pk)
        text = send.call_args.args[1]
        self.assertLessEqual(tg_len(text), 4096)
        self.assertGreater(len(text), 0)

    @override_settings(SITE_URL='http://localhost:8000')
    def test_no_button_on_http(self):
        lead = self.create_lead()
        with mock.patch(SEND, return_value=OK) as send:
            notify_broker_new_lead(lead.pk)
        self.assertIsNone(send.call_args.kwargs['buttons'])

    @override_settings(SITE_URL='https://autoforyou.ua')
    def test_button_on_https(self):
        lead = self.create_lead()
        with mock.patch(SEND, return_value=OK) as send:
            notify_broker_new_lead(lead.pk)
        self.assertTrue(send.call_args.kwargs['buttons'][0]['url'].startswith('https://'))
