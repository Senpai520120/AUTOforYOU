"""Помощники тестов pricing."""
from unittest import mock

# Инвалидация кэша идёт через transaction.on_commit, а TestCase оборачивает тест в транзакцию,
# которая не коммитится. Тесты, проверяющие сам факт сброса кэша, выполняют отложенный вызов сразу.
# Поведение «только после коммита» проверяют CacheInvalidateOnCommitTests (captureOnCommitCallbacks).
cache_invalidation_immediate = mock.patch(
    'pricing.cache.transaction.on_commit', new=lambda func, *a, **kw: func(),
)
