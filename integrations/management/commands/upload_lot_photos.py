"""
Management command: upload_lot_photos

Переносит фото лотов из внешних URL (VehicleImage.source_url) в основное хранилище
(S3 или локально), заполняя поле VehicleImage.image.

Запускать ТОЛЬКО при наличии настроенного хранилища.
При USE_S3=False фото сохраняются в media/ локально (только для тестов).

Использование:
  python manage.py upload_lot_photos              # все фото без image
  python manage.py upload_lot_photos --limit 50   # первые 50
  python manage.py upload_lot_photos --dry-run     # показать что будет, не скачивать

⚠ S3-перенос фото — промт 7. Для продакшена задать S3_BUCKET_NAME, AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY (и S3_REGION) в .env.
"""
import io
import os

import httpx
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from vehicles.models import VehicleImage


class Command(BaseCommand):
    help = 'Скачивает фото лотов из source_url и сохраняет в хранилище (S3 или local).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='Максимум фото за один запуск (0=все)')
        parser.add_argument('--dry-run', action='store_true', help='Показать список без скачивания')

    def handle(self, *args, **options):
        from django.conf import settings
        use_s3 = getattr(settings, 'USE_S3', False)
        storage_label = 'S3' if use_s3 else 'локальная папка media/'

        qs = VehicleImage.objects.filter(source_url__gt='', image='').order_by('id')
        limit = options['limit']
        if limit:
            qs = qs[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Нет фото для переноса.'))
            return

        self.stdout.write(f'Найдено {total} фото для переноса → {storage_label}')

        if options['dry_run']:
            for img in qs:
                self.stdout.write(f'  [dry-run] #{img.pk}: {img.source_url}')
            return

        ok = 0
        fail = 0
        for img in qs:
            try:
                resp = httpx.get(img.source_url, timeout=15.0, follow_redirects=True)
                resp.raise_for_status()

                content_type = resp.headers.get('content-type', 'image/jpeg')
                ext = '.jpg' if 'jpeg' in content_type else '.png' if 'png' in content_type else '.jpg'
                filename = f'lot_{img.vehicle_id}_{img.pk}{ext}'

                img.image.save(filename, ContentFile(resp.content), save=True)
                ok += 1
                self.stdout.write(f'  ✓ #{img.pk} → {filename}')
            except Exception as exc:
                fail += 1
                self.stdout.write(self.style.WARNING(f'  ✗ #{img.pk} {img.source_url}: {exc}'))

        style = self.style.SUCCESS if fail == 0 else self.style.WARNING
        self.stdout.write(style(f'Готово: {ok} успешно, {fail} ошибок.'))
