"""Миниатюры (и по желанию уменьшенные оригиналы) для уже загруженных фото объявлений (задача 8.4).

    python manage.py regenerate_listing_photos [--dry-run] [--batch N] [--resize-originals]

- без флагов: миниатюра создаётся только там, где её нет (повторный запуск ничего не делает);
- ``--resize-originals``: оригинал больше LOCAL_LISTING_PHOTO_MAX_SIDE пересохраняется уменьшенным,
  старый файл удаляется только после успешной записи нового;
- битый файл попадает в отчёт и не удаляется; ``--dry-run`` - только подсчёт.
"""
import io

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from core.uploads import ImageUploadError, make_thumbnail, sanitize_image
from local_listings.models import LocalListingImage


class Command(BaseCommand):
    help = 'Створити мініатюри (і за бажанням зменшити оригінали) для фото оголошень.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--batch', type=int, default=200)
        parser.add_argument('--resize-originals', action='store_true')

    def handle(self, *args, **opts):
        thumb_side = int(settings.LOCAL_LISTING_THUMB_MAX_SIDE)
        max_side = int(settings.LOCAL_LISTING_PHOTO_MAX_SIDE)
        qs = LocalListingImage.objects.exclude(image='').exclude(image=None).order_by('pk')
        if not opts['resize_originals']:
            qs = qs.filter(thumbnail__in=['', None])
        stats = {'thumbs': 0, 'resized': 0, 'skipped': 0}
        broken = []
        for img in qs.iterator(chunk_size=max(1, opts['batch'])):
            try:
                data = self._read(img.image)  # файл закрыт до записи: на Windows открытый не удалить
                if opts['resize_originals'] and self._too_big(data, max_side):
                    if not opts['dry_run']:
                        self._resize_original(img, data, max_side)
                        data = self._read(img.image)
                    stats['resized'] += 1
                if not img.thumbnail:
                    if not opts['dry_run']:
                        img.thumbnail.save('thumb', make_thumbnail(io.BytesIO(data), max_side=thumb_side), save=False)
                        img.save(update_fields=['thumbnail'])
                    stats['thumbs'] += 1
                else:
                    stats['skipped'] += 1
            except (OSError, ImageUploadError) as exc:
                broken.append(f'#{img.pk} {img.image.name}: {exc}')
        prefix = 'План' if opts['dry_run'] else 'Готово'
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}: мініатюр {stats["thumbs"]}, зменшено оригіналів {stats["resized"]}, '
            f'вже з мініатюрою {stats["skipped"]}, пошкоджених {len(broken)}.'
        ))
        for line in broken:
            self.stdout.write(f'  Пошкоджене (не видалено): {line}')

    @staticmethod
    def _read(fieldfile):
        with fieldfile.open('rb') as fh:
            return fh.read()

    @staticmethod
    def _too_big(data, max_side):
        with Image.open(io.BytesIO(data)) as probe:
            return max(probe.size) > max_side

    @staticmethod
    def _resize_original(img, data, max_side):
        new = sanitize_image(io.BytesIO(data), enforce_size=False, max_side=max_side)
        old_name, storage = img.image.name, img.image.storage
        img.image.save('photo', new, save=False)
        img.save(update_fields=['image'])
        if old_name and old_name != img.image.name:
            storage.delete(old_name)  # только после успешной записи нового
