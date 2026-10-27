from django.core.cache import cache
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from tests.base import CleanCacheTestCase
from tests.factories import make_admin_role, make_moderator, make_staff, make_user

from .models import DRAFT_MARKER_ERROR, FaqItem, ImportStep

HOW = '/api/v1/content/how-it-works/'
FAQ = '/api/v1/content/faq/'


class DraftMigrationTests(TestCase):
    def test_drafts_created_inactive_with_marker(self):
        self.assertGreaterEqual(ImportStep.objects.count(), 6)
        self.assertGreaterEqual(FaqItem.objects.count(), 6)
        self.assertFalse(ImportStep.objects.filter(is_active=True).exists())
        self.assertFalse(FaqItem.objects.filter(is_active=True).exists())
        self.assertTrue(ImportStep.objects.filter(duration__contains='[ПЕРЕВІРИТИ').exists())


class HowItWorksApiTests(CleanCacheTestCase):
    def test_drafts_only_means_not_published(self):
        r = APIClient().get(HOW)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'published': False, 'steps': [], 'faq': []})

    def test_active_only_in_order_without_service_fields(self):
        ImportStep.objects.all().delete()
        FaqItem.objects.all().delete()
        ImportStep.objects.create(title='Б', order=2, is_active=True)
        ImportStep.objects.create(title='А', order=1, is_active=True, duration='2 тижні')
        ImportStep.objects.create(title='Прихований', order=0, is_active=False)
        FaqItem.objects.create(question='Q2', answer='A2', order=2, is_active=True)
        FaqItem.objects.create(question='Q1', answer='A1', order=1, is_active=True)
        FaqItem.objects.create(question='Q0', answer='A0', order=0, is_active=False)
        data = APIClient().get(HOW).json()
        self.assertTrue(data['published'])
        self.assertEqual([s['title'] for s in data['steps']], ['А', 'Б'])
        self.assertEqual([f['question'] for f in data['faq']], ['Q1', 'Q2'])
        self.assertEqual(set(data['steps'][0]), {'title', 'description', 'duration'})
        self.assertEqual(set(data['faq'][0]), {'question', 'answer'})


class MarkerLeakTests(CleanCacheTestCase):
    """Запис, увімкнений в обхід clean() (update/save), з позначкою не потрапляє в API."""

    def test_activated_via_update_does_not_leak(self):
        ImportStep.objects.update(is_active=True)
        FaqItem.objects.update(is_active=True, show_on_calculator=True)
        self.assertEqual(APIClient().get(HOW).json(), {'published': False, 'steps': [], 'faq': []})
        self.assertEqual(APIClient().get(FAQ, {'place': 'calculator'}).json(), {'faq': []})

    def test_clean_record_still_published_next_to_marked_one(self):
        ImportStep.objects.update(is_active=True)
        ImportStep.objects.create(title='Чистий', order=0, is_active=True)
        data = APIClient().get(HOW).json()
        self.assertEqual([s['title'] for s in data['steps']], ['Чистий'])


class FaqPlaceTests(CleanCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        FaqItem.objects.all().delete()
        FaqItem.objects.create(question='Є', answer='a', is_active=True, show_on_calculator=True)
        FaqItem.objects.create(question='Немає', answer='a', is_active=True, show_on_calculator=False)
        FaqItem.objects.create(question='Чернетка', answer='a', is_active=False, show_on_calculator=True)

    def test_calculator_place_filters_by_flag(self):
        r = APIClient().get(FAQ, {'place': 'calculator'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([f['question'] for f in r.json()['faq']], ['Є'])

    def test_unknown_place_gives_empty_list(self):
        r = APIClient().get(FAQ, {'place': 'zzz'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'faq': []})

    def test_missing_place_gives_empty_list(self):
        r = APIClient().get(FAQ)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'faq': []})


class AdminTests(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(make_staff(superuser=True))

    def _post_step(self, obj, **over):
        data = {'title': obj.title, 'description': obj.description, 'duration': obj.duration,
                'order': obj.order, 'is_active': 'on'}
        data.update(over)
        return self.client.post(reverse('admin:content_importstep_change', args=[obj.pk]), data)

    def test_cannot_activate_with_marker(self):
        step = ImportStep.objects.first()
        r = self._post_step(step)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, DRAFT_MARKER_ERROR)
        step.refresh_from_db()
        self.assertFalse(step.is_active)

    def test_activate_after_marker_removed_updates_api(self):
        self.assertFalse(APIClient().get(HOW).json()['published'])  # прогрів кешу
        step = ImportStep.objects.first()
        r = self._post_step(step, duration='2 тижні', description='Опис без позначки')
        self.assertEqual(r.status_code, 302)
        data = APIClient().get(HOW).json()
        self.assertTrue(data['published'])
        self.assertEqual(data['steps'][0]['duration'], '2 тижні')

    def test_marker_check_is_case_insensitive_for_faq(self):
        item = FaqItem.objects.first()
        item.is_active = True
        item.answer = 'текст [перевірити з брокером]'
        with self.assertRaisesMessage(ValidationError, DRAFT_MARKER_ERROR):
            item.full_clean()

    def test_inactive_draft_with_marker_is_valid(self):
        FaqItem.objects.first().full_clean()

    def test_delete_clears_cache(self):
        ImportStep.objects.all().delete()
        ImportStep.objects.create(title='Чистий', is_active=True)
        cache.clear()
        self.assertTrue(APIClient().get(HOW).json()['published'])
        ImportStep.objects.all().delete()
        self.assertFalse(APIClient().get(HOW).json()['published'])

    def test_admin_role_allowed(self):
        self.client.force_login(make_admin_role())
        r = self.client.get(reverse('admin:content_importstep_changelist'))
        self.assertEqual(r.status_code, 200)

    def test_moderator_has_no_access(self):
        self.client.force_login(make_moderator())
        self.assertEqual(self.client.get(reverse('admin:content_importstep_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:content_faqitem_changelist')).status_code, 403)

    def test_buyer_has_no_access(self):
        self.client.force_login(make_user())
        self.assertEqual(self.client.get(reverse('admin:content_importstep_changelist')).status_code, 302)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('admin:content_importstep_changelist')).status_code, 302)

    def test_staff_with_model_permissions_but_no_admin_role_is_denied(self):
        user = make_staff()  # is_staff, role=buyer, не superuser
        user.user_permissions.set(Permission.objects.filter(content_type__app_label='content'))
        self.client.force_login(user)
        for name in ('content_importstep_changelist', 'content_faqitem_changelist'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f'admin:{name}')).status_code, 403)

    def test_list_editable_cannot_activate_record_with_marker(self):
        item = FaqItem.objects.first()
        r = self.client.post(reverse('admin:content_faqitem_changelist'), {
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1', 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-id': item.pk, 'form-0-order': item.order, 'form-0-is_active': 'on',
            'form-0-show_on_calculator': '', '_save': 'Save',
        })
        self.assertEqual(r.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(item.is_active)
