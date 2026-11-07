"""Сводка готовности к запуску (задача 7.7a). Только чтение: в БД ничего не пишет, во внешние сервисы не ходит.

    docker compose exec backend python manage.py launch_check

Код возврата 0 - обязательное заполнено (предупреждения допустимы), 1 - есть ошибки.
Значения секретов не печатаются. Режим ВОЛНЫ-2 (`--wave 2`) - задача 7.7b.
"""
from django.core.management.base import BaseCommand, CommandError

from core import launch

LABELS = {
    launch.ERROR: 'ПОМИЛКА',
    launch.WARNING: 'УВАГА  ',
    launch.OK: 'OK     ',
    launch.INFO: 'ІНФО   ',
}


class Command(BaseCommand):
    help = 'Перевіряє готовність до запуску: змінні, прапорці, інтеграції, тарифи, налаштування сайту, бекапи.'

    def add_arguments(self, parser):
        parser.add_argument('--wave', type=int, choices=(1, 2), default=1,
                            help='Режим перевірки: 1 - ВОЛНА-1 (за замовчуванням), 2 - ВОЛНА-2 (задача 7.7b).')
        parser.add_argument('--seed-threshold', type=int, default=None,
                            help='Поріг «засіву»: мінімум активних оголошень при C2C_ENABLED=true '
                                 '(за замовчуванням змінна C2C_SEED_THRESHOLD).')
        parser.add_argument('--quiet-ok', action='store_true', help='Не друкувати рядки OK.')

    def handle(self, *args, **options):
        if options['wave'] != 1:
            raise CommandError('Режим 2 (ВОЛНА-2) - задача 7.7b, у цій версії недоступний.')
        findings = launch.run_checks(wave=1, seed_threshold=options['seed_threshold'])
        styles = {
            launch.ERROR: self.style.ERROR, launch.WARNING: self.style.WARNING,
            launch.OK: self.style.SUCCESS, launch.INFO: lambda s: s,
        }
        self.stdout.write('Перевірка готовності до запуску (режим ВОЛНА-1)')
        for finding in findings:
            if options['quiet_ok'] and finding.level == launch.OK:
                continue
            self.stdout.write(styles[finding.level](f'[{LABELS[finding.level]}] {finding.text}'))
        errors = sum(1 for f in findings if f.level == launch.ERROR)
        warnings = sum(1 for f in findings if f.level == launch.WARNING)
        self.stdout.write(f'Підсумок: помилок {errors}, попереджень {warnings}.')
        if errors:
            raise CommandError('Сайт НЕ готовий до запуску: виправте помилки вище.', returncode=1)
        self.stdout.write(self.style.SUCCESS('Обов\'язкове для запуску заповнено.'))
