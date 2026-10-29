from django.core.management.base import BaseCommand

from integrations.models import RegistryReport


class Command(BaseCommand):
    help = (
        'Удаляет кэшированные RegistryReport с полем error в payload (в них мог оказаться API-ключ). '
        'По умолчанию dry-run: только печатает количество. Удаление — с флагом --confirm.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Только посчитать (по умолчанию).')
        parser.add_argument('--confirm', action='store_true', help='Действительно удалить записи.')

    def handle(self, *args, **options):
        qs = RegistryReport.objects.filter(payload__has_key='error')
        count = qs.count()
        if options['confirm'] and not options['dry_run']:
            qs.delete()
            self.stdout.write(f'Удалено записей: {count}')
        else:
            self.stdout.write(f'dry-run: записей с error: {count}. Для удаления добавьте --confirm.')
