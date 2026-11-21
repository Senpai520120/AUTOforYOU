"""Удаление фото у уже закрытых объявлений (задача 10.30).

    python manage.py purge_listing_photos            # dry-run: только подсчёт
    python manage.py purge_listing_photos --apply    # удалить

Берутся объявления rejected/sold, закрытые больше LOCAL_LISTING_PHOTO_PURGE_DAYS дней назад.
Выводит только числа, без данных пользователей. Повторный запуск ничего не находит.
"""
from django.core.management.base import BaseCommand

from local_listings.services import listings_due_for_photo_purge, photo_purge_days, purge_listing_photos


class Command(BaseCommand):
    help = 'Видалити фото відхилених/проданих оголошень (за замовчуванням dry-run).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Справді видалити (без нього лише підрахунок).')
        parser.add_argument('--dry-run', action='store_true', help='Лише підрахунок (типова поведінка).')

    def handle(self, *args, **opts):
        apply = opts['apply'] and not opts['dry_run']
        listings = photos = 0
        for listing in listings_due_for_photo_purge().iterator():
            listings += 1
            if apply:
                photos += purge_listing_photos(listing)
            else:
                photos += listing.images.count()
        prefix = 'Видалено' if apply else 'План (dry-run, додайте --apply)'
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}: оголошень {listings}, фото {photos} (старше {photo_purge_days()} дн.).'
        ))
