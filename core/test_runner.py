"""Тест-раннер с сетевым предохранителем (задача 0.2).

На время тестов запрещены исходящие соединения, кроме localhost и хоста БД
из DATABASES['default']['HOST']. Тест, который случайно ушёл во внешний API,
падает с понятной ошибкой вместо тихого платного запроса.
"""
import socket
import sys

from django.conf import settings
from django.test.runner import DiscoverRunner

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


class IsolatedDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._orig_connect = socket.socket.connect
        self._orig_create_connection = socket.create_connection
        orig_connect = self._orig_connect
        orig_create = self._orig_create_connection

        def guarded_connect(sock, address):
            _check_address(address)
            return orig_connect(sock, address)

        def guarded_create_connection(address, *args, **kw):
            _check_address(address)
            return orig_create(address, *args, **kw)

        socket.socket.connect = guarded_connect
        socket.create_connection = guarded_create_connection

    def teardown_test_environment(self, **kwargs):
        socket.socket.connect = self._orig_connect
        socket.create_connection = self._orig_create_connection
        # Ловушка aiogram (23-D4): кэш Update.event_type после прогона
        # приводит к segfault 139 в CI. Чистим для всех тестов.
        if 'aiogram.types' in sys.modules:
            from aiogram.types import Update
            try:
                Update.event_type.fget.cache_clear()
            except AttributeError:
                pass
        super().teardown_test_environment(**kwargs)
