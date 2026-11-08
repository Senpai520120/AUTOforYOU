"""8.4: файлы фото объявления удаляются вместе с записью (и при каскадном удалении объявления).

Отсутствующий файл - не ошибка (обезличивание по Q3 и ручная чистка могли убрать его раньше).
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import LocalListingImage

logger = logging.getLogger(__name__)


def _delete_files(names_and_storages):
    for storage, name in names_and_storages:
        try:
            storage.delete(name)
        except Exception:  # файл уже удалён или хранилище недоступно: запись удалена, сайт не падает
            logger.warning('listing photo file not deleted: %s', name)


@receiver(post_delete, sender=LocalListingImage)
def delete_photo_files(sender, instance, **kwargs):
    files = [(f.storage, f.name) for f in (instance.image, instance.thumbnail) if f and f.name]
    if files:
        # после коммита: при откате транзакции запись вернётся - файлы должны остаться
        transaction.on_commit(lambda: _delete_files(files))
