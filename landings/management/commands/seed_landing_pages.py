"""Створює чернетки сторінок моделей зі списку landings/fixtures/landing_models.json (задача 2.16).

Ідемпотентна: існуючі slug не чіпає (правки власника не перезаписуються). Усе створюється з is_published=False,
тексти-заготовки містять позначку «[ПЕРЕВІРИТИ ...]» і без цифр. Ціни не вигадуються.
"""
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from landings.models import ModelLandingPage

DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'fixtures' / 'landing_models.json'
# Только эти ключи берутся из файла: цены, публикация и тексты задаются не им.
ALLOWED_KEYS = ('make', 'model', 'year_from', 'year_to', 'calc_year', 'sort_order')
MARK = '[ПЕРЕВІРИТИ ЗІ ВЛАСНИКОМ'


def draft_texts(title: str) -> dict:
    return {
        'intro': f'{MARK}: вступ] Розрахунок пригону {title} зі США під ключ за чинними ставками.',
        'included_text': f'{MARK}: що входить у ціну] Ціна на аукціоні, аукціонні збори, доставка зі США до '
                         'України, мито, акциз, ПДВ, пенсійний збір.',
        'typical_term_text': f'{MARK}: орієнтовний термін]',
    }


class Command(BaseCommand):
    help = 'Створити чернетки сторінок моделей з landing_models.json (без публікації та без цін).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DEFAULT_FILE))
        parser.add_argument('--dry-run', action='store_true', help='Нічого не писати, лише показати план.')

    def handle(self, *args, **options):
        try:
            items = json.loads(Path(options['file']).read_text(encoding='utf-8'))['models']
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f'Не вдалося прочитати список моделей: {exc}')
        dry = options['dry_run']
        created = skipped = 0
        try:
            with transaction.atomic():
                for order, item in enumerate(items, start=1):
                    slug = item['slug']
                    if ModelLandingPage.objects.filter(slug=slug).exists():
                        skipped += 1
                        continue
                    title = f'{item["make"]} {item["model"]}'
                    self.stdout.write(f'{"[dry-run] " if dry else ""}створити: {slug} ({title}), чекає на ціну')
                    fields = {k: item[k] for k in ALLOWED_KEYS if k in item}
                    fields.setdefault('sort_order', order * 10)
                    page = ModelLandingPage(slug=slug, is_published=False, **fields, **draft_texts(title))
                    try:
                        page.full_clean()
                    except ValidationError as exc:
                        raise CommandError(f'{slug}: {exc}')
                    if not dry:
                        page.save()
                    created += 1
        except KeyError as exc:
            raise CommandError(f'У записі списку немає ключа {exc}')
        self.stdout.write(f'Створено: {created}, вже було: {skipped}. Усі чернетки чекають на ціни та публікацію.')
