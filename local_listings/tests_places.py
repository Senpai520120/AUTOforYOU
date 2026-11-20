"""Задача 8.2: КАТОТТГ-поля, нормализация, импорт, поиск населённого пункта, проверка is_active.

Данные - синтетическая фикстура local_listings/fixtures/katottg_sample.csv (реальный реестр в репо не кладётся).
"""
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from tests.factories import auth_client, make_local_listing, make_staff, make_user

from .models import City, LocalListing, Region
from .places import normalize_place_name

SAMPLE = Path(__file__).parent / 'fixtures' / 'katottg_sample.csv'


def run_import(*extra):
    out = StringIO()
    call_command('import_katottg', '--file', str(SAMPLE), *extra, stdout=out)
    return out.getvalue()


class TestNormalize(APITestCase):
    def test_apostrophes_and_case(self):
        variants = ["Кам'янське", 'Кам’янське', 'КАМ`ЯНСЬКЕ', 'Камʼянське']
        self.assertEqual(len({normalize_place_name(v) for v in variants}), 1)

    def test_spaces_and_dashes(self):
        self.assertEqual(normalize_place_name('  Могилів – Подільський  '), 'могилів-подільський')
        self.assertEqual(normalize_place_name('Нова   Іванівка'), 'нова іванівка')


class TestImport(APITestCase):
    def setUp(self):
        self.vin_region = Region.objects.create(name='Вінницька область', slug='vinnytska')
        # город из seed_regions до импорта: без кода
        self.legacy = City.objects.create(region=self.vin_region, name='Вінниця', slug='vinnytsia', is_major=True)
        self.listing = make_local_listing(make_user(), region=self.vin_region, city=self.legacy)

    def test_creates_and_matches_legacy_keeping_id(self):
        run_import()
        self.legacy.refresh_from_db()
        self.assertEqual(self.legacy.katottg, 'UA05000000000010001')
        self.assertEqual(self.legacy.district_name, 'Вінницький')
        self.assertEqual(City.objects.filter(name='Вінниця').count(), 1)
        self.vin_region.refresh_from_db()
        self.assertEqual(self.vin_region.katottg, 'UA05000000000000001')
        self.assertTrue(Region.objects.filter(name='Автономна Республіка Крим').exists())
        self.assertEqual(City.objects.exclude(katottg=None).count(), 12)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.city_id, self.legacy.pk)

    def test_idempotent(self):
        run_import()
        before = list(City.objects.order_by('pk').values_list('pk', 'slug', 'katottg'))
        with CaptureQueriesContext(connection) as ctx:
            out = run_import()
        # константа (чтения справочника, транзакция), а не запрос на каждую из 12 строк файла
        self.assertLessEqual(len(ctx), 20)
        self.assertEqual(list(City.objects.order_by('pk').values_list('pk', 'slug', 'katottg')), before)
        self.assertIn('пунктів нових 0', out)

    def test_same_name_villages_get_distinct_slugs(self):
        run_import()
        slugs = list(City.objects.filter(region=self.vin_region, name='Іванівка').values_list('slug', flat=True))
        self.assertEqual(len(slugs), 2)
        self.assertEqual(len(set(slugs)), 2)

    def test_dry_run_writes_nothing(self):
        cities, regions = City.objects.count(), Region.objects.count()
        out = run_import('--dry-run')
        self.assertIn('DRY-RUN', out)
        self.assertEqual(City.objects.count(), cities)
        self.assertEqual(Region.objects.count(), regions)
        self.legacy.refresh_from_db()
        self.assertIsNone(self.legacy.katottg)

    def test_deactivate_missing_keeps_city_with_listing(self):
        orphan = City.objects.create(region=self.vin_region, name='Зникле', slug='znykle')
        used = City.objects.create(region=self.vin_region, name='Стара назва', slug='stara')
        make_local_listing(make_user(), region=self.vin_region, city=used)
        out = run_import('--deactivate-missing')
        orphan.refresh_from_db()
        used.refresh_from_db()
        self.assertFalse(orphan.is_active)
        self.assertTrue(used.is_active)
        self.assertIn('Стара назва', out)

    def test_seed_regions_after_import_makes_no_duplicates(self):
        run_import()
        call_command('seed_regions', '--force', stdout=StringIO())
        self.assertEqual(City.objects.filter(region=self.vin_region, search_name='вінниця').count(), 1)
        self.assertEqual(Region.objects.filter(name='Вінницька область').count(), 1)
        jm = City.objects.get(katottg='UA05000000000010002')
        self.assertTrue(jm.is_major)

    def test_missing_file_is_clear_error(self):
        from django.core.management.base import CommandError
        with self.assertRaisesMessage(CommandError, 'Файл не знайдено'):
            call_command('import_katottg', '--file', 'nope.csv', stdout=StringIO())

    def _csv(self, content, encoding):
        import tempfile
        fh = tempfile.NamedTemporaryFile(suffix='.csv', delete=False)
        fh.write(content.encode(encoding))
        fh.close()
        self.addCleanup(Path(fh.name).unlink)
        return fh.name

    def test_cp1251_file_is_clear_error(self):
        from django.core.management.base import CommandError
        header = 'katottg,name,category,region_katottg,region_name\n'
        path = self._csv(header + 'UA01,Вінниця,M,UA00,Вінницька область\n', 'cp1251')
        with self.assertRaisesMessage(CommandError, 'не в кодуванні UTF-8'):
            call_command('import_katottg', '--file', path, stdout=StringIO())

    def test_too_long_region_name_is_error_with_line(self):
        from django.core.management.base import CommandError
        header = 'katottg,name,category,region_katottg,region_name\n'
        path = self._csv(header + f'UA01,Вінниця,M,UA00,{"О" * 101}\n', 'utf-8')
        with self.assertRaisesMessage(CommandError, 'Рядок 2: region_name довший за 100'):
            call_command('import_katottg', '--file', path, stdout=StringIO())
        self.assertFalse(Region.objects.filter(katottg='UA00').exists())

    def test_entrypoint_runs_import_only_with_file(self):
        script = (settings.BASE_DIR / 'docker' / 'entrypoint.sh').read_text(encoding='utf-8')
        self.assertIn('if [ -n "${KATOTTG_FILE:-}" ]; then', script)
        self.assertIn('run_seed import_katottg', script)


@override_settings(CITY_SEARCH_MIN_CHARS=2, CITY_SEARCH_LIMIT=20)
class TestCitySearch(APITestCase):
    URL = '/api/v1/local/cities/'

    @classmethod
    def setUpTestData(cls):
        call_command('import_katottg', '--file', str(SAMPLE), stdout=StringIO())

    def setUp(self):
        cache.clear()

    def search(self, **params):
        return APIClient().get(self.URL, params)

    def test_short_query_is_empty(self):
        resp = self.search(q='і')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_apostrophe_variants_find_same(self):
        a = [c['id'] for c in self.search(q="Кам'янське").json()]
        b = [c['id'] for c in self.search(q='кам’ян').json()]
        self.assertEqual(sorted(a), sorted(b))
        self.assertEqual(len(a), 2)

    def test_prefix_before_substring_and_major_first(self):
        names = [c['label'] for c in self.search(q='іванів').json()]
        self.assertEqual(len(names), 4)  # три «Іванівка» и «Нова Іванівка» - все совпадения по началу слова
        kam = self.search(q='кам').json()
        self.assertEqual(kam[0]['region_name'], 'Дніпропетровська область')  # крупный город выше села

    def test_word_start_ranks_above_inner_substring(self):
        City.objects.create(region=Region.objects.get(name='Вінницька область'), name='Заіванівське', slug='zaiv')
        names = [c['name'] for c in self.search(q='іванів').json()]
        self.assertEqual(names[-1], 'Заіванівське')

    @override_settings(CITY_SEARCH_LIMIT=2)
    def test_limit_from_settings(self):
        self.assertEqual(len(self.search(q='іванів', limit=50).json()), 2)

    def test_region_filter(self):
        dnipro = Region.objects.get(name='Дніпропетровська область')
        rows = self.search(q='іванів', region=dnipro.pk).json()
        self.assertEqual([r['region'] for r in rows], [dnipro.pk])

    def test_inactive_not_returned(self):
        City.objects.filter(name='Ялта').update(is_active=False)
        self.assertEqual(self.search(q='ялта').json(), [])

    def test_no_service_fields(self):
        row = self.search(q='вінниц').json()[0]
        self.assertEqual(set(row), {'id', 'name', 'region', 'region_name', 'district_name', 'label'})
        self.assertEqual(row['label'], 'Вінниця · Вінницький · Вінницька область')

    def test_bad_region_param_is_400(self):
        self.assertEqual(self.search(q='вінниц', region='x').status_code, 400)

    def test_throttle(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, 'city_search': '2/min'}
        with mock.patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            for _ in range(2):
                self.assertEqual(self.search(q='вінниц').status_code, 200)
            self.assertEqual(self.search(q='вінниц').status_code, 429)

    def test_region_cities_quick_list_and_search(self):
        vin = Region.objects.get(name='Вінницька область')
        quick = APIClient().get(f'/api/v1/local/regions/{vin.pk}/cities/').json()
        self.assertEqual(sorted(c['name'] for c in quick), ['Вінниця', 'Жмеринка'])
        found = APIClient().get(f'/api/v1/local/regions/{vin.pk}/cities/', {'q': 'ворон'}).json()
        self.assertEqual([c['name'] for c in found], ['Вороновиця'])

    def test_config_exposes_limits(self):
        data = APIClient().get('/api/v1/local/config/').json()
        self.assertEqual(data['city_search_min_chars'], 2)
        self.assertEqual(data['city_search_limit'], 20)


class TestListingCityActive(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.listing = make_local_listing(self.user)
        self.region = self.listing.region

    def _payload(self, city):
        return {
            'make': 'Skoda', 'model': 'Fabia', 'year': 2015, 'mileage_km': 100000, 'price': '5000',
            'currency': 'USD', 'fuel_type': 'petrol', 'transmission': 'manual', 'body_type': 'hatchback',
            'condition': 'used', 'region': self.region.pk, 'city': city.pk, 'description': 'Тест',
            'contact_phone': '+380501234567', 'agreed_to_rules': True, 'legal_confirmed': True,
        }

    def test_create_with_inactive_city_is_400(self):
        off = City.objects.create(region=self.region, name='Вимкнене', slug='off', is_active=False)
        resp = auth_client(make_user()).post('/api/v1/local/listings/', self._payload(off), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['city'], ['Населений пункт недоступний для вибору.'])

    def test_city_from_other_region_is_400(self):
        other = Region.objects.create(name='Інша область', slug='insha')
        foreign = City.objects.create(region=other, name='Чуже', slug='chuzhe')
        resp = auth_client(make_user()).post('/api/v1/local/listings/', self._payload(foreign), format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('city', resp.json())

    def test_old_listing_with_deactivated_city_still_opens(self):
        City.objects.filter(pk=self.listing.city_id).update(is_active=False)
        resp = APIClient().get(f'/api/v1/local/listings/{self.listing.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['city'], self.listing.city_id)

    def test_owner_edit_keeps_deactivated_city(self):
        City.objects.filter(pk=self.listing.city_id).update(is_active=False)
        LocalListing.objects.filter(pk=self.listing.pk).update(status=LocalListing.Status.ACTIVE)
        resp = auth_client(self.user).patch(f'/api/v1/local/listings/{self.listing.pk}/',
                                            {'city': self.listing.city_id, 'mileage_km': 1}, format='json')
        self.assertEqual(resp.status_code, 200)


class TestCityAdmin(APITestCase):
    def test_search_by_katottg(self):
        call_command('import_katottg', '--file', str(SAMPLE), stdout=StringIO())
        client = Client()
        client.force_login(make_staff(superuser=True))
        resp = client.get('/admin/local_listings/city/', {'q': 'UA12000000000010002'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Кам’янське')

    def test_listing_admin_does_not_load_all_cities(self):
        client = Client()
        client.force_login(make_staff(superuser=True))
        listing = make_local_listing(make_user())
        url = f'/admin/local_listings/locallisting/{listing.pk}/change/'
        first = client.get(url)
        region = listing.region
        City.objects.bulk_create([City(region=region, name=f'Село {i}', slug=f's{i}') for i in range(300)])
        resp = client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'Село 299')
