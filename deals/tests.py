from django.test import TestCase
from rest_framework.test import APIClient

from local_listings.models import LocalListing
from messaging.models import Conversation
from tests.factories import (
    auth_client,
    make_admin_role,
    make_broker,
    make_local_listing,
    make_moderator,
    make_staff,
    make_user,
)

from .models import Deal
from .services import (
    cancel_deal,
    confirm_deal,
    create_review,
    propose_deal,
    seller_rating,
)


def _make_conversation(listing, initiator):
    conv, _ = Conversation.objects.get_or_create(
        local_listing=listing,
        initiator=initiator,
    )
    return conv


class ProposeDealServiceTest(TestCase):

    def setUp(self):
        self.seller = make_user('seller@example.com')
        self.buyer = make_user('buyer@example.com')
        self.listing = make_local_listing(self.seller)
        _make_conversation(self.listing, self.buyer)

    def test_propose_deal_success(self):
        deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        self.assertEqual(deal.status, Deal.Status.PROPOSED)
        self.assertEqual(deal.seller, self.seller)
        self.assertEqual(deal.buyer_id, self.buyer.pk)
        self.assertEqual(deal.listing, self.listing)

    def test_propose_deal_only_owner_can_propose(self):
        other = make_user('other@example.com')
        with self.assertRaisesMessage(ValueError, 'Тільки власник оголошення може запропонувати угоду.'):
            propose_deal(self.listing, other, self.buyer.pk)

    def test_propose_deal_no_self_deal(self):
        with self.assertRaisesMessage(ValueError, 'Продавець і покупець не можуть бути однією особою.'):
            propose_deal(self.listing, self.seller, self.seller.pk)

    def test_propose_deal_buyer_must_have_conversation(self):
        stranger = make_user('stranger@example.com')
        with self.assertRaisesMessage(ValueError, 'Покупець не писав по цьому оголошенню.'):
            propose_deal(self.listing, self.seller, stranger.pk)

    def test_propose_deal_no_duplicates(self):
        propose_deal(self.listing, self.seller, self.buyer.pk)
        with self.assertRaisesMessage(ValueError, 'Угода з цим покупцем вже існує'):
            propose_deal(self.listing, self.seller, self.buyer.pk)


class ConfirmDealServiceTest(TestCase):

    def setUp(self):
        self.seller = make_user('seller@example.com')
        self.buyer = make_user('buyer@example.com')
        self.listing = make_local_listing(self.seller)
        _make_conversation(self.listing, self.buyer)
        self.deal = propose_deal(self.listing, self.seller, self.buyer.pk)

    def test_buyer_can_confirm(self):
        deal = confirm_deal(self.deal, self.buyer)
        self.assertEqual(deal.status, Deal.Status.CONFIRMED)
        self.assertIsNotNone(deal.confirmed_at)

    def test_confirm_marks_listing_sold(self):
        confirm_deal(self.deal, self.buyer)
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, LocalListing.Status.SOLD)

    def test_seller_cannot_confirm(self):
        with self.assertRaises(ValueError):
            confirm_deal(self.deal, self.seller)

    def test_cannot_confirm_already_confirmed(self):
        confirm_deal(self.deal, self.buyer)
        with self.assertRaises(ValueError):
            confirm_deal(self.deal, self.buyer)


class CancelDealServiceTest(TestCase):

    def setUp(self):
        self.seller = make_user('seller@example.com')
        self.buyer = make_user('buyer@example.com')
        self.listing = make_local_listing(self.seller)
        _make_conversation(self.listing, self.buyer)
        self.deal = propose_deal(self.listing, self.seller, self.buyer.pk)

    def test_seller_can_cancel(self):
        deal = cancel_deal(self.deal, self.seller)
        self.assertEqual(deal.status, Deal.Status.CANCELLED)

    def test_buyer_can_cancel(self):
        deal = cancel_deal(self.deal, self.buyer)
        self.assertEqual(deal.status, Deal.Status.CANCELLED)

    def test_outsider_cannot_cancel(self):
        outsider = make_user('outsider@example.com')
        with self.assertRaises(ValueError):
            cancel_deal(self.deal, outsider)

    def test_cannot_cancel_confirmed_deal(self):
        confirm_deal(self.deal, self.buyer)
        self.deal.refresh_from_db()
        with self.assertRaises(ValueError):
            cancel_deal(self.deal, self.seller)


class CreateReviewServiceTest(TestCase):

    def setUp(self):
        self.seller = make_user('seller@example.com')
        self.buyer = make_user('buyer@example.com')
        self.listing = make_local_listing(self.seller)
        _make_conversation(self.listing, self.buyer)
        self.deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        self.deal = confirm_deal(self.deal, self.buyer)

    def test_buyer_can_review(self):
        review = create_review(self.deal, self.buyer, 5, 'Great seller!')
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.author, self.buyer)
        self.assertEqual(review.target, self.seller)
        self.assertEqual(review.deal, self.deal)

    def test_seller_cannot_review(self):
        with self.assertRaises(ValueError):
            create_review(self.deal, self.seller, 4)

    def test_cannot_review_non_confirmed_deal(self):
        seller2 = make_user('seller2@example.com')
        buyer2 = make_user('buyer2@example.com')
        listing2 = make_local_listing(seller2)
        _make_conversation(listing2, buyer2)
        deal2 = propose_deal(listing2, seller2, buyer2.pk)
        # deal2 is still PROPOSED
        with self.assertRaises(ValueError):
            create_review(deal2, buyer2, 3)

    def test_cannot_review_twice(self):
        create_review(self.deal, self.buyer, 5)
        # Reload deal with review prefetched
        from deals.models import Deal as DealModel
        deal_fresh = DealModel.objects.prefetch_related('review').get(pk=self.deal.pk)
        with self.assertRaises(ValueError):
            create_review(deal_fresh, self.buyer, 4)


class SellerRatingServiceTest(TestCase):

    def setUp(self):
        self.seller = make_user('seller@example.com')

    def _make_confirmed_deal_with_review(self, buyer_email, rating):
        buyer = make_user(buyer_email)
        listing = make_local_listing(self.seller)
        _make_conversation(listing, buyer)
        deal = propose_deal(listing, self.seller, buyer.pk)
        deal = confirm_deal(deal, buyer)
        create_review(deal, buyer, rating)
        return deal

    def test_no_deals_no_badge(self):
        result = seller_rating(self.seller.pk)
        self.assertEqual(result['confirmed_deal_count'], 0)
        self.assertEqual(result['review_count'], 0)
        self.assertIsNone(result['avg_rating'])
        self.assertFalse(result['has_badge'])

    def test_badge_at_threshold(self):
        for i in range(3):
            self._make_confirmed_deal_with_review(f'buyer{i}@example.com', 5)
        result = seller_rating(self.seller.pk)
        self.assertEqual(result['confirmed_deal_count'], 3)
        self.assertTrue(result['has_badge'])

    def test_no_badge_below_threshold(self):
        for i in range(2):
            self._make_confirmed_deal_with_review(f'buyer{i}@example.com', 4)
        result = seller_rating(self.seller.pk)
        self.assertEqual(result['confirmed_deal_count'], 2)
        self.assertFalse(result['has_badge'])

    def test_avg_rating_calculation(self):
        self._make_confirmed_deal_with_review('b1@example.com', 4)
        self._make_confirmed_deal_with_review('b2@example.com', 2)
        result = seller_rating(self.seller.pk)
        self.assertEqual(result['avg_rating'], 3.0)
        self.assertEqual(result['review_count'], 2)


class DealsAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.seller = make_user('seller@example.com')
        self.buyer = make_user('buyer@example.com')
        self.listing = make_local_listing(self.seller)
        _make_conversation(self.listing, self.buyer)

    def _auth(self, user):
        self.client = auth_client(user)

    def test_get_my_deals_empty(self):
        self._auth(self.seller)
        resp = self.client.get('/api/v1/deals/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_get_my_deals_unauthenticated(self):
        resp = self.client.get('/api/v1/deals/')
        self.assertEqual(resp.status_code, 401)

    def test_propose_deal_via_api(self):
        self._auth(self.seller)
        resp = self.client.post('/api/v1/deals/', {
            'listing_id': self.listing.pk,
            'buyer_id': self.buyer.pk,
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'proposed')

    def test_propose_deal_no_conversation_fails(self):
        self._auth(self.seller)
        stranger = make_user('stranger@example.com')
        resp = self.client.post('/api/v1/deals/', {
            'listing_id': self.listing.pk,
            'buyer_id': stranger.pk,
        })
        self.assertEqual(resp.status_code, 400)

    def test_confirm_deal_via_api(self):
        deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        self._auth(self.buyer)
        resp = self.client.post(f'/api/v1/deals/{deal.pk}/confirm/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'confirmed')

    def test_cancel_deal_via_api(self):
        deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        self._auth(self.buyer)
        resp = self.client.post(f'/api/v1/deals/{deal.pk}/cancel/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'cancelled')

    def test_review_via_api(self):
        deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        deal = confirm_deal(deal, self.buyer)
        self._auth(self.buyer)
        resp = self.client.post(f'/api/v1/deals/{deal.pk}/review/', {
            'rating': 5,
            'text': 'Excellent!',
        })
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['rating'], 5)

    def test_seller_rating_api_public(self):
        resp = self.client.get(f'/api/v1/deals/seller-rating/{self.seller.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('has_badge', resp.data)
        self.assertIn('avg_rating', resp.data)

    def test_seller_deals_visible_in_my_deals(self):
        propose_deal(self.listing, self.seller, self.buyer.pk)
        self._auth(self.seller)
        resp = self.client.get('/api/v1/deals/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_buyer_deals_visible_in_my_deals(self):
        propose_deal(self.listing, self.seller, self.buyer.pk)
        self._auth(self.buyer)
        resp = self.client.get('/api/v1/deals/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)


class ListingBuyersAPITest(TestCase):
    """Задача 1.9 (13-S1): покупатели объявления без ПДн."""

    def setUp(self):
        self.owner = make_user('owner@example.com')
        self.buyer = make_user('leaky.buyer@example.com', first_name='Іван', last_name='Петренко')
        self.nameless = make_user('nameless.person@example.com')
        self.listing = make_local_listing(self.owner)
        _make_conversation(self.listing, self.buyer)
        _make_conversation(self.listing, self.nameless)
        self.url = f'/api/v1/deals/listing-buyers/{self.listing.pk}/'

    def test_anonymous_401(self):
        self.assertEqual(APIClient().get(self.url).status_code, 401)

    def test_stranger_404(self):
        self.assertEqual(auth_client(make_user()).get(self.url).status_code, 404)

    def test_buyer_404(self):
        self.assertEqual(auth_client(self.buyer).get(self.url).status_code, 404)

    def test_staff_without_admin_role_404(self):
        self.assertEqual(auth_client(make_staff()).get(self.url).status_code, 404)

    def test_broker_404(self):
        self.assertEqual(auth_client(make_broker()).get(self.url).status_code, 404)

    def test_moderator_404(self):
        self.assertEqual(auth_client(make_moderator()).get(self.url).status_code, 404)

    def test_admin_role_200(self):
        self.assertEqual(auth_client(make_admin_role()).get(self.url).status_code, 200)

    def test_owner_gets_only_buyers_without_pii(self):
        resp = auth_client(self.owner).get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            sorted(resp.json(), key=lambda b: b['id']),
            sorted([
                {'id': self.buyer.pk, 'display_name': 'Іван П.'},
                {'id': self.nameless.pk, 'display_name': 'Користувач'},
            ], key=lambda b: b['id']),
        )
        body = resp.content.decode()
        for leak in ('leaky.buyer', 'nameless.person', 'example.com', 'Петренко', 'owner@'):
            self.assertNotIn(leak, body)

    def test_unknown_listing_404(self):
        self.assertEqual(auth_client(self.owner).get('/api/v1/deals/listing-buyers/999999/').status_code, 404)


class DealsNoEmailLeakTest(TestCase):
    """Задача 1.9 (06-S5): email контрагента не раскрывается в сделках, отзывах, уведомлениях."""

    def setUp(self):
        self.seller = make_user('seller.secret@example.com')
        self.buyer = make_user('buyer.secret@example.com', first_name='Марія', last_name='Шевчук')
        self.listing = make_local_listing(self.seller)
        _make_conversation(self.listing, self.buyer)

    def _assert_clean(self, text):
        for leak in ('secret', 'example.com', 'Шевчук'):
            self.assertNotIn(leak, text)

    def test_deals_list_has_no_email(self):
        propose_deal(self.listing, self.seller, self.buyer.pk)
        for user in (self.seller, self.buyer):
            resp = auth_client(user).get('/api/v1/deals/')
            self.assertEqual(resp.status_code, 200)
            self._assert_clean(resp.content.decode())
            deal = resp.json()[0]
            self.assertEqual(set(deal['seller']), {'id', 'display_name'})
            self.assertEqual(set(deal['buyer']), {'id', 'display_name'})
            self.assertEqual(deal['seller']['display_name'], 'Користувач')
            self.assertEqual(deal['buyer']['display_name'], 'Марія Ш.')

    def test_review_has_author_name_not_email(self):
        deal = confirm_deal(propose_deal(self.listing, self.seller, self.buyer.pk), self.buyer)
        resp = auth_client(self.buyer).post(f'/api/v1/deals/{deal.pk}/review/', {'rating': 5, 'text': 'ok'})
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn('author_email', resp.json())
        self.assertEqual(resp.json()['author_name'], 'Марія Ш.')
        deals = auth_client(self.seller).get('/api/v1/deals/')
        self.assertNotIn('author_email', deals.json()[0]['review'])
        self._assert_clean(deals.content.decode())

    def test_proposal_notification_has_no_email(self):
        from unittest.mock import patch

        from notifications.models import Notification
        with patch('integrations.tasks.send_notification.delay') as tg:
            propose_deal(self.listing, self.seller, self.buyer.pk)
        note = Notification.objects.get(user=self.buyer, type=Notification.Type.DEAL_PROPOSED)
        self._assert_clean(note.title + note.text)
        self.assertIn('Користувач', note.text)
        tg.assert_called_once()
        self._assert_clean(tg.call_args.args[1])


class SellerRatingAccessTest(TestCase):
    """Задача 1.9 (06-S12): рейтинг только у продавцов с публичными объявлениями."""

    def test_seller_with_active_listing_200(self):
        seller = make_user()
        make_local_listing(seller)
        resp = APIClient().get(f'/api/v1/deals/seller-rating/{seller.pk}/')
        self.assertEqual(resp.status_code, 200)

    def test_user_without_public_listings_404(self):
        seller = make_user()
        make_local_listing(seller, status=LocalListing.Status.PENDING)
        resp = APIClient().get(f'/api/v1/deals/seller-rating/{seller.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_unknown_user_404(self):
        self.assertEqual(APIClient().get('/api/v1/deals/seller-rating/999999/').status_code, 404)
