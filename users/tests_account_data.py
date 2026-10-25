"""Профиль, выгрузка данных и удаление аккаунта (задача 1.8, 23-D29, 23-D30, 23-D36)."""
import json
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from deals.models import Deal, Review
from deals.services import confirm_deal, propose_deal
from favorites.models import Favorite
from leads.models import Lead
from leads.services import create_lead
from local_listings.models import LocalListing, LocalListingImage
from messaging.models import Message
from messaging.services import get_or_create_conversation, send_message_to_conversation
from notifications.models import Notification
from payments.models import Payment
from pricing.models import Calculation
from reports.models import Report
from saved_searches.models import SavedSearch
from shipments.models import Shipment
from site_settings.models import SiteSettings
from telegram_bot.models import TelegramLinkToken
from tests.base import CleanCacheTestCase
from tests.factories import TEST_PASSWORD, make_local_listing, make_staff, make_user
from tests.test_uploads import image_bytes

from .display import DELETED_NAME, public_display_name
from .jwt import VersionedRefreshToken
from .models import ConsentRecord, DealerApplication, TrustedShop
from .services import anonymize_user, schedule_account_deletion
from .tasks import anonymize_due_accounts

User = get_user_model()

PROFILE_URL = '/api/v1/auth/profile/'
CANCEL_URL = '/api/v1/auth/profile/cancel-deletion/'
EXPORT_URL = '/api/v1/auth/me/export/'
REFRESH_URL = '/api/v1/auth/token/refresh/'
TOKEN_URL = '/api/v1/auth/token/'
REGISTER_URL = '/api/v1/auth/register/'


def _session(user):
    refresh = VersionedRefreshToken.for_user(user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client, str(refresh)


class AccountTestCase(CleanCacheTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'password_reset': '1000/hour'})
        patcher.start()
        self.addCleanup(patcher.stop)
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)


# ─── Профиль (PATCH, телефон) ────────────────────────────────────────────────

class ProfileEditTests(AccountTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('profile@test.com')
        self.client, _ = _session(self.user)

    def test_patch_name_and_phone_saved(self):
        resp = self.client.patch(PROFILE_URL, {'first_name': '  Олена ', 'last_name': 'Коваль',
                                               'phone': '+380501234567'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name, self.user.phone),
                         ('Олена', 'Коваль', '+380501234567'))

    def test_invalid_phone_is_400_and_not_saved(self):
        for phone in ('abc', '0501234567', '+38050123456', '+3805012345678'):
            resp = self.client.patch(PROFILE_URL, {'phone': phone}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, phone)
            self.assertIn('phone', resp.json())
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '')

    def test_empty_phone_allowed(self):
        self.user.phone = '+380501234567'
        self.user.save()
        resp = self.client.patch(PROFILE_URL, {'phone': ''}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '')

    def test_too_long_name_is_400(self):
        resp = self.client.patch(PROFILE_URL, {'first_name': 'Я' * 151}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ─── Запрос удаления и отмена ────────────────────────────────────────────────

@override_settings(SITE_URL='https://site.test', CAPTCHA_PROVIDER='off')
class AccountDeletionRequestTests(AccountTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user('del@test.com', first_name='Олег', phone='+380501112233')
        self.client, self.refresh = _session(self.user)
        self.active = make_local_listing(self.user)
        self.pending = make_local_listing(self.user, status=LocalListing.Status.PENDING)
        self.draft = make_local_listing(self.user, status=LocalListing.Status.DRAFT)

    def _delete(self, payload, client=None):
        return (client or self.client).delete(PROFILE_URL, payload, format='json')

    def test_anonymous_is_401(self):
        self.assertEqual(self._delete({'password': TEST_PASSWORD}, APIClient()).status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_missing_or_wrong_password_is_400_and_nothing_changes(self):
        for payload in ({}, {'password': ''}, {'password': 'wrong-pass-1'}):
            resp = self._delete(payload)
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, payload)
            self.assertIn('password', resp.json())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_scheduled_at)
        self.assertEqual(self.user.session_version, 0)
        self.active.refresh_from_db()
        self.assertEqual(self.active.status, LocalListing.Status.ACTIVE)

    def test_success_schedules_hides_listings_revokes_sessions_keeps_data(self):
        with self.captureOnCommitCallbacks(execute=True):
            resp = self._delete({'password': TEST_PASSWORD})
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deletion_scheduled_at)
        expected = self.user.deletion_scheduled_at + timedelta(days=14)
        self.assertEqual(resp.json()['deletion_scheduled_for'], expected.isoformat())
        statuses = dict(LocalListing.objects.filter(owner=self.user).values_list('pk', 'status'))
        self.assertEqual(statuses, {self.active.pk: 'hidden', self.pending.pk: 'hidden', self.draft.pk: 'draft'})
        self.assertEqual(APIClient().post(REFRESH_URL, {'refresh': self.refresh}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(PROFILE_URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp.cookies['access']['max-age'], 0)
        # данные пока на месте: это только период отмены
        self.assertEqual((self.user.email, self.user.phone, self.user.is_active), ('del@test.com', '+380501112233', True))
        self.assertIsNone(self.user.deleted_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['del@test.com'])
        self.assertIn('https://site.test/me/data', mail.outbox[0].body)
        self.assertIn(timezone.localtime(expected).strftime('%d.%m.%Y'), mail.outbox[0].body)

    def test_grace_days_come_from_site_settings(self):
        s = SiteSettings.load()
        s.account_deletion_grace_days = 30
        s.save()
        resp = self._delete({'password': TEST_PASSWORD})
        self.user.refresh_from_db()
        self.assertEqual(resp.json()['deletion_scheduled_for'],
                         (self.user.deletion_scheduled_at + timedelta(days=30)).isoformat())

    def test_repeat_request_keeps_original_date(self):
        schedule_account_deletion(self.user)
        first = self.user.deletion_scheduled_at
        client, _ = _session(self.user)
        resp = self._delete({'password': TEST_PASSWORD}, client)
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.user.refresh_from_db()
        self.assertEqual(self.user.deletion_scheduled_at, first)

    def test_superuser_cannot_self_delete(self):
        admin = make_staff('root@test.com', superuser=True)
        client, _ = _session(admin)
        resp = self._delete({'password': TEST_PASSWORD}, client)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        admin.refresh_from_db()
        self.assertIsNone(admin.deletion_scheduled_at)

    def test_login_in_grace_period_works_and_profile_shows_date(self):
        schedule_account_deletion(self.user)
        resp = APIClient().post(TOKEN_URL, {'email': 'del@test.com', 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        client, _ = _session(self.user)
        data = client.get(PROFILE_URL).json()
        self.assertEqual(data['deletion_scheduled_for'],
                         (self.user.deletion_scheduled_at + timedelta(days=14)).isoformat())

    def test_cancel_resets_mark_listings_stay_hidden(self):
        schedule_account_deletion(self.user)
        client, _ = _session(self.user)
        resp = client.post(CANCEL_URL, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.json()['deletion_scheduled_for'])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_scheduled_at)
        self.active.refresh_from_db()
        self.assertEqual(self.active.status, LocalListing.Status.HIDDEN)

    def test_cancel_anonymous_is_401(self):
        self.assertEqual(APIClient().post(CANCEL_URL, format='json').status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cancel_by_other_user_does_not_touch_owner(self):
        schedule_account_deletion(self.user)
        other_client, _ = _session(make_user('other@test.com'))
        self.assertEqual(other_client.post(CANCEL_URL, format='json').status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deletion_scheduled_at)

    def test_delete_throttled_by_password_reset_scope(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'password_reset': '2/min'}):
            for _ in range(2):
                self._delete({'password': 'wrong-pass-1'})
            self.assertEqual(self._delete({'password': TEST_PASSWORD}).status_code,
                             status.HTTP_429_TOO_MANY_REQUESTS)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deletion_scheduled_at)


# ─── Обезличивание (задача anonymize_due_accounts) ────────────────────────────

@override_settings(SITE_URL='https://site.test', CAPTCHA_PROVIDER='off')
class AnonymizeTests(AccountTestCase):
    def setUp(self):
        super().setUp()
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.account_deletion_grace_days = 3
        s.save()
        self.user = make_user('gone@test.com', first_name='Марія', last_name='Шевченко',
                              phone='+380671234567', telegram_id=555000111)
        self.other = make_user('buyer@test.com', first_name='Петро', last_name='Іванов')

        self.listing = make_local_listing(self.user, contact_phone='+380671234567', description='Дзвоніть')
        self.image = LocalListingImage.objects.create(listing=self.listing)
        self.image.image.save('car.jpg', ContentFile(image_bytes()), save=True)
        self.image_name = self.image.image.name

        conv, _, _ = get_or_create_conversation(self.other, 'local', self.listing.pk, 'Ще продається?')
        send_message_to_conversation(self.user, conv, 'Так, приїжджайте')
        self.conv = conv
        self.deal = propose_deal(self.listing, self.user, self.other.pk)
        confirm_deal(self.deal, self.other)
        self.review = Review.objects.create(deal=self.deal, author=self.other, target=self.user, rating=5)
        self.report = Report.objects.create(reporter=self.user, reported_user=self.other, reason='spam')
        self.payment = Payment.objects.create(user=self.user, order_id='ORD-1', amount='10.00', currency='UAH')

        TrustedShop.objects.create(owner=self.user, name='СТО')
        SavedSearch.objects.create(user=self.user, name='Пошук', filters={})
        Favorite.objects.create(user=self.user, local_listing=make_local_listing(self.other))
        Notification.objects.create(user=self.user, type='new_message', title='Привіт')
        TelegramLinkToken.objects.create(user=self.user, expires_at=timezone.now() + timedelta(hours=1))
        DealerApplication.objects.create(user=self.user, company_name='ТОВ', full_name='Марія Шевченко',
                                         contact_phone='+380671234567')
        self.calc = Calculation.objects.create(user=self.user, inputs_snapshot={}, rates_snapshot={},
                                               breakdown={}, total_usd='1.00', total_uah='41.00')
        self.shipment = Shipment.objects.create(container_no='MSCU1112223')
        self.shipment.watchers.add(self.user)
        ConsentRecord.objects.create(user=self.user, document='terms', method='register')
        self.lead = create_lead(user=self.user, data={
            'name': 'Марія', 'phone': '0671234567', 'email': 'gone@test.com', 'contact_method': 'telegram',
            'contact_handle': '@maria', 'comment': 'Мій номер 0671234567', 'source': 'landing',
            'utm': {'utm_source': 'tg'}})
        self.lead_public_id = Lead.objects.get(pk=self.lead.pk).public_id
        self.lead_consents = ConsentRecord.objects.filter(lead=self.lead).count()
        self.old_refresh = str(VersionedRefreshToken.for_user(self.user))

    def _schedule(self, days_ago):
        User.objects.filter(pk=self.user.pk).update(deletion_scheduled_at=timezone.now() - timedelta(days=days_ago))

    def _run_task(self):
        with self.captureOnCommitCallbacks(execute=True):
            return anonymize_due_accounts()

    def test_before_grace_end_nothing_changes(self):
        self._schedule(days_ago=2)
        self.assertEqual(self._run_task(), 0)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deleted_at)
        self.assertEqual(self.user.email, 'gone@test.com')

    def test_not_scheduled_user_untouched(self):
        self.assertEqual(self._run_task(), 0)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deleted_at)

    def test_after_grace_profile_is_wiped(self):
        self._schedule(days_ago=4)
        self.assertEqual(self._run_task(), 1)
        self.user.refresh_from_db()
        self.assertRegex(self.user.email, r'^deleted-[0-9a-f]{32}@deleted\.invalid$')
        self.assertEqual((self.user.first_name, self.user.last_name, self.user.phone), ('', '', ''))
        self.assertIsNone(self.user.telegram_id)
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertIsNotNone(self.user.deleted_at)
        self.assertEqual(public_display_name(self.user), DELETED_NAME)
        # сессии отозваны и сами по себе, не только через is_active=False
        self.assertEqual(self.user.session_version, 1)
        self.assertTrue(BlacklistedToken.objects.filter(token__user=self.user).exists())

    def test_after_grace_login_fails_and_email_phone_free_for_registration(self):
        self._schedule(days_ago=4)
        self._run_task()
        resp = APIClient().post(TOKEN_URL, {'email': 'gone@test.com', 'password': TEST_PASSWORD}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(APIClient().post(REFRESH_URL, {'refresh': self.old_refresh}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)
        resp = APIClient().post(REGISTER_URL, {
            'email': 'gone@test.com', 'password': 'Strong-Pass-9182', 'password2': 'Strong-Pass-9182',
            'first_name': 'Нова', 'phone': '+380671234567', 'agreed_to_terms': True, 'confirmed_age_18': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email='gone@test.com', phone='+380671234567').exclude(
            pk=self.user.pk).exists())

    def test_second_party_keeps_deal_messages_and_sees_deleted_name(self):
        self._schedule(days_ago=4)
        self._run_task()
        self.assertTrue(Deal.objects.filter(pk=self.deal.pk).exists())
        self.assertTrue(Review.objects.filter(pk=self.review.pk).exists())
        self.assertTrue(Report.objects.filter(pk=self.report.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=self.payment.pk, user=self.user).exists())
        self.assertEqual(Message.objects.filter(conversation=self.conv).count(), 2)
        client, _ = _session(self.other)
        rows = client.get('/api/v1/deals/').json()
        self.assertEqual(rows[0]['seller']['display_name'], DELETED_NAME)
        detail = client.get(f'/api/v1/messages/conversations/{self.conv.pk}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        body = detail.content.decode()
        self.assertIn(DELETED_NAME, body)
        self.assertNotIn('Марія', body)

    def test_listings_archived_without_phone_and_photos(self):
        self._schedule(days_ago=4)
        self._run_task()
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.HIDDEN)
        self.assertEqual((self.listing.contact_phone, self.listing.description), ('', ''))
        self.assertFalse(LocalListingImage.objects.filter(listing=self.listing).exists())
        self.assertFalse(default_storage.exists(self.image_name))

    def test_private_records_deleted(self):
        self._schedule(days_ago=4)
        self._run_task()
        for model, field in ((TrustedShop, 'owner'), (SavedSearch, 'user'), (Favorite, 'user'),
                             (Notification, 'user'), (TelegramLinkToken, 'user'), (DealerApplication, 'user')):
            self.assertFalse(model.objects.filter(**{field: self.user}).exists(), model.__name__)
        self.calc.refresh_from_db()
        self.assertIsNone(self.calc.user)
        self.assertFalse(self.shipment.watchers.filter(pk=self.user.pk).exists())

    def test_consent_records_kept_and_unlinked(self):
        total = ConsentRecord.objects.count()
        self._schedule(days_ago=4)
        self._run_task()
        self.assertEqual(ConsentRecord.objects.count(), total)
        self.assertFalse(ConsentRecord.objects.filter(user=self.user).exists())
        self.assertEqual(ConsentRecord.objects.filter(lead_id=self.lead.pk).count(), self.lead_consents)

    def test_lead_anonymized_but_partner_fields_kept(self):
        before = Lead.objects.get(pk=self.lead.pk)
        self._schedule(days_ago=4)
        self._run_task()
        lead = Lead.objects.get(pk=self.lead.pk)
        self.assertEqual(lead.name, DELETED_NAME)
        self.assertEqual((lead.phone, lead.email, lead.contact_handle, lead.comment), ('', '', '', ''))
        self.assertIsNone(lead.user)
        self.assertEqual(lead.public_id, self.lead_public_id)
        for field in ('partner_name', 'partner_status', 'journal_message_id', 'attribution_until',
                      'calculation_snapshot', 'utm', 'referrer', 'entry_page_url', 'page_url'):
            self.assertEqual(getattr(lead, field), getattr(before, field), field)

    def test_deleted_email_sent_to_old_address(self):
        self._schedule(days_ago=4)
        mail.outbox.clear()
        self._run_task()
        self.assertEqual([m.to for m in mail.outbox], [['gone@test.com']])
        self.assertIn('видалено', mail.outbox[0].subject)

    def test_smtp_failure_does_not_block_anonymization(self):
        self._schedule(days_ago=4)
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError('smtp down')):
            self.assertEqual(self._run_task(), 1)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deleted_at)

    def test_one_failure_does_not_stop_others(self):
        second = make_user('second@test.com')
        self._schedule(days_ago=4)
        User.objects.filter(pk=second.pk).update(deletion_scheduled_at=timezone.now() - timedelta(days=5))
        real = anonymize_user

        def flaky(user, **kw):
            if user.pk == self.user.pk:
                raise RuntimeError('boom')
            return real(user, **kw)

        with mock.patch('users.services.anonymize_user', side_effect=flaky):
            self.assertEqual(self._run_task(), 1)
        second.refresh_from_db()
        self.assertIsNotNone(second.deleted_at)

    def test_broker_import_conversations_passed_to_admin(self):
        from tests.factories import make_broker, make_listing, make_vehicle
        broker = make_broker('broker.gone@test.com')
        admin = make_staff('boss@test.com', superuser=True)
        lot = make_listing(make_vehicle(), admin)
        conv, _, _ = get_or_create_conversation(self.other, 'imported', lot.pk, 'Питання по лоту')
        conv.participants.add(broker)
        anonymize_user(broker)
        self.assertFalse(conv.participants.filter(pk=broker.pk).exists())
        self.assertTrue(conv.participants.filter(pk=admin.pk).exists())

    def test_cancel_during_task_run_is_respected(self):
        # Отмена после выборки задачи и до блокировки строки: обезличивать нельзя.
        self._schedule(days_ago=4)
        real = anonymize_user

        def cancel_then_anonymize(user, **kw):
            User.objects.filter(pk=user.pk).update(deletion_scheduled_at=None)
            return real(user, **kw)

        with mock.patch('users.services.anonymize_user', side_effect=cancel_then_anonymize):
            self.assertEqual(self._run_task(), 0)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.deleted_at)
        self.assertEqual(self.user.email, 'gone@test.com')

    def test_squatted_placeholder_email_does_not_block(self):
        make_user(f'deleted-{self.user.pk}@deleted.invalid')
        self._schedule(days_ago=4)
        self.assertEqual(self._run_task(), 1)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.deleted_at)

    def test_anonymize_is_idempotent(self):
        self.assertTrue(anonymize_user(self.user))
        self.assertFalse(anonymize_user(self.user))


# ─── Выгрузка «Мої дані» ─────────────────────────────────────────────────────

class DataExportTests(AccountTestCase):
    SECTIONS = {
        'profile', 'consents', 'trusted_shops', 'dealer_applications', 'calculations', 'watched_shipments',
        'leads', 'local_listings', 'imported_listings', 'favorites', 'saved_searches', 'notifications',
        'conversations', 'deals', 'reviews_written', 'reviews_received', 'reports_filed', 'payments',
    }

    def setUp(self):
        super().setUp()
        s = SiteSettings.load()
        s.partner_name = 'Партнер Тест'
        s.save()
        self.a = make_user('alice@test.com', first_name='Аліна', last_name='Мороз', phone='+380501110000')
        self.b = make_user('bob@test.com', first_name='Богдан', last_name='Лис', phone='+380502220000')
        ConsentRecord.objects.create(user=self.a, document='terms', method='register', doc_version='2026-10')
        self.a_lead = create_lead(user=self.a, data={
            'name': 'Аліна', 'phone': '0501110000', 'contact_method': 'telegram', 'source': 'landing'})
        create_lead(user=self.b, data={
            'name': 'Богдан-заявка', 'phone': '0502220000', 'contact_method': 'telegram', 'source': 'landing'})
        TrustedShop.objects.create(owner=self.a, name='СТО Аліни')
        TrustedShop.objects.create(owner=self.b, name='СТО Богдана')
        Notification.objects.create(user=self.b, type='new_message', title='Сповіщення Богдана')
        listing = make_local_listing(self.a, contact_phone='+380501110000')
        conv, _, _ = get_or_create_conversation(self.b, 'local', listing.pk, 'Повідомлення від Богдана')
        send_message_to_conversation(self.a, conv, 'Відповідь Аліни')
        deal = propose_deal(listing, self.a, self.b.pk)
        confirm_deal(deal, self.b)
        Review.objects.create(deal=deal, author=self.b, target=self.a, rating=4, text='Добре')
        Report.objects.create(reporter=self.a, reported_user=self.b, reason='spam', comment='Скарга Аліни')
        Report.objects.create(reporter=self.b, reported_user=self.a, reason='fraud', comment='Скарга на Аліну')
        Payment.objects.create(user=self.a, order_id='ORD-A', amount='100.00', currency='UAH',
                               liqpay_raw={'sender_card_mask2': 'SECRET-RAW'})
        self.client, _ = _session(self.a)

    def _export(self):
        resp = self.client.get(EXPORT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp, json.loads(resp.content)

    def test_anonymous_is_401(self):
        self.assertEqual(APIClient().get(EXPORT_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_is_json_attachment_with_all_sections(self):
        resp, data = self._export()
        self.assertTrue(resp['Content-Type'].startswith('application/json'))
        self.assertRegex(resp['Content-Disposition'], r'^attachment; filename="autoforyou-data-\d{4}-\d{2}-\d{2}\.json"$')
        self.assertEqual(resp['Cache-Control'], 'no-store')
        self.assertTrue(self.SECTIONS <= set(data))
        self.assertEqual(data['profile']['email'], 'alice@test.com')
        self.assertEqual(data['profile']['phone'], '+380501110000')

    def test_contains_own_leads_and_consents(self):
        _, data = self._export()
        public_id = Lead.objects.get(pk=self.a_lead.pk).public_id
        self.assertEqual([lead['public_id'] for lead in data['leads']], [public_id])
        docs = {(c['document'], c['lead_public_id']) for c in data['consents']}
        self.assertIn(('terms', ''), docs)
        self.assertIn(('lead_processing', public_id), docs)

    def test_contains_own_conversation_deal_reviews(self):
        _, data = self._export()
        self.assertEqual(data['conversations'][0]['with'], ['Богдан Л.'])
        texts = [m['text'] for m in data['conversations'][0]['messages']]
        self.assertEqual(texts, ['Повідомлення від Богдана', 'Відповідь Аліни'])
        self.assertEqual(data['deals'][0]['counterparty'], 'Богдан Л.')
        self.assertEqual(data['reviews_received'][0]['author'], 'Богдан Л.')
        self.assertEqual([r['comment'] for r in data['reports_filed']], ['Скарга Аліни'])
        self.assertEqual(data['local_listings'][0]['contact_phone'], '+380501110000')

    def test_nothing_from_other_user_but_display_name(self):
        resp, _ = self._export()
        body = resp.content.decode()
        for marker in ('bob@test.com', '+380502220000', '0502220000', 'Богдан-заявка', 'СТО Богдана',
                       'Сповіщення Богдана', 'Скарга на Аліну', 'Лис'):
            self.assertNotIn(marker, body)

    def test_payment_without_raw_provider_response(self):
        resp, data = self._export()
        self.assertEqual(data['payments'][0]['order_id'], 'ORD-A')
        self.assertNotIn('SECRET-RAW', resp.content.decode())
        self.assertNotIn('liqpay_raw', data['payments'][0])

    def test_throttle_data_export(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'data_export': '2/min'}):
            for _ in range(2):
                self.assertEqual(self.client.get(EXPORT_URL).status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get(EXPORT_URL).status_code, status.HTTP_429_TOO_MANY_REQUESTS)


# ─── Админка ─────────────────────────────────────────────────────────────────

class AdminAnonymizeTests(AccountTestCase):
    def setUp(self):
        super().setUp()
        self.root = make_staff('root@test.com', superuser=True)
        self.target = make_user('victim@test.com', first_name='Іра')
        self.client.force_login(self.root)

    def test_delete_page_forbidden_even_for_superuser(self):
        resp = self.client.get(f'/admin/users/customuser/{self.target.pk}/delete/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_bulk_delete_action_absent(self):
        resp = self.client.get('/admin/users/customuser/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('value="delete_selected"', resp.content.decode())
        self.assertIn('value="anonymize"', resp.content.decode())

    def test_anonymize_action_uses_service(self):
        with mock.patch('users.admin.anonymize_user', wraps=anonymize_user) as spy:
            resp = self.client.post('/admin/users/customuser/', {
                'action': 'anonymize', '_selected_action': [self.target.pk, self.root.pk]})
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        spy.assert_called_once()
        self.target.refresh_from_db()
        self.root.refresh_from_db()
        self.assertIsNotNone(self.target.deleted_at)
        self.assertIsNone(self.root.deleted_at)

    def test_other_superuser_skipped(self):
        other_root = make_staff('root2@test.com', superuser=True)
        self.client.post('/admin/users/customuser/', {
            'action': 'anonymize', '_selected_action': [self.target.pk, other_root.pk]})
        other_root.refresh_from_db()
        self.target.refresh_from_db()
        self.assertIsNone(other_root.deleted_at)
        self.assertEqual(other_root.email, 'root2@test.com')
        self.assertIsNotNone(self.target.deleted_at)

    def test_non_superuser_staff_cannot_anonymize(self):
        from django.contrib.auth.models import Permission
        staff = make_staff('staff@test.com')
        staff.user_permissions.add(*Permission.objects.filter(codename__in=['change_customuser', 'view_customuser']))
        self.client.force_login(staff)
        self.client.post('/admin/users/customuser/', {'action': 'anonymize', '_selected_action': [self.target.pk]})
        self.target.refresh_from_db()
        self.assertIsNone(self.target.deleted_at)

    def test_deleted_filter(self):
        anonymize_user(self.target)
        resp = self.client.get('/admin/users/customuser/?deleted=yes')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(list(resp.context['cl'].queryset), [self.target])
