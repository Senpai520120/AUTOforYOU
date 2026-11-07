"""Задача 3.4b: Telegram-адаптер (режимы, demo/Outbox, счётчик пропусков, health) и кнопки LiqPay/бота."""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from integrations import registry
from integrations.checks import check_integration_modes
from integrations.models import IntegrationHealth, OutboxMessage
from integrations.tasks import send_notification
from telegram_bot.provider import (
    DemoTelegramProvider,
    DisabledTelegramProvider,
    RealTelegramProvider,
    TelegramProvider,
    get_telegram_provider,
)
from tests.base import CleanCacheTestCase
from tests.factories import make_staff, make_user

TOKEN = '123456:ABCdef'   # короткая заглушка в формате, который принимает aiogram
NO_TOKEN = {'TELEGRAM_BOT_TOKEN': ''}


class TelegramModeTests(SimpleTestCase):
    @override_settings(TELEGRAM_MODE='auto', **NO_TOKEN)
    def test_empty_token_not_configured(self):
        res = TelegramProvider().resolution()
        self.assertEqual(res.configured, False)
        self.assertIsInstance(get_telegram_provider(), DisabledTelegramProvider)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN='your_bot_token')
    def test_placeholder_token_not_configured(self):
        self.assertFalse(TelegramProvider().is_configured())
        self.assertIsInstance(get_telegram_provider(), DisabledTelegramProvider)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_auto_with_token_is_real(self):
        self.assertIsInstance(get_telegram_provider(), RealTelegramProvider)

    @override_settings(TELEGRAM_MODE='demo', **NO_TOKEN)
    def test_demo_needs_no_token(self):
        self.assertIsInstance(get_telegram_provider(), DemoTelegramProvider)

    @override_settings(TELEGRAM_MODE='off', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_off_wins_over_token(self):
        self.assertIsInstance(get_telegram_provider(), DisabledTelegramProvider)

    @override_settings(TELEGRAM_MODE='real', **NO_TOKEN)
    def test_real_without_token_is_config_error(self):
        res = TelegramProvider().resolution()
        self.assertEqual((res.mode, res.configured), ('real', False))
        self.assertIsInstance(get_telegram_provider(), DisabledTelegramProvider)

    @override_settings(TELEGRAM_MODE='bogus', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_invalid_mode_not_configured(self):
        self.assertFalse(TelegramProvider().is_configured())

    @override_settings(TELEGRAM_MODE='sandbox')
    def test_sandbox_not_allowed_for_telegram_by_check(self):
        ids = [m.id for m in check_integration_modes() if 'TELEGRAM_MODE' in m.msg]
        self.assertEqual(ids, ['integrations.E001'])

    @override_settings(LIQPAY_MODE='sandbox')
    def test_sandbox_allowed_for_liqpay_by_check(self):
        self.assertEqual([m for m in check_integration_modes() if 'LIQPAY_MODE' in m.msg], [])

    @override_settings(LIQPAY_MODE='demo')
    def test_demo_not_allowed_for_liqpay_by_check(self):
        ids = [m.id for m in check_integration_modes() if 'LIQPAY_MODE' in m.msg]
        self.assertEqual(ids, ['integrations.E001'])

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_WEBHOOK_SECRET='abcdef',
                       TELEGRAM_CHANNEL_ID='@ch', TELEGRAM_B2B_CHANNEL_ID='', TELEGRAM_BOT_USERNAME='afy_bot')
    def test_status_rows_and_webhook_mode_without_values(self):
        st = registry.build_status(next(p for p in registry.get_providers() if p.key == 'telegram'))
        rows = dict(st.env_rows)
        self.assertEqual(rows['TELEGRAM_BOT_TOKEN'], 'задано')
        self.assertEqual(rows['TELEGRAM_BOT_USERNAME'], 'задано')
        self.assertEqual(rows['TELEGRAM_CHANNEL_ID'], 'задано')
        self.assertEqual(rows['TELEGRAM_B2B_CHANNEL_ID'], 'не задано')
        self.assertEqual(rows['TELEGRAM_WEBHOOK_SECRET'], 'задано')
        self.assertTrue(any('webhook' in n for n in st.notes))
        self.assertNotIn(TOKEN, repr(st))

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_WEBHOOK_SECRET='')
    def test_status_polling_without_secret(self):
        st = TelegramProvider().status()
        self.assertTrue(any('polling' in n for n in st.notes))


class SendNotificationAdapterTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user(telegram_id=555000111)

    @override_settings(TELEGRAM_MODE='demo', **NO_TOKEN)
    def test_demo_writes_outbox_and_never_builds_bot(self):
        with mock.patch('aiogram.Bot') as bot_cls:
            result = send_notification(self.user.pk, 'Привіт, світ')
        bot_cls.assert_not_called()
        self.assertEqual(result, {'sent': True})
        row = OutboxMessage.objects.get()
        self.assertEqual((row.provider, row.recipient, row.body), ('telegram', '555000111', 'Привіт, світ'))

    @override_settings(TELEGRAM_MODE='demo', **NO_TOKEN)
    def test_demo_log_has_no_text_or_telegram_id(self):
        with self.assertLogs('', 'INFO') as logs:
            send_notification(self.user.pk, 'секретний текст')
        out = '\n'.join(logs.output)
        self.assertNotIn('секретний текст', out)
        self.assertNotIn('555000111', out)

    @override_settings(TELEGRAM_MODE='auto', **NO_TOKEN)
    def test_not_configured_explicit_result_and_counter(self):
        with mock.patch('aiogram.Bot') as bot_cls:
            first = send_notification(self.user.pk, 'a')
            send_notification(self.user.pk, 'b')
        bot_cls.assert_not_called()
        self.assertEqual(first, {'sent': False, 'reason': 'not_configured'})
        self.assertEqual(IntegrationHealth.objects.get(provider_key='telegram').skipped_count, 2)
        self.assertEqual(OutboxMessage.objects.count(), 0)
        st = {s.key: s for s in registry.get_statuses()}['telegram']
        self.assertEqual(st.skipped_count, 2)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_not_linked_user_is_not_counted_as_skip(self):
        result = send_notification(make_user().pk, 'x')
        self.assertEqual(result, {'sent': False, 'reason': 'not linked'})
        self.assertFalse(IntegrationHealth.objects.filter(provider_key='telegram').exists())

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_real_success_records_health(self):
        with mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock,
                        return_value=SimpleNamespace(message_id=9)) as send:
            result = send_notification(self.user.pk, 'Привіт', buttons=[{'text': 'Open', 'url': 'https://x.test/'}])
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs['chat_id'], 555000111)
        self.assertIsNotNone(send.await_args.kwargs['reply_markup'])
        self.assertEqual(result, {'sent': True})
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='telegram').last_success_at)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_api_error_result_and_health_without_token(self):
        exc = TelegramBadRequest(method=mock.Mock(), message=f'bad bot{TOKEN}/x')
        with mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock, side_effect=exc):
            result = send_notification(self.user.pk, 'Привіт')
        self.assertEqual(result, {'sent': False, 'reason': 'TelegramBadRequest'})
        row = IntegrationHealth.objects.get(provider_key='telegram')
        self.assertIsNotNone(row.last_error_at)
        self.assertNotIn(TOKEN, row.last_error)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_network_error_propagates_for_retry_with_class_only(self):
        exc = TelegramNetworkError(method=mock.Mock(), message=f'https://api.telegram.org/bot{TOKEN}/x')
        with mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock, side_effect=exc):
            # EAGER-режим: autoretry_for ретраит сетевую ошибку и в итоге пробрасывает её.
            with self.assertRaises(ConnectionError) as cm:
                send_notification(self.user.pk, 'Привіт')
        self.assertEqual(str(cm.exception), 'TelegramNetworkError')
        self.assertNotIn(TOKEN, IntegrationHealth.objects.get(provider_key='telegram').last_error)

    def test_autoretry_attributes_kept(self):
        from integrations.base import RETRYABLE_EXCEPTIONS
        self.assertEqual(tuple(send_notification.autoretry_for), tuple(RETRYABLE_EXCEPTIONS))
        self.assertEqual(send_notification.name, 'integrations.tasks.send_notification')


class AutopostAdapterTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        from tests.factories import make_listing, make_vehicle
        with mock.patch('telegram_bot.tasks.post_listing_to_channel.delay'):
            self.listing = make_listing(make_vehicle(), make_user())

    @override_settings(TELEGRAM_MODE='demo', TELEGRAM_CHANNEL_ID='@ch', **NO_TOKEN)
    def test_demo_autopost_goes_to_outbox(self):
        from telegram_bot.tasks import post_listing_to_channel
        with mock.patch('telegram_bot.tasks.time.sleep'), mock.patch('aiogram.Bot') as bot_cls:
            result = post_listing_to_channel(self.listing.pk)
        bot_cls.assert_not_called()
        self.assertEqual(result, {'posted': True, 'listing_id': self.listing.pk})
        row = OutboxMessage.objects.get()
        self.assertEqual((row.provider, row.recipient), ('telegram', '@ch'))

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_CHANNEL_ID='@ch', **NO_TOKEN)
    def test_not_configured_counts_skip(self):
        from telegram_bot.tasks import post_listing_to_channel
        result = post_listing_to_channel(self.listing.pk)
        self.assertEqual(result, {'posted': False, 'reason': 'not_configured'})
        self.assertEqual(IntegrationHealth.objects.get(provider_key='telegram').skipped_count, 1)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_CHANNEL_ID='@ch')
    def test_real_autopost_uses_bot_send_message(self):
        from telegram_bot.tasks import post_listing_to_channel
        with mock.patch('telegram_bot.tasks.time.sleep'), \
                mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock,
                           return_value=SimpleNamespace(message_id=3)) as send:
            result = post_listing_to_channel(self.listing.pk)
        send.assert_awaited_once()
        self.assertEqual(send.await_args.kwargs['chat_id'], '@ch')
        self.assertEqual(send.await_args.kwargs['parse_mode'], 'HTML')
        self.assertEqual(result['posted'], True)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_CHANNEL_ID='@ch')
    def test_api_error_does_not_crash(self):
        from telegram_bot.tasks import post_listing_to_channel
        exc = TelegramBadRequest(method=mock.Mock(), message='chat not found')
        with mock.patch('aiogram.Bot.send_message', new_callable=mock.AsyncMock, side_effect=exc):
            result = post_listing_to_channel(self.listing.pk)
        self.assertEqual(result, {'posted': False, 'reason': 'telegram_error'})


class WebhookNeedsRealBotTests(CleanCacheTestCase):
    @override_settings(TELEGRAM_MODE='demo', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_WEBHOOK_SECRET='right')
    def test_demo_mode_webhook_503(self):
        resp = self.client.post('/api/v1/telegram/webhook/', data='{}', content_type='application/json',
                                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='right')
        self.assertEqual(resp.status_code, 503)


class NoDirectBotSourceTests(SimpleTestCase):
    def test_bot_constructed_only_in_provider(self):
        root = Path(settings.BASE_DIR)
        offenders = []
        for path in root.rglob('*.py'):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(('.venv', '.claude', 'cars/')) or 'node_modules' in rel or '/migrations/' in rel:
                continue
            if rel.startswith('telegram_bot/provider.py') or '/tests' in f'/{rel}' or rel.startswith('tests/'):
                continue
            if 'Bot(token=' in path.read_text(encoding='utf-8', errors='ignore'):
                offenders.append(rel)
        self.assertEqual(offenders, [])


class AdapterButtonsTests(CleanCacheTestCase):
    BOT_URL = '/admin/integrations/status/check-bot/'
    LIQPAY_URL = '/admin/integrations/status/check-liqpay/'

    def setUp(self):
        super().setUp()
        self.admin = make_staff('boss@mail.test', superuser=True)
        self.client.force_login(self.admin)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_check_bot_shows_username_and_webhook_without_token(self):
        me = SimpleNamespace(username='afy_test_bot')
        info = SimpleNamespace(url='https://site.test/api/v1/telegram/webhook/')
        with mock.patch('aiogram.Bot.get_me', new_callable=mock.AsyncMock, return_value=me), \
                mock.patch('aiogram.Bot.get_webhook_info', new_callable=mock.AsyncMock, return_value=info):
            resp = self.client.post(self.BOT_URL, follow=True)
        self.assertContains(resp, '@afy_test_bot')
        self.assertContains(resp, 'https://site.test/api/v1/telegram/webhook/')
        self.assertNotContains(resp, TOKEN)
        self.assertIsNotNone(IntegrationHealth.objects.get(provider_key='telegram').last_success_at)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN)
    def test_check_bot_failure_shown_without_token(self):
        exc = TelegramNetworkError(method=mock.Mock(), message=f'https://api.telegram.org/bot{TOKEN}/getMe')
        with mock.patch('aiogram.Bot.get_me', new_callable=mock.AsyncMock, side_effect=exc):
            resp = self.client.post(self.BOT_URL, follow=True)
        self.assertContains(resp, 'Не вдалося перевірити бота')
        self.assertNotContains(resp, TOKEN)

    @override_settings(TELEGRAM_MODE='auto', **NO_TOKEN)
    def test_check_bot_not_configured(self):
        with mock.patch('aiogram.Bot.get_me', new_callable=mock.AsyncMock) as get_me:
            resp = self.client.post(self.BOT_URL, follow=True)
        get_me.assert_not_awaited()
        self.assertContains(resp, 'Не налаштовано')

    @override_settings(TELEGRAM_MODE='demo', **NO_TOKEN)
    def test_check_bot_demo_makes_no_calls(self):
        with mock.patch('aiogram.Bot.get_me', new_callable=mock.AsyncMock) as get_me:
            resp = self.client.post(self.BOT_URL, follow=True)
        get_me.assert_not_awaited()
        self.assertContains(resp, 'Демо')

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_PUBLIC_KEY='test_pub', LIQPAY_PRIVATE_KEY='test_priv')
    def test_liqpay_check_is_config_only(self):
        with mock.patch('httpx.Client.send') as http, mock.patch('urllib.request.urlopen') as urlopen:
            resp = self.client.post(self.LIQPAY_URL, follow=True)
        http.assert_not_called()
        urlopen.assert_not_called()
        self.assertContains(resp, 'LiqPay налаштовано: sandbox')
        self.assertNotContains(resp, 'test_priv')

    @override_settings(LIQPAY_MODE='auto', LIQPAY_PUBLIC_KEY='', LIQPAY_PRIVATE_KEY='')
    def test_liqpay_check_reports_not_configured(self):
        resp = self.client.post(self.LIQPAY_URL, follow=True)
        self.assertContains(resp, 'Не налаштовано')

    def test_status_page_has_buttons_and_skip_counter(self):
        IntegrationHealth.objects.create(provider_key='telegram', skipped_count=4)
        resp = self.client.get('/admin/integrations/status/')
        self.assertContains(resp, 'Перевірити бота')
        self.assertContains(resp, 'Перевірити конфігурацію')
        self.assertContains(resp, 'Пропущено (не налаштовано): 4')

    def test_non_superuser_staff_forbidden_and_anonymous_redirected(self):
        from django.contrib.auth.models import Permission
        staff = make_staff('viewer@mail.test')
        staff.user_permissions.add(Permission.objects.get(codename='view_integrationhealth'))
        self.client.force_login(staff)
        for url in (self.BOT_URL, self.LIQPAY_URL):
            self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(make_user())
        for url in (self.BOT_URL, self.LIQPAY_URL):
            resp = self.client.post(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/admin/login/', resp['Location'])


# ─── Ревью безопасности 3.4b ──────────────────────────────────────────────────

class DemoOutboxPrivacyTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        from leads.models import LeadNotificationSettings
        from leads.tests_api import set_partner
        set_partner()
        cfg = LeadNotificationSettings.get_solo()
        cfg.telegram_chat_id = '-555'
        cfg.save()

    @override_settings(TELEGRAM_MODE='demo', **NO_TOKEN)
    def test_lead_in_demo_outbox_is_marker_without_pii(self):
        from leads import services
        from leads.tasks import notify_broker_new_lead
        lead = services.create_lead(user=None, data={
            'name': 'Іван', 'phone': '0671234567', 'consent': True, 'partner_consent': True})
        notify_broker_new_lead(lead.pk)
        row = OutboxMessage.objects.get(provider='telegram')
        self.assertEqual(row.body, f'lead #{lead.pk}')
        self.assertNotIn('0671234567', row.body + row.recipient + row.subject)
        self.assertNotIn('Іван', row.body)

    @override_settings(TELEGRAM_MODE='demo', **NO_TOKEN)
    def test_notification_text_still_stored_in_demo(self):
        user = make_user(telegram_id=777000222)
        send_notification(user.pk, 'Привіт')
        self.assertEqual(OutboxMessage.objects.get().body, 'Привіт')

    def test_delete_account_removes_telegram_outbox(self):
        from integrations.models import write_outbox
        from users.services import anonymize_user
        user = make_user(telegram_id=777000333)
        write_outbox('telegram', recipient='777000333', body='x')
        write_outbox('telegram', recipient='777000444', body='y')
        anonymize_user(user)
        self.assertEqual(list(OutboxMessage.objects.values_list('recipient', flat=True)), ['777000444'])


class ProductionChecksTests(SimpleTestCase):
    @override_settings(TELEGRAM_MODE='demo', DEBUG=False)
    def test_telegram_demo_in_production_is_error(self):
        ids = [m.id for m in check_integration_modes() if 'Telegram' in m.msg]
        self.assertIn('integrations.E002', ids)

    @override_settings(TELEGRAM_MODE='demo', DEBUG=True)
    def test_telegram_demo_in_debug_allowed(self):
        self.assertNotIn('integrations.E002', [m.id for m in check_integration_modes()])

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_PUBLIC_KEY='sandbox_pub', LIQPAY_PRIVATE_KEY='sandbox_priv',
                       DEBUG=False)
    def test_liqpay_sandbox_in_production_hint_says_real(self):
        msgs = [m for m in check_integration_modes() if 'LiqPay' in m.msg and m.id == 'integrations.W002']
        self.assertEqual(len(msgs), 1)
        self.assertIn('LIQPAY_MODE=real', msgs[0].hint)


class LiqPayKeyKindTests(SimpleTestCase):
    @override_settings(LIQPAY_MODE='real', LIQPAY_PUBLIC_KEY='sandbox_i123', LIQPAY_PRIVATE_KEY='sandbox_priv')
    def test_real_with_sandbox_key_is_config_error(self):
        from payments.providers import LiqPayProvider
        res = LiqPayProvider().resolution()
        self.assertFalse(res.configured)
        self.assertIn('sandbox', res.reason)

    @override_settings(LIQPAY_MODE='auto', LIQPAY_SANDBOX=False,
                       LIQPAY_PUBLIC_KEY='sandbox_i123', LIQPAY_PRIVATE_KEY='sandbox_priv')
    def test_auto_real_with_sandbox_key_is_config_error(self):
        from payments.providers import LiqPayProvider
        self.assertFalse(LiqPayProvider().is_configured())

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_PUBLIC_KEY='i123live', LIQPAY_PRIVATE_KEY='live_priv')
    def test_sandbox_with_live_key_warns_in_status(self):
        from payments.providers import LiqPayProvider
        provider = LiqPayProvider()
        self.assertTrue(provider.is_configured())
        self.assertTrue(any('бойовий ключ' in n for n in provider.status().notes))

    @override_settings(LIQPAY_MODE='sandbox', LIQPAY_PUBLIC_KEY='sandbox_i123', LIQPAY_PRIVATE_KEY='sandbox_priv')
    def test_sandbox_with_sandbox_key_no_warning(self):
        from payments.providers import LiqPayProvider
        self.assertFalse(any('бойовий ключ' in n for n in LiqPayProvider().status().notes))


class WebhookUrlMaskingTests(CleanCacheTestCase):
    BOT_URL = '/admin/integrations/status/check-bot/'
    SECRET = 'whsecretvalue99'

    def _check(self, url):
        self.client.force_login(make_staff('boss@mail.test', superuser=True))
        info = SimpleNamespace(url=url)
        with mock.patch('aiogram.Bot.get_me', new_callable=mock.AsyncMock,
                        return_value=SimpleNamespace(username='afy_test_bot')), \
                mock.patch('aiogram.Bot.get_webhook_info', new_callable=mock.AsyncMock, return_value=info):
            return self.client.post(self.BOT_URL, follow=True)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_WEBHOOK_SECRET='whsecretvalue99')
    def test_query_string_is_stripped(self):
        resp = self._check('https://site.test/hook/?' + 'sec' + 'ret=' + self.SECRET)
        self.assertContains(resp, 'https://site.test/hook/')
        self.assertNotContains(resp, self.SECRET)

    @override_settings(TELEGRAM_MODE='auto', TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_WEBHOOK_SECRET='whsecretvalue99')
    def test_secret_in_path_is_masked(self):
        resp = self._check(f'https://site.test/hook/{self.SECRET}/')
        self.assertContains(resp, 'https://site.test/hook/')
        self.assertNotContains(resp, self.SECRET)
