"""
Management command: import_lot

Ручной/скриптовой импорт лота аукциона в Vehicle + Listing.

Примеры:
  # Из JSON-строки (manual):
  python manage.py import_lot --json '{"vin":"1HGBH41JXMN109186","make":"Honda",...}'

  # Из файла:
  python manage.py import_lot --file /path/to/lot.json

  # Через Apify (требует APIFY_TOKEN):
  python manage.py import_lot --source apify --url https://www.copart.com/lot/12345678

⚠ Автоматический импорт по расписанию — Celery (промт 10).
"""
import json
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from integrations.importer import import_lot
from integrations.providers import ManualLotProvider, get_lot_provider

User = get_user_model()


class Command(BaseCommand):
    help = 'Импортирует лот аукциона (Copart/IAAI) в Vehicle + Listing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source', choices=['manual', 'apify'], default='manual',
            help='Источник данных: manual (default) или apify',
        )
        parser.add_argument('--json', dest='json_str', help='JSON-строка с данными лота')
        parser.add_argument('--file', dest='json_file', help='Путь к JSON-файлу с данными лота')
        parser.add_argument('--url', help='URL лота (для --source apify)')
        parser.add_argument(
            '--seller-email', default=None,
            help='Email продавца (должен существовать в БД). По умолчанию — первый superuser.',
        )

    def handle(self, *args, **options):
        seller = self._resolve_seller(options['seller_email'])
        source = options['source']

        if source == 'manual':
            raw = self._load_json(options)
            provider = ManualLotProvider()
            lot_data = provider.fetch_lot(raw)
        else:
            url = options.get('url')
            if not url:
                raise CommandError('--url обязателен для --source apify')
            provider = get_lot_provider()
            lot_data = provider.fetch_lot(url)

        if lot_data.get('error'):
            raise CommandError(f'Ошибка провайдера: {lot_data["error"]}')

        if lot_data.get('demo'):
            self.stdout.write(self.style.WARNING('⚠ Демо-режим (провайдер без ключа).'))

        vehicle, listing, created = import_lot(lot_data, seller=seller)

        action = 'Создан' if created else 'Обновлён'
        self.stdout.write(self.style.SUCCESS(
            f'{action}: Vehicle #{vehicle.id} ({vehicle.vin}), '
            f'Listing #{listing.id} [{listing.status}]'
        ))

    def _load_json(self, options) -> dict:
        json_str = options.get('json_str')
        json_file = options.get('json_file')

        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as exc:
                raise CommandError(f'Неверный JSON: {exc}')

        if json_file:
            try:
                with open(json_file) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError(f'Ошибка чтения файла: {exc}')

        # Читаем из stdin если есть
        if not sys.stdin.isatty():
            try:
                return json.load(sys.stdin)
            except json.JSONDecodeError as exc:
                raise CommandError(f'Неверный JSON из stdin: {exc}')

        raise CommandError('Укажите --json, --file или передайте JSON через stdin')

    def _resolve_seller(self, email: str | None):
        if email:
            try:
                return User.objects.get(email=email)
            except User.DoesNotExist:
                raise CommandError(f'Пользователь {email} не найден')
        # fallback — первый суперюзер
        seller = User.objects.filter(is_superuser=True).first()
        if not seller:
            raise CommandError('Не найден ни один superuser. Укажите --seller-email.')
        return seller
