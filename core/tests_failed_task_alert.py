"""Алерт о росте упавших Celery-задач (задача 9.55, остаток): порог, окно, дедупликация, состав текста."""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.utils import timezone

from core.tasks import alert_failed_task_growth
from task_ledger.models import FailedTask
from tests.base import CleanCacheTestCase

TG = 'telegram_bot.sender.send_message'
MAIL = 'integrations.email.send_email'
CFG = dict(FAILED_TASK_ALERT_THRESHOLD=3, FAILED_TASK_ALERT_WINDOW_MINUTES=60, FAILED_TASK_ALERT_COOLDOWN_MINUTES=360,
           FAILED_TASK_ALERT_CHAT_ID='-100777', FAILED_TASK_ALERT_EMAIL='')


def fail(name='leads.tasks.notify', count=1, **kw):
    for _ in range(count):
        FailedTask.objects.create(task_name=name, **kw)


@override_settings(**CFG)
class FailedTaskAlertTests(CleanCacheTestCase):
    def run_task(self):
        with mock.patch(TG, return_value=mock.Mock(ok=True)) as tg:
            alert_failed_task_growth()
        return tg

    def test_at_threshold_sends_count_and_names(self):
        fail('leads.tasks.notify', 2)
        fail('pricing.tasks.fetch', 1)
        tg = self.run_task()
        tg.assert_called_once()
        chat_id, text = tg.call_args.args[:2]
        self.assertEqual(chat_id, '-100777')
        self.assertIn('за 60 хв: 3', text)
        self.assertIn('leads.tasks.notify: 2', text)
        self.assertIn('pricing.tasks.fetch: 1', text)

    def test_below_threshold_sends_nothing(self):
        fail(count=2)
        self.assertEqual(self.run_task().call_count, 0)

    def test_failures_outside_window_are_not_counted(self):
        fail(count=3)
        FailedTask.objects.update(failed_at=timezone.now() - timedelta(minutes=61))
        self.assertEqual(self.run_task().call_count, 0)

    def test_same_alert_is_not_repeated_within_cooldown(self):
        fail(count=3)
        self.run_task()
        self.assertEqual(self.run_task().call_count, 0)

    def test_new_set_of_failing_tasks_alerts_again(self):
        fail('leads.tasks.notify', 3)
        self.run_task()
        fail('payments.tasks.charge', 1)
        self.assertEqual(self.run_task().call_count, 1)

    def test_tenfold_growth_with_same_tasks_alerts_again(self):
        fail('leads.tasks.notify', 3)
        self.run_task()
        fail('leads.tasks.notify', 7)  # 3 -> 10: другой порядок величины
        self.assertEqual(self.run_task().call_count, 1)

    def test_more_than_ten_task_names_are_truncated_but_all_count_for_key(self):
        for i in range(12):
            fail(f'app.tasks.t{i:02d}', 1)
        tg = self.run_task()
        self.assertEqual(tg.call_args.args[1].count('• '), 10)
        self.assertEqual(self.run_task().call_count, 0)

    def test_name_with_trailing_newline_is_hidden(self):
        fail('leads.tasks.notify\n', 3)
        self.assertIn('назву приховано', self.run_task().call_args.args[1])

    def test_email_failure_does_not_leak_address_to_log(self):
        fail(count=3)
        with override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL='owner@example.test'),                 mock.patch(MAIL, side_effect=RuntimeError('rejected owner@example.test')),                 self.assertLogs('core.tasks', level='WARNING') as logs:
            alert_failed_task_growth()
        self.assertNotIn('owner@example.test', logs.output[0])

    def test_text_has_no_error_text_arguments_or_ids(self):
        fail(count=3, error='secret-error-text', args=['+380671234567'], kwargs={'email': 'a@b.c'},
             task_id='deadbeef-id', exception_class='ValueError')
        text = self.run_task().call_args.args[1]
        for leaked in ('secret-error-text', '380671234567', 'a@b.c', 'deadbeef-id', 'ValueError'):
            self.assertNotIn(leaked, text)

    def test_unsafe_task_name_is_hidden(self):
        fail('anna@example.com sent +380671234567', 3)
        text = self.run_task().call_args.args[1]
        self.assertNotIn('anna@example.com', text)
        self.assertIn('назву приховано', text)

    def test_no_channel_configured_does_not_fail_or_send(self):
        fail(count=3)
        with override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL=''), \
                mock.patch(TG) as tg, mock.patch(MAIL) as mail, \
                self.assertLogs('core.tasks', level='WARNING') as logs:
            alert_failed_task_growth()
        self.assertEqual((tg.call_count, mail.call_count), (0, 0))
        self.assertIn('канал алерта не настроен', logs.output[0])

    def test_email_channel(self):
        fail(count=3)
        with override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL='owner@example.test'), \
                mock.patch(MAIL, return_value={'queued': True}) as mail:
            alert_failed_task_growth()
        self.assertEqual(mail.call_args.args[0], 'owner@example.test')
        self.assertIn('за 60 хв: 3', mail.call_args.args[2])

    def test_email_not_queued_allows_retry(self):
        fail(count=3)
        with override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL='owner@example.test'):
            with mock.patch(MAIL, return_value={'configured': False, 'queued': False}):
                alert_failed_task_growth()
            with mock.patch(MAIL, return_value={'queued': True}) as mail:
                alert_failed_task_growth()
        self.assertEqual(mail.call_count, 1)

    def test_telegram_failure_does_not_raise_and_allows_retry(self):
        fail(count=3)
        with mock.patch(TG, side_effect=ConnectionError('boom -100777')), \
                self.assertLogs('core.tasks', level='WARNING') as logs:
            alert_failed_task_growth()
        self.assertNotIn('-100777', logs.output[0])
        self.assertEqual(self.run_task().call_count, 1)  # ключ дедупликации снят: следующий запуск шлёт снова

    def test_rejected_by_telegram_allows_retry(self):
        fail(count=3)
        with mock.patch(TG, return_value=mock.Mock(ok=False)):
            alert_failed_task_growth()
        self.assertEqual(self.run_task().call_count, 1)

    def test_cache_outage_still_alerts(self):
        fail(count=3)
        with mock.patch('core.tasks.cache.add', side_effect=RuntimeError('redis down')), \
                mock.patch('core.tasks.cache.delete'), mock.patch(TG, return_value=mock.Mock(ok=True)) as tg, \
                self.assertLogs('core.tasks', level='WARNING'):
            alert_failed_task_growth()
        self.assertEqual(tg.call_count, 1)

    def test_scheduled_every_ten_minutes_with_expiry(self):
        entry = settings.CELERY_BEAT_SCHEDULE['failed-task-alert']
        self.assertEqual(entry['task'], 'core.tasks.alert_failed_task_growth')
        self.assertEqual(entry['options']['expires'], 540)
