from django.core.management.base import BaseCommand, CommandError

from metrics.reports import build_report, dispatch_report


class Command(BaseCommand):
    help = 'Отчёт о воронке за последние полные дни: только счётчики, без ПДн (9.50).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=7, help='Сколько полных дней, вчера включительно')
        parser.add_argument('--dry-run', action='store_true', help='Показать текст и ничего не отправлять')

    def handle(self, *args, days, dry_run, **options):
        if days < 1:
            raise CommandError('--days должно быть не меньше 1')
        text = build_report(days)
        self.stdout.write(text)
        if dry_run:
            return
        channels = dispatch_report(text)
        if not channels:
            raise CommandError('Отчёт не отправлен: задайте FUNNEL_REPORT_CHAT_ID или FUNNEL_REPORT_EMAIL')
        self.stdout.write(f"Поставлено в очередь: {', '.join(channels)}")
