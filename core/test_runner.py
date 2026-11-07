"""Тест-раннер с сетевым предохранителем (задача 0.2).

На время тестов запрещены исходящие соединения, кроме localhost и хоста БД
из DATABASES['default']['HOST']. Тест, который случайно ушёл во внешний API,
падает с понятной ошибкой вместо тихого платного запроса.
"""
import socket
import sys

from django.conf import settings
from django.test.runner import DiscoverRunner, ParallelTestSuite

_LOCAL_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '0.0.0.0'})


class ExternalNetworkBlocked(RuntimeError):
    """Тест попытался открыть соединение с внешним хостом."""


def _allowed_hosts():
    allowed = set(_LOCAL_HOSTS)
    db_host = (settings.DATABASES.get('default', {}).get('HOST') or '').strip()
    if db_host:
        allowed.add(db_host)
    return allowed


def _check_address(address):
    # AF_UNIX и прочие не-кортежные адреса — локальные, пропускаем.
    if not isinstance(address, tuple) or len(address) < 2:
        return
    host, port = address[0], address[1]
    if isinstance(host, bytes):
        host = host.decode('ascii', 'ignore')
    if host in _allowed_hosts():
        return
    raise ExternalNetworkBlocked(
        f'Внешний сетевой запрос в тесте: {host}:{port}. Замокайте провайдер'
    )


_ORIGINALS: dict = {}


def install_network_guard() -> None:
    """Ставит предохранитель на socket. Идемпотентно: повторный вызов ничего не меняет.

    Вызывается и в основном процессе (setup_test_environment), и в каждом воркере `--parallel`
    (ParallelTestSuite.process_setup). При fork воркер наследует патч родителя, при spawn/forkserver
    (Windows, macOS) воркер стартует «чистым» - без явной установки предохранителя там его бы не было.
    """
    if _ORIGINALS:
        return
    _ORIGINALS.update(
        connect=socket.socket.connect, connect_ex=socket.socket.connect_ex, sendto=socket.socket.sendto,
        create_connection=socket.create_connection,
    )
    orig_connect, orig_connect_ex = _ORIGINALS['connect'], _ORIGINALS['connect_ex']
    orig_sendto, orig_create = _ORIGINALS['sendto'], _ORIGINALS['create_connection']

    def guarded_connect(sock, address):
        _check_address(address)
        return orig_connect(sock, address)

    def guarded_create_connection(address, *args, **kw):
        _check_address(address)
        return orig_create(address, *args, **kw)

    def guarded_connect_ex(sock, address):
        _check_address(address)
        return orig_connect_ex(sock, address)

    def guarded_sendto(sock, data, *args):
        # sendto(data, address) или sendto(data, flags, address): адрес - последний аргумент.
        if args:
            _check_address(args[-1])
        return orig_sendto(sock, data, *args)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.socket.sendto = guarded_sendto
    socket.create_connection = guarded_create_connection


def remove_network_guard() -> None:
    if not _ORIGINALS:
        return
    socket.socket.connect = _ORIGINALS['connect']
    socket.socket.connect_ex = _ORIGINALS['connect_ex']
    socket.socket.sendto = _ORIGINALS['sendto']
    socket.create_connection = _ORIGINALS['create_connection']
    _ORIGINALS.clear()


def _guard_process_setup(*args):
    """Хук воркера `--parallel` (Django вызывает его в spawn/forkserver до django.setup()). Функция модульная: picklable."""
    install_network_guard()


class GuardedParallelTestSuite(ParallelTestSuite):
    """Параллельный набор: в каждом воркере ставится сетевой предохранитель (задача 9.47)."""
    process_setup = _guard_process_setup


class IsolatedDiscoverRunner(DiscoverRunner):
    parallel_test_suite = GuardedParallelTestSuite

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        install_network_guard()

    def teardown_test_environment(self, **kwargs):
        remove_network_guard()
        # Ловушка aiogram (23-D4): кэш Update.event_type после прогона
        # приводит к segfault 139 в CI. Чистим для всех тестов.
        if 'aiogram.types' in sys.modules:
            from aiogram.types import Update
            try:
                Update.event_type.fget.cache_clear()
            except AttributeError:
                pass
        super().teardown_test_environment(**kwargs)
