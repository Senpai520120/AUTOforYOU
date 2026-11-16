"""Алерт о заполнении диска (10.20): порог, дедупликация, пустые каналы, состав текста."""
from collections import namedtuple
from unittest import mock

from django.test import override_settings

from core.tasks import alert_disk_usage
from tests.base import CleanCacheTestCase

TG = 'telegram_bot.sender.send_message'
DISK = 'core.tasks.shutil.disk_usage'
Usage = namedtuple('Usage', 'total used free')
GB = 1024 ** 3
CFG = dict(DISK_ALERT_PATH='/', DISK_ALERT_THRESHOLD_PERCENT=85, DISK_ALERT_COOLDOWN_MINUTES=360,
           FAILED_TASK_ALERT_CHAT_ID='-100777', FAILED_TASK_ALERT_EMAIL='')


def usage(used_percent):
    return Usage(100 * GB, used_percent * GB, (100 - used_percent) * GB)


@override_settings(**CFG)
class DiskAlertTests(CleanCacheTestCase):
    def run_task(self, used_percent):
        with mock.patch(DISK, return_value=usage(used_percent)), \
                mock.patch(TG, return_value=mock.Mock(ok=True)) as tg:
            alert_disk_usage()
        return tg

    def test_below_threshold_sends_nothing(self):
        self.assertEqual(self.run_task(84).call_count, 0)

    def test_at_threshold_sends_percent_and_free_gb_only(self):
        tg = self.run_task(90)
        tg.assert_called_once()
        chat_id, text = tg.call_args.args[:2]
        self.assertEqual(chat_id, '-100777')
        self.assertIn('90%', text)
        self.assertIn('10.0 ГБ', text)

    def test_exactly_threshold_sends(self):
        self.assertEqual(self.run_task(85).call_count, 1)

    def test_repeat_within_cooldown_not_sent(self):
        self.assertEqual(self.run_task(90).call_count, 1)
        self.assertEqual(self.run_task(95).call_count, 0)

    def test_failed_delivery_does_not_block_retry(self):
        with mock.patch(DISK, return_value=usage(90)), mock.patch(TG, return_value=mock.Mock(ok=False)):
            alert_disk_usage()
        self.assertEqual(self.run_task(90).call_count, 1)

    @override_settings(FAILED_TASK_ALERT_CHAT_ID='', FAILED_TASK_ALERT_EMAIL='')
    def test_no_channels_does_not_crash(self):
        with self.assertLogs('core.tasks', level='WARNING') as logs:
            tg = self.run_task(90)
        self.assertEqual(tg.call_count, 0)
        self.assertIn('канал алерта не настроен', logs.output[0])

    def test_disk_error_does_not_crash(self):
        with mock.patch(DISK, side_effect=FileNotFoundError('/x')), mock.patch(TG) as tg, \
                self.assertLogs('core.tasks', level='WARNING'):
            alert_disk_usage()
        self.assertEqual(tg.call_count, 0)

    def test_beat_entry(self):
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE['disk-usage-alert']
        self.assertEqual(entry['task'], 'core.tasks.alert_disk_usage')
