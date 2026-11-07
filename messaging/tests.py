from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from local_listings.models import City, LocalListing, Region
from messaging.models import Conversation, Message
from messaging.services import get_or_create_conversation, unread_count_for_user
from tests.factories import make_dealer, make_listing, make_local_listing, make_user, make_vehicle


class SetupMixin(TestCase):
    def setUp(self):
        self.buyer = make_user('buyer@test.com')
        self.seller = make_user('seller@test.com')
        # Признак администратора — is_staff. Раньше здесь стояло role='admin':
        # тест проходил, но проверял привилегию, которую пользователь мог
        # назначить себе сам.
        self.admin = make_user('admin@test.com', role='admin', is_staff=True)
        self.region = Region.objects.create(name='Київська', slug='kyivska')
        self.city = City.objects.create(name='Київ', slug='kyiv', region=self.region)
        self.listing = make_local_listing(self.seller, region=self.region, city=self.city)
        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)


# ── Сервіс ──────────────────────────────────────────────────────────────────


class TestGetOrCreateConversation(SetupMixin):
    def test_creates_new_conversation(self):
        conv, created, msg = get_or_create_conversation(
            self.buyer, 'local', self.listing.pk, 'Привіт!'
        )
        self.assertTrue(created)
        self.assertIsNotNone(conv.pk)
        self.assertEqual(msg.text, 'Привіт!')
        self.assertIn(self.buyer, conv.participants.all())
        self.assertIn(self.seller, conv.participants.all())

    def test_reuses_existing_conversation(self):
        conv1, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        conv2, created, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Ще раз')
        self.assertFalse(created)
        self.assertEqual(conv1.pk, conv2.pk)
        self.assertEqual(conv1.messages.count(), 2)

    def test_cannot_message_own_listing(self):
        with self.assertRaises(ValueError):
            get_or_create_conversation(self.seller, 'local', self.listing.pk, 'Привіт!')

    def test_inactive_listing_raises(self):
        self.listing.status = LocalListing.Status.PENDING
        self.listing.save()
        with self.assertRaises(ValueError):
            get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')

    def test_unknown_listing_type_raises(self):
        with self.assertRaises(ValueError):
            get_or_create_conversation(self.buyer, 'unknown', 1, 'text')


class TestUnreadCount(SetupMixin):
    def test_unread_count(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        # buyer sent 1 msg — seller has 1 unread, buyer has 0
        self.assertEqual(unread_count_for_user(self.seller), 1)
        self.assertEqual(unread_count_for_user(self.buyer), 0)

    def test_unread_decreases_after_read(self):
        from messaging.services import mark_as_read
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        mark_as_read(self.seller, conv)
        self.assertEqual(unread_count_for_user(self.seller), 0)


# ── API ─────────────────────────────────────────────────────────────────────


class TestStartConversationAPI(SetupMixin):
    url = '/api/v1/messages/start/'

    def test_anon_gets_401(self):
        r = self.client.post(self.url, {'listing_type': 'local', 'listing_id': self.listing.pk, 'text': 'Hi'}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_buyer_starts_conversation(self):
        self.auth(self.buyer)
        r = self.client.post(self.url, {'listing_type': 'local', 'listing_id': self.listing.pk, 'text': 'Привіт!'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertIn('conversation_id', r.data)
        self.assertTrue(r.data['created'])

    def test_repeat_returns_200(self):
        self.auth(self.buyer)
        payload = {'listing_type': 'local', 'listing_id': self.listing.pk, 'text': 'text'}
        self.client.post(self.url, payload, format='json')
        r = self.client.post(self.url, payload, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data['created'])

    def test_seller_cannot_self_message(self):
        self.auth(self.seller)
        r = self.client.post(self.url, {'listing_type': 'local', 'listing_id': self.listing.pk, 'text': 'Hi'}, format='json')
        self.assertEqual(r.status_code, 400)


class TestConversationListAPI(SetupMixin):
    def test_buyer_sees_own_conversations(self):
        get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.buyer)
        r = self.client.get('/api/v1/messages/conversations/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 1)

    def test_stranger_sees_nothing(self):
        get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        stranger = make_user('stranger@test.com')
        self.auth(stranger)
        r = self.client.get('/api/v1/messages/conversations/')
        self.assertEqual(r.data['count'], 0)

    def test_anon_gets_401(self):
        r = self.client.get('/api/v1/messages/conversations/')
        self.assertEqual(r.status_code, 401)


class TestConversationDetailAPI(SetupMixin):
    def setUp(self):
        super().setUp()
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.conv = conv

    def test_buyer_can_read_thread(self):
        self.auth(self.buyer)
        r = self.client.get(f'/api/v1/messages/conversations/{self.conv.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['messages']), 1)

    def test_seller_can_read_thread(self):
        self.auth(self.seller)
        r = self.client.get(f'/api/v1/messages/conversations/{self.conv.pk}/')
        self.assertEqual(r.status_code, 200)

    def test_stranger_gets_404(self):
        stranger = make_user('stranger2@test.com')
        self.auth(stranger)
        r = self.client.get(f'/api/v1/messages/conversations/{self.conv.pk}/')
        self.assertEqual(r.status_code, 404)

    def test_reading_marks_messages_as_read(self):
        # seller reads → buyer's message becomes read
        self.auth(self.seller)
        self.client.get(f'/api/v1/messages/conversations/{self.conv.pk}/')
        msg = Message.objects.filter(conversation=self.conv).first()
        self.assertIsNotNone(msg.read_at)

    def test_seller_can_reply(self):
        self.auth(self.seller)
        r = self.client.post(
            f'/api/v1/messages/conversations/{self.conv.pk}/',
            {'text': 'Відповідь продавця'},
            format='json',
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.conv.messages.count(), 2)

    def test_stranger_cannot_post(self):
        stranger = make_user('stranger3@test.com')
        self.auth(stranger)
        r = self.client.post(
            f'/api/v1/messages/conversations/{self.conv.pk}/',
            {'text': 'spam'},
            format='json',
        )
        self.assertEqual(r.status_code, 404)


class TestUnreadCountAPI(SetupMixin):
    def test_unread_count_zero_initially(self):
        self.auth(self.buyer)
        r = self.client.get('/api/v1/messages/unread-count/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['unread_count'], 0)

    def test_unread_count_increments(self):
        get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.seller)
        r = self.client.get('/api/v1/messages/unread-count/')
        self.assertEqual(r.data['unread_count'], 1)

    def test_anon_gets_401(self):
        r = self.client.get('/api/v1/messages/unread-count/')
        self.assertEqual(r.status_code, 401)


class TestNoEmailLeak(SetupMixin):
    """Задача 1.9 (06-S5): email и его локальная часть не уходят в ответы и уведомления."""

    def setUp(self):
        super().setUp()
        self.nameless = make_user('leaky.nameless@test.com')

    def _assert_clean(self, text):
        for leak in ('leaky', 'nameless@', '@test.com'):
            self.assertNotIn(leak, text)

    def test_conversation_responses_have_no_email(self):
        conv, _, _ = get_or_create_conversation(self.nameless, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.seller)
        lst = self.client.get('/api/v1/messages/conversations/')
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(set(lst.data['results'][0]['other_participant']), {'id', 'display_name'})
        self.assertEqual(lst.data['results'][0]['other_participant']['display_name'], 'Користувач')
        self._assert_clean(lst.content.decode())
        det = self.client.get(f'/api/v1/messages/conversations/{conv.pk}/')
        self.assertEqual(det.status_code, 200)
        for p in det.data['participants']:
            self.assertEqual(set(p), {'id', 'display_name'})
        self.assertEqual(det.data['messages'][0]['sender_name'], 'Користувач')
        self._assert_clean(det.content.decode())

    def test_message_notification_has_no_email(self):
        from unittest.mock import patch

        from notifications.models import Notification
        with patch('integrations.tasks.send_notification.delay') as tg,                 self.captureOnCommitCallbacks(execute=True):
            get_or_create_conversation(self.nameless, 'local', self.listing.pk, 'Привіт!')
        note = Notification.objects.get(user=self.seller, type=Notification.Type.NEW_MESSAGE)
        self._assert_clean(note.title + note.text)
        self.assertIn('Користувач', note.title)
        tg.assert_called_once()
        self._assert_clean(tg.call_args.args[1])


class TestStartImportedConversationGating(SetupMixin):
    url = '/api/v1/messages/start/'

    def _start(self, user, listing):
        self.auth(user)
        return self.client.post(
            self.url, {'listing_type': 'imported', 'listing_id': listing.pk, 'text': 'Hi'}, format='json',
        )

    def test_retail_lot_works_when_lots_enabled(self):
        lot = make_listing(make_vehicle(), self.seller)
        self.assertEqual(self._start(self.buyer, lot).status_code, 201)

    @override_settings(LOTS_ENABLED=False)
    def test_imported_is_404_when_lots_disabled(self):
        lot = make_listing(make_vehicle(), self.seller)
        self.assertEqual(self._start(self.buyer, lot).status_code, 404)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_wholesale_is_404_for_regular_buyer(self):
        lot = make_listing(make_vehicle(), self.seller, channel='wholesale')
        self.assertEqual(self._start(self.buyer, lot).status_code, 404)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_wholesale_works_for_verified_dealer(self):
        lot = make_listing(make_vehicle(), self.seller, channel='wholesale')
        self.assertEqual(self._start(make_dealer(), lot).status_code, 201)

    @override_settings(B2B_ENABLED=False)
    def test_wholesale_is_404_for_dealer_when_b2b_disabled(self):
        lot = make_listing(make_vehicle(), self.seller, channel='wholesale')
        self.assertEqual(self._start(make_dealer(), lot).status_code, 404)
        self.assertEqual(Conversation.objects.count(), 0)


# ── Задача 4.7 ──────────────────────────────────────────────────────────────

PHONE_TEXT = 'Дзвоніть +380501234567'


class TestAntispamHard47(SetupMixin):

    def setUp(self):
        super().setUp()
        cache.clear()

    @override_settings(ANTISPAM_MODE='hard')
    def test_start_with_phone_is_400_and_no_conversation(self):
        self.auth(self.buyer)
        r = self.client.post('/api/v1/messages/start/', {
            'listing_type': 'local', 'listing_id': self.listing.pk, 'text': PHONE_TEXT}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('text', r.data)
        self.assertFalse(Conversation.objects.exists())

    @override_settings(ANTISPAM_MODE='hard')
    def test_reply_with_phone_is_400_and_no_message(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.seller)
        r = self.client.post(f'/api/v1/messages/conversations/{conv.pk}/', {'text': PHONE_TEXT}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('text', r.data)
        self.assertEqual(Message.objects.count(), 1)

    @override_settings(ANTISPAM_MODE='soft')
    def test_soft_returns_warning(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.seller)
        r = self.client.post(f'/api/v1/messages/conversations/{conv.pk}/', {'text': PHONE_TEXT}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertIn('warning', r.data)


class TestReplyThrottle47(SetupMixin):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def test_third_reply_is_429_start_not_limited(self):
        from rest_framework.settings import api_settings
        from rest_framework.throttling import ScopedRateThrottle
        rates = {**api_settings.DEFAULT_THROTTLE_RATES, 'messages_reply': '2/hour'}
        with patch.object(ScopedRateThrottle, 'THROTTLE_RATES', rates):
            conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
            self.auth(self.seller)
            url = f'/api/v1/messages/conversations/{conv.pk}/'
            codes = [self.client.post(url, {'text': f'Відповідь {i}'}, format='json').status_code for i in range(3)]
            self.assertEqual(codes, [201, 201, 429])
            other = make_local_listing(self.seller, region=self.region, city=self.city)
            self.auth(self.buyer)
            r = self.client.post('/api/v1/messages/start/', {
                'listing_type': 'local', 'listing_id': other.pk, 'text': 'Ще одне'}, format='json')
            self.assertEqual(r.status_code, 201)


class TestNotifyOnCommit47(SetupMixin):

    def test_telegram_only_after_commit(self):
        with patch('integrations.tasks.send_notification.delay') as tg:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
            tg.assert_not_called()
            for cb in callbacks:
                cb()
            tg.assert_called_once()

    def test_notification_errors_logged_not_raised(self):
        self.auth(self.buyer)
        with patch('notifications.services.create_notification', side_effect=RuntimeError('db down')), \
                self.assertLogs('notifications.services', level='ERROR') as logs:
            r = self.client.post('/api/v1/messages/start/', {
                'listing_type': 'local', 'listing_id': self.listing.pk, 'text': 'Секретний текст'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertNotIn('Секретний', '\n'.join(logs.output))

    def test_deleted_recipient_gets_no_notification(self):
        from django.utils import timezone

        from notifications.models import Notification
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        Notification.objects.all().delete()
        self.seller.__class__.objects.filter(pk=self.seller.pk).update(deleted_at=timezone.now(), is_active=False)
        self.auth(self.buyer)
        r = self.client.post(f'/api/v1/messages/conversations/{conv.pk}/', {'text': 'Ви тут?'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['detail'], 'Користувач видалений')
        self.assertFalse(Notification.objects.filter(user=self.seller).exists())


class TestConversationListQueries47(SetupMixin):

    def _make(self, n):
        for _ in range(n):
            listing = make_local_listing(self.seller, region=self.region, city=self.city)
            conv, _, _ = get_or_create_conversation(self.buyer, 'local', listing.pk, 'Привіт!')
            Message.objects.create(conversation=conv, sender=self.seller, text='Відповідь продавця')

    def _queries(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.auth(self.buyer)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get('/api/v1/messages/conversations/')
        self.assertEqual(r.status_code, 200)
        return len(ctx.captured_queries), r

    def test_constant_queries_and_values(self):
        self._make(2)
        few, r = self._queries()
        first = r.data['results'][0]
        self.assertEqual(first['last_message_text'], 'Відповідь продавця')
        self.assertEqual(first['unread_count'], 1)
        self.assertEqual(first['other_participant']['id'], self.seller.pk)
        self._make(18)
        many, r = self._queries()
        self.assertEqual(few, many)
        self.assertEqual(r.data['count'], 20)


class TestMessagesPagination47(SetupMixin):

    @override_settings(MESSAGES_PAGE_SIZE=5)
    def test_last_n_and_earlier_by_cursor(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'm0')
        for i in range(1, 12):
            Message.objects.create(conversation=conv, sender=self.buyer, text=f'm{i}')
        self.auth(self.seller)
        url = f'/api/v1/messages/conversations/{conv.pk}/'
        r = self.client.get(url)
        self.assertEqual([m['text'] for m in r.data['messages']], ['m7', 'm8', 'm9', 'm10', 'm11'])
        self.assertTrue(r.data['has_earlier'])
        r2 = self.client.get(f"{url}?before={r.data['messages'][0]['id']}")
        self.assertEqual([m['text'] for m in r2.data['messages']], ['m2', 'm3', 'm4', 'm5', 'm6'])
        self.assertTrue(r2.data['has_earlier'])
        self.assertEqual(self.client.get(f'{url}?before=abc').status_code, 400)


class TestConversationRace47(SetupMixin):

    def test_integrity_error_returns_existing(self):
        """Второй параллельный запрос: первая проверка «диалога нет», create падает на уникальности."""
        from unittest.mock import MagicMock
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        real_filter = Conversation.objects.filter
        calls = {'n': 0}

        def filter_once_empty(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                return MagicMock(first=MagicMock(return_value=None))
            return real_filter(*args, **kwargs)

        with patch.object(Conversation.objects, 'filter', side_effect=filter_once_empty),                 patch.object(Conversation.objects, 'create', side_effect=IntegrityError('unique_initiator_local_listing')):
            again, created, msg = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Ще раз')
        self.assertFalse(created)
        self.assertEqual(again.pk, conv.pk)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(msg.conversation_id, conv.pk)


class TestClosedAndReadMarks47(SetupMixin):

    def test_reply_to_sold_listing_is_closed(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        LocalListing.objects.filter(pk=self.listing.pk).update(status=LocalListing.Status.SOLD)
        self.auth(self.buyer)
        r = self.client.post(f'/api/v1/messages/conversations/{conv.pk}/', {'text': 'Ще актуально?'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertIn('Діалог закрито', r.data['detail'])

    def test_broker_opening_import_dialog_does_not_mark_read(self):
        from tests.factories import make_broker
        vehicle = make_vehicle()
        lot = make_listing(vehicle, make_dealer())
        broker1 = make_broker()
        conv = Conversation.objects.create(initiator=self.buyer, imported_listing=lot)
        conv.participants.set([self.buyer.pk, broker1.pk])
        reply = Message.objects.create(conversation=conv, sender=broker1, text='Відповідь брокера')
        broker2 = make_broker()
        self.auth(broker2)
        r = self.client.get(f'/api/v1/messages/conversations/{conv.pk}/')
        self.assertEqual(r.status_code, 200)
        reply.refresh_from_db()
        self.assertIsNone(reply.read_at)


class TestReviewFixes47(SetupMixin):
    """Ревью 4.7: входящие для брокеров (E3), закрытые диалоги (E5), notify удалённому."""

    def _import_dialog(self):
        from tests.factories import make_broker
        lot = make_listing(make_vehicle(), make_dealer())
        self.broker1, self.broker2 = make_broker(), make_broker()
        conv = Conversation.objects.create(initiator=self.buyer, imported_listing=lot)
        conv.participants.set([self.buyer.pk, self.broker1.pk])
        Message.objects.create(conversation=conv, sender=self.buyer, text='Питання покупця')
        colleague = Message.objects.create(conversation=conv, sender=self.broker2, text='Відповідь колеги')
        return conv, colleague

    def test_participant_broker_does_not_mark_colleague_reply(self):
        conv, colleague = self._import_dialog()
        self.auth(self.broker1)
        self.assertEqual(self.client.get(f'/api/v1/messages/conversations/{conv.pk}/').status_code, 200)
        colleague.refresh_from_db()
        self.assertIsNone(colleague.read_at)
        self.assertEqual(unread_count_for_user(self.buyer), 1)

    def test_broker_unread_ignores_colleague_messages(self):
        conv, _ = self._import_dialog()
        from tests.factories import make_broker
        broker3 = make_broker()
        self.auth(broker3)
        item = next(c for c in self.client.get('/api/v1/messages/conversations/').data['results'] if c['id'] == conv.pk)
        self.assertEqual(item['unread_count'], 1)  # только сообщение покупателя
        self.client.get(f'/api/v1/messages/conversations/{conv.pk}/')
        item = next(c for c in self.client.get('/api/v1/messages/conversations/').data['results'] if c['id'] == conv.pk)
        self.assertEqual(item['unread_count'], 0)
        self.assertEqual(unread_count_for_user(broker3), 0)

    def test_reply_closed_for_every_non_open_status(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.buyer)
        url = f'/api/v1/messages/conversations/{conv.pk}/'
        for st in LocalListing.Status:
            LocalListing.objects.filter(pk=self.listing.pk).update(status=st)
            expected = 201 if st in (LocalListing.Status.ACTIVE, LocalListing.Status.PENDING) else 403
            with self.subTest(status=st):
                self.assertEqual(self.client.post(url, {'text': f'{st}?'}, format='json').status_code, expected)

    def test_reply_closed_when_listing_deleted(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        Conversation.objects.filter(pk=conv.pk).update(local_listing=None)
        self.auth(self.buyer)
        r = self.client.post(f'/api/v1/messages/conversations/{conv.pk}/', {'text': 'Є?'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_notify_skips_anonymized_even_if_active(self):
        from django.utils import timezone

        from notifications.models import Notification
        from notifications.services import notify
        User = self.seller.__class__
        User.objects.filter(pk=self.seller.pk).update(deleted_at=timezone.now())  # is_active остаётся True
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            notify(self.seller.pk, 'deal_confirmed', {'listing': 'X'})
        self.assertFalse(Notification.objects.filter(user=self.seller).exists())
        self.assertEqual(callbacks, [])

    def test_before_non_ascii_digit_is_400(self):
        conv, _, _ = get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        self.auth(self.buyer)
        self.assertEqual(self.client.get(f'/api/v1/messages/conversations/{conv.pk}/?before=²').status_code, 400)
        self.assertEqual(
            self.client.get(f'/api/v1/messages/conversations/{conv.pk}/?before={"9" * 30}').status_code, 400)
