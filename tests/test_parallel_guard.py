"""Сетевой предохранитель работает и в воркерах `--parallel` (задача 9.47).

Воркеры в режиме spawn (Windows, macOS) стартуют без патча родителя. Тест запускает отдельный процесс
`manage.py test tests.probe_parallel_guard --parallel 2` с принудительным spawn и проверяет, что зонд, выполняющийся
именно в воркере, получил ExternalNetworkBlocked. Без хука `process_setup` в GuardedParallelTestSuite зонд краснеет.
"""
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase
from django.test import runner as django_runner

from core.test_runner import GuardedParallelTestSuite, IsolatedDiscoverRunner, _guard_process_setup

LAUNCHER = (
    'import multiprocessing, sys\n'
    "multiprocessing.set_start_method('spawn', force=True)\n"
    'from django.core.management import execute_from_command_line\n'
    "execute_from_command_line(['manage.py', 'test', 'tests.probe_parallel_guard', '--parallel', '2', '--noinput'])\n"
)


class ParallelGuardTests(SimpleTestCase):
    def test_runner_uses_guarded_parallel_suite(self):
        self.assertIs(IsolatedDiscoverRunner.parallel_test_suite, GuardedParallelTestSuite)
        self.assertIs(GuardedParallelTestSuite.process_setup, _guard_process_setup)

    def test_tblib_is_installed_so_worker_exceptions_are_passed_back(self):
        self.assertIsNotNone(django_runner.tblib)

    def test_probe_in_spawned_workers_sees_blocked_network(self):
        env = {**os.environ, 'DATABASE_URL': '', 'REDIS_URL': ''}
        proc = subprocess.run([sys.executable, '-c', LAUNCHER], cwd=settings.BASE_DIR, env=env,
                              capture_output=True, text=True, timeout=300, encoding='utf8', errors='replace')
        output = (proc.stdout or '') + (proc.stderr or '')
        self.assertEqual(proc.returncode, 0, output[-1500:])
        self.assertIn('Ran 2 tests', output)
        self.assertNotIn('не в воркере', output)
