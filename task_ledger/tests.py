"""Учёт упавших Celery-задач (задача 8.9).

Ловушка eager-режима: при CELERY_TASK_EAGER_PROPAGATES=True исключение пробрасывается из apply(),
но task_failure отправляется до проброса (проверено тестами ниже); apply() используется с
throw=False, чтобы задача отработала как в воркере.
"""
from datetime import timedelta
from unittest import mock

from celery import shared_task
from django.test import override_settings
from django.utils import timezone

from core.tasks import ResilientTask
from tests.base import CleanCacheTestCase
from tests.factories import make_admin_role, make_broker, make_moderator, make_staff

from .models import FailedTask
from .sanitize import safe_args, safe_repr
from .signals import record_failed_task
from .tasks import purge_failed_tasks

CALLS = {'n': 0}


@shared_task(name='task_ledger.tests.boom')
def boom(*args, **kwargs):
    raise ValueError('boom for user@example.com')


@shared_task(name='task_ledger.tests.flaky', base=ResilientTask, bind=True)
def flaky(self):
    CALLS['n'] += 1
    raise ConnectionError('network down')


class LedgerTestCase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch('task_ledger.signals.capture_message')
        self.capture = patcher.start()
        self.addCleanup(patcher.stop)


class SignalTests(LedgerTestCase):
    def test_failure_creates_one_record_and_one_event(self):
        result = boom.apply(args=('+380501234567', 'user@example.com', {'a': 1}, 42, None), throw=False)
        self.assertTrue(result.failed())
        rec = FailedTask.objects.get()
        self.assertEqual((rec.task_name, rec.task_id, rec.exception_class, rec.retries),
                         ('task_ledger.tests.boom', result.id, 'ValueError', 0))
        self.assertEqual(rec.args, ['***', '***', '<dict:1>', 42, None])
        self.assertNotIn('user@example.com', rec.error)
        self.capture.assert_called_once()
        extra = self.capture.call_args.kwargs['extra']
        self.assertEqual(set(extra), {'task_name', 'task_id', 'retries', 'exception_class'})
        self.assertNotIn('380501234567', str(self.capture.call_args))

    @override_settings(RESILIENT_TASK_MAX_RETRIES=2)
    def test_last_retry_failure_creates_single_record(self):
        # Eager-повторы в Celery 5 не эмулируют воркер (вложенный apply бросает Retry наружу), поэтому
        # проверяем последнюю попытку напрямую: retries == max_retries -> окончательная неудача.
        CALLS['n'] = 0
        result = flaky.apply(retries=2, throw=False)
        self.assertTrue(result.failed())
        self.assertEqual(CALLS['n'], 1)
        rec = FailedTask.objects.get()
        self.assertEqual((rec.task_name, rec.retries, rec.exception_class), ('task_ledger.tests.flaky', 2, 'ConnectionError'))
        self.capture.assert_called_once()

    @override_settings(RESILIENT_TASK_MAX_RETRIES=2)
    def test_intermediate_attempt_retries_without_record(self):
        from celery.exceptions import Retry
        with mock.patch.object(ResilientTask, 'retry', side_effect=Retry('again')) as retry:
            with self.assertRaises(Retry):
                flaky.apply(retries=0, throw=True)
        retry.assert_called_once()
        self.assertEqual(FailedTask.objects.count(), 0)
        self.capture.assert_not_called()

    def test_texts_and_long_strings_stored_as_length_only(self):
        boom.apply(kwargs={'text': 'x' * 1000, 'msg': 'Привіт, Іване', 'code': 'AFY-2026-0001',
                           'items': [1, 2], 'n': 5}, throw=False)
        rec = FailedTask.objects.get()
        self.assertEqual(rec.kwargs['text'], '<str:1000>')
        self.assertEqual(rec.kwargs['msg'], '<str:13>')
        self.assertEqual(rec.kwargs['code'], 'AFY-2026-0001')
        self.assertEqual(rec.kwargs['items'], '<list:2>')
        self.assertEqual(rec.kwargs['n'], 5)

    def test_db_error_does_not_escape_and_monitoring_still_called(self):
        with mock.patch('task_ledger.models.FailedTask.objects.create', side_effect=RuntimeError('db down')), \
                self.assertLogs('task_ledger.signals', 'ERROR') as logs:
            record_failed_task(sender=boom, task_id='t1', exception=ValueError('x'),
                               args=('secret@mail.com',), kwargs={})
        self.capture.assert_called_once()
        self.assertNotIn('secret@mail.com', '\n'.join(logs.output))

    def test_send_notification_text_not_stored(self):
        from integrations.tasks import send_notification
        record_failed_task(sender=send_notification, task_id='t3', exception=OSError('x'),
                           args=(5, 'Нове авто за пошуком «Мій BMW» для Олени'), kwargs={})
        rec = FailedTask.objects.get()
        self.assertEqual(rec.args, [5, '<str:40>'])

    def test_broken_sender_does_not_escape(self):
        class Weird:
            @property
            def request(self):
                raise RuntimeError('no request')
        record_failed_task(sender=Weird(), task_id='t4', exception=ValueError('x'), args=(), kwargs={})
        self.capture.assert_called_once()

    def test_monitoring_disabled_record_still_created(self):
        self.capture.return_value = False
        boom.apply(throw=False)
        self.assertEqual(FailedTask.objects.count(), 1)

    def test_monitoring_error_does_not_escape(self):
        self.capture.side_effect = RuntimeError('sentry down')
        record_failed_task(sender=boom, task_id='t2', exception=ValueError('x'), args=(), kwargs={})
        self.assertEqual(FailedTask.objects.count(), 1)

    def test_successful_task_no_record(self):
        @shared_task(name='task_ledger.tests.ok')
        def ok():
            return 1
        ok.apply()
        self.assertEqual(FailedTask.objects.count(), 0)


class RealMonitoringNoopTests(CleanCacheTestCase):
    def test_without_dsn_record_created_and_no_error(self):
        from core import monitoring
        with mock.patch.object(monitoring, '_enabled', False):
            boom.apply(throw=False)
        self.assertEqual(FailedTask.objects.count(), 1)


class SanitizeTests(CleanCacheTestCase):
    def test_rules(self):
        self.assertEqual(safe_args([True, 7, None, 1.5]), [True, 7, None, 1.5])
        self.assertEqual(safe_repr('call +380 50 123 45 67 or a@b.cc'), '<str:32>')
        self.assertEqual(safe_repr('a@b.cc'), '***')
        self.assertEqual(safe_repr('+380501234567'), '***')
        self.assertEqual(safe_repr('/reset?token=abc'), '/reset?token=***')
        self.assertEqual(safe_repr({'nested': {'email': 'a@b.cc'}}), '<dict:1>')
        self.assertEqual(safe_repr(object()), '<object>')

    @override_settings(FAILED_TASK_ARG_MAX_LEN=10)
    def test_limit_from_settings(self):
        self.assertEqual(safe_repr('abcdefghijklmnop'), '<str:16>')
        self.assertEqual(safe_repr('abcdefghij'), 'abcdefghij')


class ResilientTaskTests(CleanCacheTestCase):
    @override_settings(RESILIENT_TASK_MAX_RETRIES=7, RESILIENT_TASK_ACKS_LATE=False)
    def test_params_from_settings(self):
        self.assertEqual((flaky.max_retries, flaky.acks_late), (7, False))
        self.assertTrue(flaky.retry_backoff and flaky.retry_jitter)
        self.assertEqual(flaky.autoretry_for, (OSError, ConnectionError))

    def test_other_tasks_not_affected_globally(self):
        # 8.9 не меняет поведение чужих задач: acks_late только у ResilientTask.
        from core.celery import app
        from integrations.tasks import send_notification
        from pricing.tasks import fetch_nbu_rates_task
        self.assertFalse(app.conf.task_acks_late)
        self.assertFalse(send_notification.acks_late)
        self.assertFalse(fetch_nbu_rates_task.acks_late)
        self.assertTrue(flaky.acks_late)

    def test_saved_searches_task_uses_base(self):
        from saved_searches.tasks import check_saved_searches
        self.assertIsInstance(check_saved_searches, ResilientTask)


class PurgeTests(CleanCacheTestCase):
    @override_settings(FAILED_TASK_RETENTION_DAYS=30)
    def test_purge_old_only(self):
        old = FailedTask.objects.create(task_name='old')
        FailedTask.objects.filter(pk=old.pk).update(failed_at=timezone.now() - timedelta(days=31))
        fresh = FailedTask.objects.create(task_name='fresh')
        self.assertEqual(purge_failed_tasks(), 1)
        self.assertEqual(list(FailedTask.objects.values_list('pk', flat=True)), [fresh.pk])

    def test_scheduled(self):
        from django.conf import settings
        tasks = {e['task'] for e in settings.CELERY_BEAT_SCHEDULE.values()}
        self.assertIn('task_ledger.tasks.purge_failed_tasks', tasks)


class AdminTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        self.rec = FailedTask.objects.create(task_name='notify.send', exception_class='ConnectionError',
                                             args=['ARGMARKER7', '<str:40>', 42], kwargs={'n': 1})

    def test_admin_role_sees_list_without_arg_values(self):
        self.client.force_login(make_admin_role())
        resp = self.client.get('/admin/task_ledger/failedtask/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'notify.send')
        self.assertNotContains(resp, 'ARGMARKER7')

    def test_detail_shows_only_safe_values(self):
        # В карточке аргументы видны, но в них только безопасное представление (тексты - длиной).
        self.client.force_login(make_admin_role())
        resp = self.client.get(f'/admin/task_ledger/failedtask/{self.rec.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '&lt;str:40&gt;')

    def test_add_change_delete_forbidden(self):
        self.client.force_login(make_staff(superuser=True))
        for url in ('/admin/task_ledger/failedtask/add/', f'/admin/task_ledger/failedtask/{self.rec.pk}/delete/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        resp = self.client.post(f'/admin/task_ledger/failedtask/{self.rec.pk}/change/', {'task_name': 'x'})
        self.assertEqual(resp.status_code, 403)
        self.rec.refresh_from_db()
        self.assertEqual(self.rec.task_name, 'notify.send')

    def test_moderator_and_broker_do_not_see_section(self):
        for user in (make_moderator(), make_broker()):
            self.client.force_login(user)
            self.assertEqual(self.client.get('/admin/task_ledger/failedtask/').status_code, 403)
