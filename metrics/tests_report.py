"""Отчёт о воронке владельцу (задача 9.50)."""
from datetime import date, datetime, timedelta
from io import StringIO
from itertools import count
from unittest import mock
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramRetryAfter
from django.conf import settings
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from core.attribution import clean_attribution
from leads.models import Lead, LeadPartnerStatusChange, NotifyStatus, PartnerStatus, Qualification
from metrics import reports, tasks
from metrics.models import DailyMetric, MetricKey
from task_ledger.models import FailedTask
from telegram_bot.provider import SendResult
from tests.factories import make_lead

KYIV = ZoneInfo('Europe/Kyiv')
START, END = date(2026, 3, 2), date(2026, 3, 8)
INSIDE = datetime(2026, 3, 4, 12, 0, tzinfo=KYIV)
BEFORE = datetime(2026, 3, 1, 23, 59, tzinfo=KYIV)
AFTER = datetime(2026, 3, 9, 0, 0, tzinfo=KYIV)
COMMAND_DISPATCH = 'metrics.management.commands.weekly_funnel_report.dispatch_report'
_public_ids = count(1)


def lead_at(moment, **kw):
    lead = make_lead(public_id=f'AFY-T-{next(_public_ids):04d}', **kw)
    Lead.objects.filter(pk=lead.pk).update(created_at=moment)
    return Lead.objects.get(pk=lead.pk)


def status_change(lead, status, moment=INSIDE):
    with mock.patch('django.utils.timezone.now', return_value=moment):
        return LeadPartnerStatusChange.objects.create(lead=lead, to_status=status)


class ReportPeriodTests(TestCase):
    def test_full_days_ending_yesterday(self):
        self.assertEqual(reports.report_period(7, today=date(2026, 3, 9)), (START, END))

    def test_single_day(self):
        self.assertEqual(reports.report_period(1, today=date(2026, 3, 9)), (END, END))


class CollectFunnelTests(TestCase):
    def collect(self):
        return reports.collect_funnel(START, END)

    def test_metrics_are_summed_only_inside_period(self):
        for day, amount in ((START, 2), (END, 3), (date(2026, 3, 1), 100), (date(2026, 3, 9), 100)):
            DailyMetric.objects.create(date=day, key=MetricKey.LANDING_VISIT, value=amount)
        DailyMetric.objects.create(date=START, key=MetricKey.CALCULATOR_VISIT, value=7)
        DailyMetric.objects.create(date=START, key=MetricKey.CALCULATION, value=4)
        data = self.collect()
        self.assertEqual(data['landing_visits'], 5)
        self.assertEqual(data['calculator_visits'], 7)
        self.assertEqual(data['calculations'], 4)

    def test_leads_counted_by_kyiv_day_bounds(self):
        lead_at(BEFORE)
        lead_at(datetime(2026, 3, 2, 0, 0, tzinfo=KYIV))
        lead_at(datetime(2026, 3, 8, 23, 59, tzinfo=KYIV))
        lead_at(AFTER)
        self.assertEqual(self.collect()['leads'], 2)

    def test_hot_only_from_period(self):
        lead_at(INSIDE, qualification=Qualification.HOT)
        lead_at(INSIDE, qualification=Qualification.COLD)
        lead_at(BEFORE, qualification=Qualification.HOT)
        self.assertEqual(self.collect()['hot'], 1)

    def test_status_events_counted_once_per_lead_and_only_in_period(self):
        old_lead = lead_at(BEFORE)
        status_change(old_lead, PartnerStatus.DEPOSIT)
        status_change(old_lead, PartnerStatus.DEPOSIT)
        status_change(lead_at(INSIDE), PartnerStatus.DEPOSIT, moment=AFTER)
        status_change(lead_at(INSIDE), PartnerStatus.BOUGHT)
        status_change(lead_at(INSIDE), PartnerStatus.NO_ANSWER)
        data = self.collect()
        self.assertEqual(data['deposits'], 1)
        self.assertEqual(data['bought'], 1)
        self.assertEqual(data['no_answer'], 1)

    def test_median_first_response_uses_answers_from_period(self):
        for hours in (1, 2, 9):
            lead = lead_at(INSIDE)
            Lead.objects.filter(pk=lead.pk).update(first_response_at=INSIDE + timedelta(hours=hours))
        outside = lead_at(BEFORE)
        Lead.objects.filter(pk=outside.pk).update(first_response_at=BEFORE)
        self.assertEqual(self.collect()['median_response_seconds'], 7200)

    def test_median_without_answers_is_none(self):
        lead_at(INSIDE)
        self.assertIsNone(self.collect()['median_response_seconds'])

    def test_undelivered_needs_both_channels_unsent(self):
        sent, failed, skipped = NotifyStatus.SENT, NotifyStatus.FAILED, NotifyStatus.SKIPPED
        lead_at(INSIDE, telegram_status=sent, email_status=failed)
        lead_at(INSIDE, telegram_status=failed, email_status=sent)
        lead_at(INSIDE, telegram_status=failed, email_status=failed)
        lead_at(INSIDE, telegram_status=skipped, email_status=skipped)
        lead_at(BEFORE, telegram_status=failed, email_status=failed)
        self.assertEqual(self.collect()['undelivered'], 2)

    def test_failed_tasks_only_in_period(self):
        for moment in (INSIDE, BEFORE):
            row = FailedTask.objects.create(task_name='x')
            FailedTask.objects.filter(pk=row.pk).update(failed_at=moment)
        self.assertEqual(self.collect()['failed_tasks'], 1)

    def test_sources_limited_to_top(self):
        for index in range(reports.TOP_SOURCES + 2):
            for _ in range(index + 1):
                lead_at(INSIDE, utm={'source': f'src{index}'})
        sources = self.collect()['sources']
        self.assertEqual(len(sources), reports.TOP_SOURCES)
        self.assertEqual(sources[0], ('src6', 7))


class RenderReportTests(TestCase):
    def render(self):
        return reports.render_report(reports.collect_funnel(START, END))

    def test_conversions_and_period(self):
        DailyMetric.objects.create(date=START, key=MetricKey.LANDING_VISIT, value=150)
        DailyMetric.objects.create(date=START, key=MetricKey.CALCULATOR_VISIT, value=50)
        DailyMetric.objects.create(date=START, key=MetricKey.CALCULATION, value=20)
        lead_at(INSIDE, qualification=Qualification.HOT)
        lead_at(INSIDE)
        text = self.render()
        self.assertIn('02.03.2026 – 08.03.2026', text)
        self.assertIn('візит → заявка: 1.0%', text)
        self.assertIn('розрахунок → заявка: 10.0%', text)
        self.assertIn('заявка → гаряча: 50.0%', text)

    def test_empty_period_has_no_division_error(self):
        text = self.render()
        self.assertIn('візит → заявка: —', text)
        self.assertIn('депозит → викуп: —', text)
        self.assertIn('Медіана першої відповіді: немає даних', text)

    def test_duration_format(self):
        lead = lead_at(INSIDE)
        Lead.objects.filter(pk=lead.pk).update(first_response_at=INSIDE + timedelta(minutes=85))
        self.assertIn('Медіана першої відповіді: 1 год 25 хв', self.render())

    def test_no_personal_data(self):
        lead = lead_at(INSIDE, name='Секретне Імʼя', phone='+380671112233', city='Місто-Тест',
                       email='secret@example.test', contact_handle='secret_handle', comment='Секретний коментар',
                       telegram_status=NotifyStatus.FAILED, email_status=NotifyStatus.FAILED)
        text = self.render()
        for secret in ('Секретне', '+380671112233', 'Місто-Тест', 'secret@example.test', 'secret_handle',
                       'Секретний', lead.public_id):
            self.assertNotIn(secret, text)

    def test_phone_like_source_passes_attribution_filter_but_is_hidden(self):
        utm = clean_attribution({'utm': {'source': '380671112233'}})['utm']
        self.assertEqual(utm['source'], '380671112233')  # фильтр атрибуции цифры пропускает, скрывает отчёт
        self.assertEqual(reports._source_label(utm['source']), reports.HIDDEN_SOURCE)
        self.assertEqual(reports._source_label('tel380671112233'), reports.HIDDEN_SOURCE)
        self.assertEqual(reports._source_label('google-2026'), 'google-2026')
        # Напрямую, не через БД: SQLite читает цифровую строку из JSON как число, PostgreSQL - как строку.
        text = reports.render_report({**reports.collect_funnel(START, END), 'sources': [(utm['source'], 1)]})
        self.assertNotIn('380671112233', text)
        self.assertIn(f'{reports.HIDDEN_SOURCE}: 1', text)

    def test_long_multiline_source_is_flattened_and_cut(self):
        lead_at(INSIDE, utm={'source': 'a\nb ' + 'x' * 100})
        line = next(row for row in self.render().splitlines() if row.startswith('a b'))
        self.assertEqual(line, 'a b ' + 'x' * (reports.SOURCE_MAX_LEN - 4) + ': 1')


class DispatchTests(TestCase):
    @override_settings(FUNNEL_REPORT_EMAIL='owner@example.test', FUNNEL_REPORT_CHAT_ID='42')
    def test_both_channels(self):
        with mock.patch('integrations.email.send_email', return_value={'queued': True}) as email, \
                mock.patch.object(tasks.send_funnel_report_telegram, 'delay') as telegram:
            channels = reports.dispatch_report('текст')
        self.assertEqual(channels, ['email', 'telegram'])
        email.assert_called_once_with('owner@example.test', reports.EMAIL_SUBJECT, 'текст')
        telegram.assert_called_once_with('текст')

    @override_settings(FUNNEL_REPORT_EMAIL='owner@example.test', FUNNEL_REPORT_CHAT_ID='42')
    def test_email_failure_does_not_stop_telegram(self):
        with mock.patch('integrations.email.send_email', return_value={'queued': False}), \
                mock.patch.object(tasks.send_funnel_report_telegram, 'delay') as telegram, \
                self.assertLogs('metrics.reports', 'WARNING'):
            channels = reports.dispatch_report('текст')
        self.assertEqual(channels, ['telegram'])
        telegram.assert_called_once_with('текст')

    def test_no_channels_configured(self):
        with mock.patch('integrations.email.send_email') as email, \
                mock.patch.object(tasks.send_funnel_report_telegram, 'delay') as telegram, \
                self.assertLogs('metrics.reports', 'WARNING'):
            self.assertEqual(reports.dispatch_report('текст'), [])
        email.assert_not_called()
        telegram.assert_not_called()

    def test_scheduled_monday_nine_with_expiry(self):
        entry = settings.CELERY_BEAT_SCHEDULE['weekly-funnel-report']
        self.assertEqual(entry['task'], 'metrics.tasks.send_weekly_funnel_report')
        self.assertEqual(entry['schedule'].day_of_week, {1})
        self.assertEqual(entry['schedule'].hour, {9})
        self.assertEqual(entry['schedule'].minute, {0})
        self.assertEqual(entry['options']['expires'], 86400)

    def test_beat_task_builds_and_dispatches(self):
        with mock.patch.object(reports, 'build_report', return_value='текст') as build, \
                mock.patch.object(reports, 'dispatch_report') as dispatch:
            tasks.send_weekly_funnel_report()
        build.assert_called_once_with(7)
        dispatch.assert_called_once_with('текст')


@override_settings(FUNNEL_REPORT_CHAT_ID='42')
class TelegramTaskTests(TestCase):
    def run_task(self, **send):
        with mock.patch('telegram_bot.provider.telegram_configured', return_value=True), \
                mock.patch('telegram_bot.sender.send_message', **send) as sender:
            tasks.send_funnel_report_telegram.run('<b>текст</b>')
        return sender

    def test_sends_plain_text_to_owner_chat(self):
        sender = self.run_task(return_value=SendResult(ok=True, message_id=1))
        sender.assert_called_once_with('42', '<b>текст</b>', parse_mode=None, demo_body='weekly funnel report')

    def test_rejection_fails_task_for_ledger(self):
        with self.assertRaisesMessage(RuntimeError, 'TelegramBadRequest'):
            self.run_task(return_value=SendResult(ok=False, reason='TelegramBadRequest'))

    def test_network_error_is_left_for_autoretry(self):
        self.assertIn(ConnectionError, tasks.send_funnel_report_telegram.autoretry_for)
        with self.assertRaisesMessage(ConnectionError, 'down'):
            self.run_task(side_effect=ConnectionError('down'))

    def test_flood_control_retries_with_capped_pause(self):
        error = TelegramRetryAfter(method=mock.Mock(), message='chat 42', retry_after=5000)
        with mock.patch.object(tasks.send_funnel_report_telegram, 'retry', side_effect=RuntimeError('retry')) as retry, \
                self.assertRaisesMessage(RuntimeError, 'retry'):
            self.run_task(side_effect=error)
        self.assertEqual(retry.call_args.kwargs['countdown'], tasks.RETRY_AFTER_MAX_COUNTDOWN)
        self.assertNotIn('42', str(retry.call_args.kwargs['exc']))

    def test_not_configured_sends_nothing(self):
        with mock.patch('telegram_bot.provider.telegram_configured', return_value=False), \
                mock.patch('telegram_bot.sender.send_message') as sender, \
                self.assertLogs('metrics.tasks', 'WARNING'):
            tasks.send_funnel_report_telegram.run('текст')
        sender.assert_not_called()


class CommandTests(TestCase):
    def test_dry_run_prints_and_sends_nothing(self):
        out = StringIO()
        with mock.patch(COMMAND_DISPATCH) as dispatch:
            call_command('weekly_funnel_report', '--dry-run', stdout=out)
        dispatch.assert_not_called()
        self.assertIn('Воронка AUTOforYOU', out.getvalue())

    def test_days_argument_changes_period(self):
        out = StringIO()
        with mock.patch('metrics.reports.timezone.localdate', return_value=date(2026, 3, 9)):
            call_command('weekly_funnel_report', '--days', '28', '--dry-run', stdout=out)
        self.assertIn('09.02.2026 – 08.03.2026', out.getvalue())

    def test_zero_days_rejected(self):
        with self.assertRaisesMessage(CommandError, '--days'):
            call_command('weekly_funnel_report', '--days', '0', '--dry-run')

    def test_send_reports_channels(self):
        out = StringIO()
        with mock.patch(COMMAND_DISPATCH, return_value=['telegram']):
            call_command('weekly_funnel_report', stdout=out)
        self.assertIn('Поставлено в очередь: telegram', out.getvalue())

    def test_no_channel_is_an_error(self):
        with mock.patch(COMMAND_DISPATCH, return_value=[]), \
                self.assertRaisesMessage(CommandError, 'FUNNEL_REPORT_CHAT_ID'):
            call_command('weekly_funnel_report', stdout=StringIO())
