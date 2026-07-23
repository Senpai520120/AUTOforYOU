from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from local_listings.models import LocalListing, Region, City
from messaging.models import Conversation
from .models import Deal
from .services import (
    propose_deal,
    confirm_deal,
    cancel_deal,
    create_review,
    seller_rating,
)

User = get_user_model()


def _make_user(email, **kwargs):
    return User.objects.create_user(
        email=email,
        password='testpassword123',
        **kwargs,
    )


def _make_listing(owner, status=LocalListing.Status.ACTIVE):
    region, _ = Region.objects.get_or_create(name='Тестова область', slug='test-region')
    city, _ = City.objects.get_or_create(
        region=region,
        name='Тестове місто',
        defaults={'slug': 'test-city'},
    )
    return LocalListing.objects.create(
        owner=owner,
        make='Toyota',
        model='Camry',
        year=2020,
        mileage_km=50000,
        fuel_type='petrol',
        transmission='auto',
        body_type='sedan',
        price=15000,
        currency='USD',
        region=region,
        city=city,
        status=status,
    )


def _make_conversation(listing, initiator):
    conv, _ = Conversation.objects.get_or_create(
        local_listing=listing,
        initiator=initiator,
    )
    return conv


class ProposeDealServiceTest(TestCase):

    def setUp(self):
        self.seller = _make_user('seller@example.com')
        self.buyer = _make_user('buyer@example.com')
        self.listing = _make_listing(self.seller)
        _make_conversation(self.listing, self.buyer)

    def test_propose_deal_success(self):
        deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        self.assertEqual(deal.status, Deal.Status.PROPOSED)
        self.assertEqual(deal.seller, self.seller)
        self.assertEqual(deal.buyer_id, self.buyer.pk)
        self.assertEqual(deal.listing, self.listing)

    def test_propose_deal_only_owner_can_propose(self):
        other = _make_user('other@example.com')
        with self.assertRaises(ValueError, msg='Тільки власник оголошення може запропонувати угоду.'):
            propose_deal(self.listing, other, self.buyer.pk)

    def test_propose_deal_no_self_deal(self):
        with self.assertRaises(ValueError):
            propose_deal(self.listing, self.seller, self.seller.pk)

    def test_propose_deal_buyer_must_have_conversation(self):
        stranger = _make_user('stranger@example.com')
        with self.assertRaises(ValueError, msg='Покупець не писав по цьому оголошенню.'):
            propose_deal(self.listing, self.seller, stranger.pk)

    def test_propose_deal_no_duplicates(self):
        propose_deal(self.listing, self.seller, self.buyer.pk)
        with self.assertRaises(ValueError, msg='Угода з цим покупцем вже існує'):
            propose_deal(self.listing, self.seller, self.buyer.pk)


class ConfirmDealServiceTest(TestCase):

    def setUp(self):
        self.seller = _make_user('seller@example.com')
        self.buyer = _make_user('buyer@example.com')
        self.listing = _make_listing(self.seller)
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
        self.seller = _make_user('seller@example.com')
        self.buyer = _make_user('buyer@example.com')
        self.listing = _make_listing(self.seller)
        _make_conversation(self.listing, self.buyer)
        self.deal = propose_deal(self.listing, self.seller, self.buyer.pk)

    def test_seller_can_cancel(self):
        deal = cancel_deal(self.deal, self.seller)
        self.assertEqual(deal.status, Deal.Status.CANCELLED)

    def test_buyer_can_cancel(self):
        deal = cancel_deal(self.deal, self.buyer)
        self.assertEqual(deal.status, Deal.Status.CANCELLED)

    def test_outsider_cannot_cancel(self):
        outsider = _make_user('outsider@example.com')
        with self.assertRaises(ValueError):
            cancel_deal(self.deal, outsider)

    def test_cannot_cancel_confirmed_deal(self):
        confirm_deal(self.deal, self.buyer)
        self.deal.refresh_from_db()
        with self.assertRaises(ValueError):
            cancel_deal(self.deal, self.seller)


class CreateReviewServiceTest(TestCase):

    def setUp(self):
        self.seller = _make_user('seller@example.com')
        self.buyer = _make_user('buyer@example.com')
        self.listing = _make_listing(self.seller)
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
        seller2 = _make_user('seller2@example.com')
        buyer2 = _make_user('buyer2@example.com')
        listing2 = _make_listing(seller2)
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
        self.seller = _make_user('seller@example.com')

    def _make_confirmed_deal_with_review(self, buyer_email, rating):
        buyer = _make_user(buyer_email)
        listing = _make_listing(self.seller)
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
        self.seller = _make_user('seller@example.com')
        self.buyer = _make_user('buyer@example.com')
        self.listing = _make_listing(self.seller)
        _make_conversation(self.listing, self.buyer)

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

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
        stranger = _make_user('stranger@example.com')
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
