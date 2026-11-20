"""10.19: запасной получатель заявок (второй chat_id)."""
from unittest import mock

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, override_settings

from leads.models import LeadNotificationSettings, NotifyStatus
from leads.tasks import notify_broker_new_lead
from telegram_bot.sender import SendResult
from tests.factories import make_staff

from .tests_notify import NotifyBase

SEND = 'telegram_bot.sender.send_message'
OK = SendResult(ok=True, message_id=7)
BAD = SendResult(ok=False, reason='TelegramForbiddenError')


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef', TELEGRAM_BROKER_CHAT_ID='')
class BackupRecipientTests(NotifyBase):
    def setUp(self):
        super().setUp()
        self.cfg.backup_telegram_chat_id = '-777'
        self.cfg.save()

    def _chats(self, send):
        return [call.args[0] for call in send.call_args_list]

    def test_primary_ok_backup_not_called(self):
        with mock.patch(SEND, return_value=OK) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-555'])
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.telegram_error), (NotifyStatus.SENT, ''))

    def test_primary_api_error_goes_to_backup(self):
        with mock.patch(SEND, side_effect=[BAD, OK]) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-555', '-777'])
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SENT)
        self.assertEqual(lead.telegram_error, 'via_backup:TelegramForbiddenError')

    def test_primary_connection_error_after_retries_goes_to_backup(self):
        def fake(chat_id, *args, **kwargs):
            if chat_id == '-555':
                raise ConnectionError('boom')
            return OK
        with mock.patch(SEND, side_effect=fake) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-555'] * 4 + ['-777'])
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.telegram_error), (NotifyStatus.SENT, 'via_backup:ConnectionError'))

    def test_both_failed(self):
        with mock.patch(SEND, return_value=BAD) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-555', '-777'])
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.FAILED)
        self.assertEqual(lead.telegram_error, 'backup_failed:TelegramForbiddenError')

    def test_no_primary_uses_backup_visibly(self):
        self.cfg.telegram_chat_id = ''
        self.cfg.save()
        with mock.patch(SEND, return_value=OK) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-777'])
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.telegram_error), (NotifyStatus.SENT, 'via_backup:no_primary'))
        self.assertEqual(LeadNotificationSettings.get_solo().telegram_chat_id, '')

    def test_same_as_primary_single_send(self):
        self.cfg.backup_telegram_chat_id = '-555'
        self.cfg.save()
        with mock.patch(SEND, return_value=BAD) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-555'])
        lead.refresh_from_db()
        self.assertEqual((lead.telegram_status, lead.telegram_error), (NotifyStatus.FAILED, 'TelegramForbiddenError'))

    def test_no_backup_behaviour_unchanged(self):
        self.cfg.backup_telegram_chat_id = ''
        self.cfg.save()
        with mock.patch(SEND, return_value=BAD) as send:
            lead = self.create_via_api()
        self.assertEqual(self._chats(send), ['-555'])
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_error, 'TelegramForbiddenError')

    def test_backup_is_not_tried_for_missing_token(self):
        with override_settings(TELEGRAM_BOT_TOKEN=''), mock.patch(SEND) as send:
            lead = self.create_via_api()
        send.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.SKIPPED)

    def test_already_sent_via_backup_not_resent(self):
        with mock.patch(SEND, side_effect=[BAD, OK]) as send:
            lead = self.create_via_api()
            notify_broker_new_lead.delay(lead.pk)
        self.assertEqual(send.call_count, 2)

    def test_logs_have_no_chat_id_or_pii(self):
        with mock.patch(SEND, side_effect=[BAD, OK]), self.assertLogs('leads.tasks', 'WARNING') as logs:
            self.create_via_api()
        text = ''.join(logs.output)
        for secret in ('-555', '-777', '0671234567', 'Іван'):
            self.assertNotIn(secret, text)

    def test_validator(self):
        for bad in ('@channel', 'abc', '12 3'):
            self.cfg.backup_telegram_chat_id = bad
            with self.assertRaisesMessage(ValidationError, 'Лише числовий chat_id'):
                self.cfg.full_clean()
        for good in ('-1001234567890', '12345', ''):
            self.cfg.backup_telegram_chat_id = good
            self.cfg.full_clean()


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef', TELEGRAM_BROKER_CHAT_ID='', CELERY_TASK_ALWAYS_EAGER=False)
class BackupWithCeleryRetryTests(NotifyBase):
    """Не eager: запасной получает сообщение только когда основной окончательно исчерпал повторы."""
    RETRY = 'leads.tasks.notify_broker_new_lead.retry'

    def setUp(self):
        super().setUp()
        self.cfg.backup_telegram_chat_id = '-777'
        self.cfg.save()

    def _run_primary_retry(self, exc):
        with mock.patch(SEND, side_effect=exc) as send,                 mock.patch(self.RETRY, side_effect=RuntimeError('retried')) as retry:
            lead = self.create_lead()
            with self.assertRaisesMessage(RuntimeError, 'retried'):
                notify_broker_new_lead(lead.pk)
        retry.assert_called_once()
        self.assertEqual([c.args[0] for c in send.call_args_list], ['-555'])
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.PENDING)

    def test_connection_error_on_primary_retries_without_backup(self):
        self._run_primary_retry(ConnectionError('boom'))

    def test_retry_after_on_primary_retries_without_backup(self):
        from aiogram.exceptions import TelegramRetryAfter
        self._run_primary_retry(TelegramRetryAfter(method=mock.Mock(), message='x', retry_after=5))

    def test_retry_after_on_backup_does_not_retry(self):
        from aiogram.exceptions import TelegramRetryAfter

        def fake(chat_id, *args, **kwargs):
            if chat_id == '-555':
                return BAD
            raise TelegramRetryAfter(method=mock.Mock(), message='x', retry_after=5)
        with mock.patch(SEND, side_effect=fake), mock.patch(self.RETRY) as retry:
            lead = self.create_lead()
            notify_broker_new_lead(lead.pk)
        retry.assert_not_called()
        lead.refresh_from_db()
        self.assertEqual(lead.telegram_status, NotifyStatus.FAILED)
        self.assertEqual(lead.telegram_error, 'backup_failed:TelegramForbiddenError')


@override_settings(TELEGRAM_BOT_TOKEN='123456:ABCdef', TELEGRAM_BROKER_CHAT_ID='', FAILED_TASK_ALERT_CHAT_ID='-900')
class BackupOwnerAlertTests(NotifyBase):
    def setUp(self):
        super().setUp()
        self.cfg.backup_telegram_chat_id = '-777'
        self.cfg.save()
        cache.delete('leads:backup_used_alert')

    def test_alert_once_without_pii(self):
        with mock.patch(SEND, side_effect=[BAD, OK, BAD, OK]),                 mock.patch('core.tasks._send_failed_task_alert', return_value=True) as alert:
            first = self.create_via_api()
            self.create_via_api()
        alert.assert_called_once()
        text = alert.call_args.args[0]
        self.assertIn(first.public_id, text)
        for secret in ('0671234567', 'Іван', '-555', '-777'):
            self.assertNotIn(secret, text)

    def test_no_alert_when_primary_ok(self):
        with mock.patch(SEND, return_value=OK),                 mock.patch('core.tasks._send_failed_task_alert', return_value=True) as alert:
            self.create_via_api()
        alert.assert_not_called()

    def test_failed_alert_does_not_block_next(self):
        with mock.patch(SEND, side_effect=[BAD, OK, BAD, OK]),                 mock.patch('core.tasks._send_failed_task_alert', return_value=False) as alert:
            self.create_via_api()
            self.create_via_api()
        self.assertEqual(alert.call_count, 2)


class SettingsAdminPermissionTests(NotifyBase):
    URL = '/admin/leads/leadnotificationsettings/1/change/'

    def test_staff_with_change_permission_still_forbidden(self):
        staff = make_staff()
        staff.user_permissions.add(Permission.objects.get(codename='change_leadnotificationsettings'),
                                   Permission.objects.get(codename='view_leadnotificationsettings'))
        client = Client()
        client.force_login(staff)
        self.assertEqual(client.post(self.URL, {'backup_telegram_chat_id': '-1'}).status_code, 403)
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.backup_telegram_chat_id, '')
