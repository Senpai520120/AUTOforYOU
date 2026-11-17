"""Зонд для tests/test_parallel_guard.py (задача 9.47). Имя не начинается с test, поэтому обычный прогон его не собирает.

Запускается отдельным процессом: `manage.py test tests.probe_parallel_guard --parallel 2`. Два класса нужны, чтобы
Django действительно разнёс тесты по воркерам. Каждый тест доказывает, что он идёт в воркере и что соединение с внешним
хостом заблокировано предохранителем.
"""
import multiprocessing
import socket

from django.test import SimpleTestCase

from core.test_runner import ExternalNetworkBlocked


class _Probe:
    def test_runs_in_worker_and_blocks_external_connection(self):
        self.assertIsNotNone(multiprocessing.parent_process(), 'тест выполняется не в воркере --parallel')
        with self.assertRaises(ExternalNetworkBlocked):
            socket.create_connection(('example.com', 80), timeout=1)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        with self.assertRaises(ExternalNetworkBlocked):
            s.connect(('93.184.216.34', 80))


class ProbeA(_Probe, SimpleTestCase):
    pass


class ProbeB(_Probe, SimpleTestCase):
    pass
