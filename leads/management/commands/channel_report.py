"""Отчёт пилота Telegram-каналов (9.57, M12): заявки по каналам за окно и активные объявления канала.

Источник - существующая атрибуция заявок (2.14, `Lead.utm`): метка `utm_source=tg_<канал>` из ссылок для
подписчиков. Выводятся только счётчики, без имён, телефонов и текстов. Визиты с канала в базе не хранятся
(они в аналитике): порог «менее 50 визитов за 14 дней» владелец смотрит там.
Запуск: python manage.py channel_report [--days 14]
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from leads.models import Lead
from local_listings.models import LocalListing

PREFIX = 'tg_'


class Command(BaseCommand):
    help = 'Заявки по Telegram-каналам (utm_source=tg_<канал>) и активные объявления канала, только счётчики'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=14, help='Окно в днях (по умолчанию 14)')

    def handle(self, *args, **options):
        days = max(1, options['days'])
        since = timezone.now() - timedelta(days=days)

        listings = {}
        for name in (LocalListing.objects.filter(status=LocalListing.Status.ACTIVE).exclude(source_channel='')
                     .values_list('source_channel', flat=True)):
            listings[name.lower()] = listings.get(name.lower(), 0) + 1

        leads = {}
        rows = (Lead.objects.filter(created_at__gte=since, utm__source__startswith=PREFIX)
                .values('utm__source').annotate(n=Count('pk')))
        for row in rows:
            channel = str(row['utm__source'])[len(PREFIX):].lower()
            leads[channel] = leads.get(channel, 0) + row['n']

        self.stdout.write(f'Отчёт по каналам за {days} дн.: заявки по utm_source=tg_<канал>, активные объявления канала.')
        channels = sorted(set(listings) | set(leads))
        if not channels:
            self.stdout.write('Нет ни объявлений с каналом, ни заявок с метками tg_*.')
            return
        for channel in channels:
            self.stdout.write(f'@{channel}: заявок {leads.get(channel, 0)}, активных объявлений {listings.get(channel, 0)}')
        self.stdout.write('Визиты с канала смотрите в аналитике (UTM); в базе их нет.')
