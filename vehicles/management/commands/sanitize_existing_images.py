"""
Management command: sanitize_existing_images (задача 1.10)

Прогоняет уже загруженные фото через core.uploads.sanitize_image: новое uuid-имя,
без EXIF/GPS. Фото трекинга заодно переезжают из публичного media/ в приватное
хранилище (PRIVATE_MEDIA_ROOT). Модели: LocalListingImage.image, VehicleImage.image,
TrackingEvent.photo. Legacy Car.image не трогается.

По умолчанию — только план (dry-run), ничего не меняется:
  python manage.py sanitize_existing_images
Выполнить:
  python manage.py sanitize_existing_images --apply
Битые/не-изображения только попадают в отчёт; удалить их файл и очистить поле:
  python manage.py sanitize_existing_images --apply --delete-invalid

Старый файл удаляется только после успешного сохранения нового и обновления строки.
Отсутствующий файл — в отчёт, без падения. Лимит байт не применяется (файлы уже
лежат), лимит пикселей — да.
"""
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from core.uploads import SANITIZED_NAME_RE, ImageUploadError, sanitize_image

BATCH = 200


def _targets():
    from local_listings.models import LocalListingImage
    from shipments.models import TrackingEvent
    from vehicles.models import VehicleImage

    return [(LocalListingImage, 'image'), (VehicleImage, 'image'), (TrackingEvent, 'photo')]


class Command(BaseCommand):
    help = 'Очищает уже загруженные фото от EXIF и переименовывает в uuid (по умолчанию dry-run).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Выполнить изменения (без флага — только план).')
        parser.add_argument('--dry-run', action='store_true', help='Только план (поведение по умолчанию).')
        parser.add_argument('--delete-invalid', action='store_true',
                            help='С --apply: удалить файлы, которые не являются допустимым изображением.')

    def handle(self, *args, **options):
        apply = options['apply'] and not options['dry_run']
        delete_invalid = apply and options['delete_invalid']
        if not apply:
            self.stdout.write('Режим dry-run: ничего не меняется. Для выполнения: --apply.')

        totals = {'clean': 0, 'done': 0, 'missing': 0, 'invalid': 0, 'deleted': 0}
        for model, field_name in _targets():
            self._process_model(model, field_name, apply, delete_invalid, totals)

        self.stdout.write(self.style.SUCCESS(
            f"Итого: обработано {totals['done']}, уже чистых {totals['clean']}, "
            f"нет файла {totals['missing']}, битых {totals['invalid']} (удалено {totals['deleted']})."
        ))

    def _process_model(self, model, field_name, apply, delete_invalid, totals):
        label = f'{model._meta.label}.{field_name}'
        field = model._meta.get_field(field_name)
        target = field.storage
        qs = (model.objects.exclude(**{f'{field_name}__isnull': True}).exclude(**{field_name: ''})
              .order_by('pk').only('pk', field_name))
        for obj in qs.iterator(chunk_size=BATCH):
            name = getattr(obj, field_name).name
            source = self._locate(name, target)
            if source is None:
                totals['missing'] += 1
                self.stdout.write(self.style.WARNING(f'  [нет файла] {label} #{obj.pk}: {name}'))
                continue
            basename = name.rsplit('/', 1)[-1]
            if source is target and SANITIZED_NAME_RE.match(basename):
                totals['clean'] += 1
                continue
            try:
                with source.open(name, 'rb') as fh:
                    content = sanitize_image(fh, enforce_size=False)
            except ImageUploadError as exc:
                totals['invalid'] += 1
                self.stdout.write(self.style.WARNING(f'  [битый] {label} #{obj.pk}: {name} — {exc}'))
                if delete_invalid:
                    source.delete(name)
                    model.objects.filter(pk=obj.pk).update(**{field_name: ''})
                    totals['deleted'] += 1
                continue

            if not apply:
                totals['done'] += 1
                self.stdout.write(f'  [план] {label} #{obj.pk}: {name} → очистка EXIF, uuid-имя')
                continue

            new_name = target.save(field.generate_filename(obj, content.name), content)
            model.objects.filter(pk=obj.pk).update(**{field_name: new_name})
            # Старый файл — только после того, как новый сохранён и строка обновлена.
            if not (source is target and new_name == name):
                source.delete(name)
            totals['done'] += 1
            self.stdout.write(f'  ✓ {label} #{obj.pk}: {name} → {new_name}')

    @staticmethod
    def _locate(name, target):
        if target.exists(name):
            return target
        # Фото трекинга до 1.10 лежали в публичном media/: переносим в приватное хранилище.
        if target is not default_storage and default_storage.exists(name):
            return default_storage
        return None
