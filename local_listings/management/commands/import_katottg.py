"""Импорт населённых пунктов из CSV нормализованного формата (задача 8.2, A3.1).

Формат (UTF-8, первая строка - заголовок, разделитель - запятая):

    katottg,name,category,region_katottg,region_name,district_name,hromada_name,is_major
    UA05020030010063720,Вінниця,M,UA05000000000010236,Вінницька область,Вінницький,Вінницька,1

- ``katottg`` - код пункта (уникален), ``category`` - код вида из источника (M, T, C, X ...; не проверяется);
- ``region_*`` - область пункта; ``is_major`` - 1/0, необязательная колонка (крупный город для быстрого списка).

Сопоставление: по ``katottg``; запись без кода (из ``seed_regions``) - по (область, нормализованное имя),
поэтому ``City.id`` и ссылки объявлений сохраняются, ничего не удаляется. Повторный импорт идемпотентен.
``--dry-run`` печатает план и откатывает транзакцию. ``--deactivate-missing`` помечает ``is_active=False``
пункты, которых нет в файле, кроме тех, на которые ссылаются объявления (они остаются и попадают в отчёт).
Реальный файл реестра в репозиторий не кладётся: путь - аргумент или ``KATOTTG_FILE`` в ``.env``.
"""
import csv
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from local_listings.models import City, Region
from local_listings.places import normalize_place_name

from .seed_regions import _slugify_uk

REQUIRED = ('katottg', 'name', 'category', 'region_katottg', 'region_name')
TRUE = ('1', 'true', 'yes', 'так')


class _DryRun(Exception):
    pass


class Command(BaseCommand):
    help = 'Імпорт населених пунктів КАТОТТГ з CSV (див. docstring модуля: формат колонок).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default='', help='Шлях до CSV; за замовчуванням KATOTTG_FILE з .env')
        parser.add_argument('--dry-run', action='store_true', help='Лише план, нічого не записувати')
        parser.add_argument('--deactivate-missing', action='store_true',
                            help='Позначити відсутні у файлі пункти is_active=False (крім тих, що мають оголошення)')

    def handle(self, *args, **options):
        path = options['file'] or getattr(settings, 'KATOTTG_FILE', '')
        if not path:
            raise CommandError('Не вказано файл: --file або KATOTTG_FILE у .env')
        rows = self._read(path)
        stats = Counter()
        kept_with_listings = []
        try:
            with transaction.atomic():
                regions = self._import_regions(rows, stats)
                touched = self._import_cities(rows, regions, stats)
                if options['deactivate_missing']:
                    kept_with_listings = self._deactivate_missing(touched, stats)
                if options['dry_run']:
                    raise _DryRun
        except _DryRun:
            self.stdout.write('DRY-RUN: нічого не записано.')
        self._report(stats, kept_with_listings, options['dry_run'])

    # ─── читання ──────────────────────────────────────────────────────────────
    def _read(self, path):
        try:
            with open(path, encoding='utf-8-sig', newline='') as fh:
                reader = csv.DictReader(fh)
                missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
                if missing:
                    raise CommandError(f'У файлі немає колонок: {", ".join(missing)}')
                rows = []
                for n, row in enumerate(reader, start=2):
                    row = {k: (v or '').strip() for k, v in row.items() if k}
                    if not row['katottg'] or not row['name'] or not row['region_name']:
                        raise CommandError(f'Рядок {n}: порожні katottg, name або region_name')
                    limit = Region._meta.get_field('name').max_length
                    if len(row['region_name']) > limit:
                        raise CommandError(f'Рядок {n}: region_name довший за {limit} символів')
                    rows.append(row)
        except FileNotFoundError as exc:
            raise CommandError(f'Файл не знайдено: {path}') from exc
        except UnicodeDecodeError as exc:
            raise CommandError(f'Файл {path} не в кодуванні UTF-8 (збережіть CSV як UTF-8): {exc.reason}') from exc
        codes = Counter(r['katottg'] for r in rows)
        dup = [c for c, k in codes.items() if k > 1]
        if dup:
            raise CommandError(f'Повторені коди katottg: {", ".join(dup[:5])}')
        return rows

    # ─── області ──────────────────────────────────────────────────────────────
    def _import_regions(self, rows, stats):
        by_code = {r.katottg: r for r in Region.objects.exclude(katottg=None)}
        by_name = {normalize_place_name(r.name): r for r in Region.objects.filter(katottg=None)}
        slugs = set(Region.objects.values_list('slug', flat=True))
        result = {}
        for code, name in {(r['region_katottg'], r['region_name']) for r in rows}:
            region = by_code.get(code) or by_name.pop(normalize_place_name(name), None)
            if region is None:
                slug = _slugify_uk(name)
                if slug in slugs:
                    slug = f'{slug}-{code[-6:].lower()}'
                region = Region.objects.create(name=name, slug=slug, katottg=code)
                slugs.add(slug)
                stats['regions_created'] += 1
            elif region.katottg != code:
                region.katottg = code
                region.save(update_fields=['katottg'])
                stats['regions_matched'] += 1
            result[code] = region
        return result

    # ─── пункти ───────────────────────────────────────────────────────────────
    def _import_cities(self, rows, regions, stats):
        by_code = {c.katottg: c for c in City.objects.exclude(katottg=None)}
        legacy = {}
        for c in City.objects.filter(katottg=None):
            legacy.setdefault((c.region_id, c.search_name or normalize_place_name(c.name)), c)
        slugs = set(City.objects.values_list('region_id', 'slug'))
        fields = ['name', 'category', 'district_name', 'hromada_name', 'search_name', 'katottg', 'region']
        to_create, to_update, touched = [], [], set()

        for row in rows:
            region = regions[row['region_katottg']]
            search = normalize_place_name(row['name'])
            data = {
                'name': row['name'][:100], 'category': row.get('category', '')[:16],
                'district_name': row.get('district_name', '')[:100], 'hromada_name': row.get('hromada_name', '')[:150],
                'search_name': search[:100], 'katottg': row['katottg'], 'region': region,
            }
            major = (row.get('is_major') or '').lower() in TRUE
            city = by_code.get(row['katottg']) or legacy.pop((region.pk, search), None)
            if city is None:
                slug = _slugify_uk(row['name'])[:80] or row['katottg'].lower()
                if (region.pk, slug) in slugs:
                    slug = f'{slug}-{row["katottg"][-6:].lower()}'
                slugs.add((region.pk, slug))
                to_create.append(City(slug=slug, is_major=major, **data))
                stats['cities_created'] += 1
                continue
            touched.add(city.pk)
            changed = [f for f in fields if getattr(city, f) != data[f]]
            if major and not city.is_major:
                city.is_major = True
                changed.append('is_major')
            if changed:
                for f in fields:
                    setattr(city, f, data[f])
                to_update.append(city)
                stats['cities_updated'] += 1
            else:
                stats['cities_unchanged'] += 1

        City.objects.bulk_create(to_create, batch_size=1000)
        City.objects.bulk_update(to_update, [*fields, 'is_major'], batch_size=1000)
        touched.update(City.objects.filter(katottg__in=[c.katottg for c in to_create]).values_list('pk', flat=True))
        return touched

    def _deactivate_missing(self, touched, stats):
        missing = City.objects.exclude(pk__in=touched).filter(is_active=True)
        with_listings = list(
            missing.annotate(n=Count('locallisting')).filter(n__gt=0).select_related('region')
        )
        keep = {c.pk for c in with_listings}
        stats['cities_deactivated'] = missing.exclude(pk__in=keep).update(is_active=False)
        return with_listings

    def _report(self, stats, kept, dry_run):
        prefix = 'План' if dry_run else 'Готово'
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}: областей нових {stats["regions_created"]}, зіставлено {stats["regions_matched"]}; '
            f'пунктів нових {stats["cities_created"]}, оновлено {stats["cities_updated"]}, '
            f'без змін {stats["cities_unchanged"]}, деактивовано {stats["cities_deactivated"]}.'
        ))
        for c in kept:
            self.stdout.write(f'  Лишено активним (є оголошення): #{c.pk} {c.name} ({c.region.name})')
