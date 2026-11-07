"""Источник визита first-touch у регистрации и объявления (задача 2.14, Н-37).

Одна функция очистки (core/attribution.py) на заявку, регистрацию и объявление; поля видит только admin.
"""
import json

from django.test import override_settings
from rest_framework.test import APIClient

from core.attribution import clean_attribution
from local_listings.models import LocalListing
from tests.base import CleanCacheTestCase
from tests.factories import (
    auth_client,
    make_admin_role,
    make_broker,
    make_local_listing,
    make_moderator,
    make_region_city,
    make_staff,
    make_user,
)
from users.models import CustomUser
from users.services import anonymize_user

ATTR = {
    'utm': {'source': 'tiktok', 'campaign': 'test', 'evil': 'x', 'medium': 'a b'},
    'referrer': 'https://t.me/x?token=SECRET#a',
    'entry_page_url': '/calculator?email=a@b.cc#top',
}
SOURCE_FIELDS = {'first_touch_utm', 'first_touch_referrer', 'first_touch_entry_url', 'utm', 'referrer',
                 'entry_page_url', 'attribution'}


class CleanAttributionTests(CleanCacheTestCase):
    def test_rules(self):
        data = clean_attribution(ATTR)
        self.assertEqual(data['utm'], {'source': 'tiktok', 'campaign': 'test'})
        self.assertEqual(data['referrer'], 'https://t.me')
        self.assertEqual(data['entry_page_url'], '/calculator')

    def test_garbage_and_dangerous(self):
        for raw in ('x', ['a'], None, 42, {'utm': 'x', 'referrer': 5, 'entry_page_url': ['a']}):
            self.assertEqual(clean_attribution(raw), {'utm': {}, 'referrer': '', 'entry_page_url': '', 'page_url': ''})
        self.assertEqual(clean_attribution({'entry_page_url': '/a\x00b'})['entry_page_url'], '')
        self.assertEqual(clean_attribution({'referrer': 'https://a\x00b.test'})['referrer'], '')
        self.assertEqual(clean_attribution({'referrer': 'https://user:pass@host.test:8443/x'})['referrer'],
                         'https://host.test:8443')
        data = clean_attribution({'referrer': 'javascript:alert(1)', 'entry_page_url': '//evil.test/x',
                                  'utm': {'source': 'y' * 101}})
        self.assertEqual((data['referrer'], data['entry_page_url'], data['utm']), ('', '', {}))
        self.assertEqual(len(clean_attribution({'entry_page_url': '/' + 'p' * 900})['entry_page_url']), 500)

    def test_leads_uses_same_function(self):
        from leads import validators
        self.assertIs(validators.clean_attribution, clean_attribution)


@override_settings(CAPTCHA_PROVIDER='off')
class RegistrationSourceTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        from unittest import mock

        from rest_framework.throttling import SimpleRateThrottle
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'register': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _register(self, email, **extra):
        body = {'email': email, 'password': 'Strong-Pass-9182', 'password2': 'Strong-Pass-9182',
                'agreed_to_terms': True, 'confirmed_age_18': True, **extra}
        return APIClient().post('/api/v1/auth/register/', json.dumps(body), content_type='application/json')

    def test_saved_once_on_registration(self):
        resp = self._register('src@test.com', attribution=ATTR)
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(SOURCE_FIELDS & set(resp.json()))
        user = CustomUser.objects.get(email='src@test.com')
        self.assertEqual(user.first_touch_utm, {'source': 'tiktok', 'campaign': 'test'})
        self.assertEqual((user.first_touch_referrer, user.first_touch_entry_url), ('https://t.me', '/calculator'))

    def test_without_or_garbage_attribution_registers(self):
        for i, extra in enumerate(({}, {'attribution': 'x'}, {'attribution': ['a', 'b']}, {'attribution': None},
                                   {'attribution': {'entry_page_url': '/a\x00b', 'referrer': 'https://a\x00'}},
                                   {'attribution': {'utm': {'source': 'z' * 5000}}})):
            email = f'g{i}@test.com'
            self.assertEqual(self._register(email, **extra).status_code, 201, extra)
            user = CustomUser.objects.get(email=email)
            self.assertEqual((user.first_touch_utm, user.first_touch_referrer), ({}, ''))

    def test_profile_patch_cannot_change_source(self):
        self._register('keep@test.com', attribution=ATTR)
        user = CustomUser.objects.get(email='keep@test.com')
        resp = auth_client(user).patch('/api/v1/auth/profile/', {
            'first_touch_utm': {'source': 'hacked'}, 'first_touch_referrer': 'https://evil.test',
            'attribution': {'utm': {'source': 'hacked'}}}, format='json')
        self.assertEqual(resp.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.first_touch_utm['source'], 'tiktok')
        self.assertEqual(user.first_touch_referrer, 'https://t.me')
        self.assertFalse(SOURCE_FIELDS & set(resp.json()))

    def test_own_export_contains_source(self):
        self._register('exp@test.com', attribution=ATTR)
        user = CustomUser.objects.get(email='exp@test.com')
        data = json.loads(auth_client(user).get('/api/v1/auth/me/export/').content)
        self.assertEqual(data['profile']['first_touch_utm'], {'source': 'tiktok', 'campaign': 'test'})

    def test_anonymize_clears_source(self):
        self._register('anon@test.com', attribution=ATTR)
        user = CustomUser.objects.get(email='anon@test.com')
        listing = make_local_listing(user, utm={'source': 'tiktok'}, referrer='https://t.me', entry_page_url='/x')
        anonymize_user(user)
        user.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual((user.first_touch_utm, user.first_touch_referrer, user.first_touch_entry_url), ({}, '', ''))
        self.assertEqual((listing.referrer, listing.entry_page_url), ('', ''))


class ListingSourceTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user('seller@test.com')
        region, city = make_region_city()
        self.payload = {
            'make': 'Toyota', 'model': 'Camry', 'year': 2020, 'mileage_km': 50000, 'engine_cc': 2500,
            'fuel_type': 'petrol', 'transmission': 'auto', 'body_type': 'sedan', 'condition': 'used',
            'price': '500000', 'currency': 'UAH', 'price_type': 'fixed', 'region': region.pk, 'city': city.pk,
            'description': 'Тест', 'contact_phone': '+380501234567', 'agreed_to_rules': True,
        }

    def test_create_saves_source_and_hides_it(self):
        resp = auth_client(self.owner).post('/api/v1/local/listings/', {**self.payload, 'attribution': ATTR},
                                            format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(SOURCE_FIELDS & set(resp.json()))
        listing = LocalListing.objects.get(pk=resp.json()['id'])
        self.assertEqual((listing.utm, listing.referrer, listing.entry_page_url),
                         ({'source': 'tiktok', 'campaign': 'test'}, 'https://t.me', '/calculator'))

    def test_garbage_attribution_does_not_block(self):
        for garbage in ('x', None, {'entry_page_url': '/a\x00b'}):
            resp = auth_client(self.owner).post('/api/v1/local/listings/', {**self.payload, 'attribution': garbage},
                                                format='json')
            self.assertEqual(resp.status_code, 201, garbage)
            self.assertEqual(LocalListing.objects.get(pk=resp.json()['id']).entry_page_url, '')

    def test_edit_does_not_change_source(self):
        listing = make_local_listing(self.owner, utm={'source': 'tiktok'}, referrer='https://t.me')
        resp = auth_client(self.owner).patch(f'/api/v1/local/listings/{listing.pk}/', {
            'description': 'Нове', 'utm': {'source': 'x'}, 'referrer': 'https://evil.test',
            'attribution': {'utm': {'source': 'x'}}}, format='json')
        self.assertEqual(resp.status_code, 200)
        listing.refresh_from_db()
        self.assertEqual((listing.utm, listing.referrer), ({'source': 'tiktok'}, 'https://t.me'))

    def test_public_and_owner_responses_have_no_source(self):
        listing = make_local_listing(self.owner, utm={'source': 'tiktok'}, referrer='https://t.me',
                                     entry_page_url='/calculator')
        anon = APIClient()
        responses = [
            anon.get('/api/v1/local/listings/'),
            anon.get(f'/api/v1/local/listings/{listing.pk}/'),
            auth_client(self.owner).get(f'/api/v1/local/listings/{listing.pk}/'),
            auth_client(self.owner).get('/api/v1/local/my-listings/'),
            auth_client(self.owner).get('/api/v1/auth/profile/'),
        ]
        for resp in responses:
            self.assertEqual(resp.status_code, 200, resp.wsgi_request.path)
            body = resp.content.decode()
            for marker in ('tiktok', 't.me', 'first_touch', '"utm"', '"referrer"', 'entry_page_url'):
                self.assertNotIn(marker, body, resp.wsgi_request.path)


class AdminSourceVisibilityTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        self.target = make_user('target@test.com', first_touch_utm={'source': 'tiktokADM'})
        self.listing = make_local_listing(self.target, status=LocalListing.Status.PENDING,
                                          utm={'source': 'tiktokLST'}, referrer='https://ref.example')

    def _get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)

    def _admin_in_group(self):
        from django.contrib.auth.models import Group
        user = make_admin_role()
        user.groups.add(Group.objects.get(name='Адміністратори'))
        return user

    def test_admin_sees_readonly_source(self):
        # Пользователей в админке видит только суперпользователь; объявления - и admin-роль из группы.
        root = make_staff(superuser=True)
        resp = self._get(root, f'/admin/users/customuser/{self.target.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'tiktokADM')
        self.assertNotContains(resp, 'name="first_touch_utm"')  # только чтение
        for user in (root, self._admin_in_group()):
            resp = self._get(user, f'/admin/local_listings/locallisting/{self.listing.pk}/change/')
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, 'tiktokLST')
            self.assertNotContains(resp, 'name="referrer"')

    def test_moderator_and_broker_do_not_see_source(self):
        user_url = f'/admin/users/customuser/{self.target.pk}/change/'
        listing_url = f'/admin/local_listings/locallisting/{self.listing.pk}/change/'
        queue_url = f'/admin/local_listings/pendinglocallistingproxy/{self.listing.pk}/change/'
        moderator, broker = make_moderator(), make_broker()
        for user, url in ((moderator, user_url), (broker, user_url), (broker, listing_url), (broker, queue_url)):
            self.assertEqual(self._get(user, url).status_code, 403, (user.email, url))
        for url in (listing_url, queue_url):  # модератору страницы открыты, но без источника
            resp = self._get(moderator, url)
            self.assertEqual(resp.status_code, 200, url)
            body = resp.content.decode()
            for marker in ('tiktokLST', 'ref.example', 'Джерело візиту'):
                self.assertNotIn(marker, body, url)

    def test_admin_role_without_permission_does_not_see(self):
        from django.contrib.auth.models import Group
        admin = self._admin_in_group()
        group = Group.objects.get(name='Адміністратори')
        group.permissions.remove(*group.permissions.filter(codename='view_attribution'))
        resp = self._get(admin, f'/admin/local_listings/locallisting/{self.listing.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'tiktokLST')

    def test_staff_with_user_view_perm_but_no_attribution_perm(self):
        from django.contrib.auth.models import Permission
        staff = make_staff('viewer@test.com')
        staff.user_permissions.add(Permission.objects.get(codename='view_customuser'))
        resp = self._get(staff, f'/admin/users/customuser/{self.target.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'tiktokADM')
        self.assertNotContains(resp, 'Джерело візиту')

    def test_moderator_queue_page_opens_without_source(self):
        resp = self._get(make_moderator(), f'/admin/local_listings/pendinglocallistingproxy/{self.listing.pk}/change/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'tiktokLST')

    def test_admin_group_has_permission(self):
        from django.contrib.auth.models import Group
        group = Group.objects.get(name='Адміністратори')
        self.assertTrue(group.permissions.filter(codename='view_attribution').exists())
        self.assertFalse(Group.objects.get(name='Модератори').permissions.filter(codename='view_attribution').exists())
