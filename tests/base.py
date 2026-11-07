"""Общие базовые классы тестов (задача 0.2, 13-Q13)."""
from django.core.cache import cache
from django.test import TestCase


class CleanCacheTestCase(TestCase):
    """TestCase, который не оставляет и не наследует состояние кэша.

    Откат транзакции TestCase не трогает LocMem-кэш: объекты удалённых
    seed-строк (например, тарифы аукционных сборов) переживают класс и
    «воскресают» в следующем. Кэш чистится на входе в класс, перед каждым
    тестом и на выходе из класса.

    Сидировать данные нужно в setUpTestData, а не в setUpClass + call_command.
    Если переопределяете setUp / setUpClass / tearDownClass — вызывайте super().
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cache.clear()

    def setUp(self):
        super().setUp()
        cache.clear()

    @classmethod
    def tearDownClass(cls):
        cache.clear()
        super().tearDownClass()
