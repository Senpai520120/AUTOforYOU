from django.test import TestCase
from rest_framework.test import APIClient

from local_listings.models import City, LocalListing, Region
from messaging.models import Message
from messaging.services import get_or_create_conversation, unread_count_for_user
from users.models import CustomUser


def make_user(email, role='buyer', **kw):
    u = CustomUser.objects.create_user(email=email, password='pass1234', role=role, **kw)
    return u


def make_local_listing(owner, region, city, **kw):
    defaults = dict(
        make='Toyota', model='Camry', year=2020,
        mileage_km=50000, fuel_type='petrol', transmission='auto',
        body_type='sedan', condition='used',
        price='500000', currency='UAH', price_type='fixed',
        region=region, city=city,
        status=LocalListing.Status.ACTIVE,
        agreed_to_rules=True,
    )
    defaults.update(kw)
    return LocalListing.objects.create(owner=owner, **defaults)


class SetupMixin(TestCase):
    def setUp(self):
        self.buyer = make_user('buyer@test.com')
        self.seller = make_user('seller@test.com')
        self.admin = make_user('admin@test.com', role='admin')
        self.region = Region.objects.create(name='Київська', slug='kyivska')
        self.city = City.objects.create(name='Київ', slug='kyiv', region=self.region)
        self.listing = make_local_listing(self.seller, self.region, self.city)
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
        self.assertEqual(len(r.data), 1)

    def test_stranger_sees_nothing(self):
        get_or_create_conversation(self.buyer, 'local', self.listing.pk, 'Привіт!')
        stranger = make_user('stranger@test.com')
        self.auth(stranger)
        r = self.client.get('/api/v1/messages/conversations/')
        self.assertEqual(len(r.data), 0)

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

    def test_stranger_gets_403(self):
        stranger = make_user('stranger2@test.com')
        self.auth(stranger)
        r = self.client.get(f'/api/v1/messages/conversations/{self.conv.pk}/')
        self.assertEqual(r.status_code, 403)

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
        self.assertEqual(r.status_code, 403)


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
