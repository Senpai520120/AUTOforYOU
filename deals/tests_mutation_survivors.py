"""deals/services.py: тесты против выживших мутантов cosmic-ray (scripts/mutation.sh deals).

- транзакции: ошибка после записи откатывает сделку/объявление/отзыв (без @transaction.atomic - нет);
- проверки участников - по равенству id, а не по порядку (пользователь с меньшим pk);
- уведомление об отмене уходит второй стороне; округление рейтинга; порог бейджа включительно.
"""
from unittest.mock import patch

from django.test import TestCase, override_settings

from local_listings.models import LocalListing
from messaging.models import Conversation
from tests.factories import make_local_listing, make_user

from .models import Deal, Review
from .services import cancel_deal, confirm_deal, create_review, propose_deal, seller_rating


class _DealBase(TestCase):
    def setUp(self):
        # Порядок создания задаёт pk: «чужой» и «покупатель» меньше продавца.
        self.stranger = make_user()
        self.buyer = make_user()
        self.seller = make_user()
        self.listing = make_local_listing(self.seller)
        Conversation.objects.create(local_listing=self.listing, initiator=self.buyer)

    def _deal(self, status=Deal.Status.PROPOSED):
        return Deal.objects.create(listing=self.listing, seller=self.seller, buyer=self.buyer, status=status)


class ParticipantChecksTests(_DealBase):
    def test_non_owner_with_lower_pk_cannot_propose(self):
        with self.assertRaisesMessage(ValueError, 'Тільки власник оголошення'):
            propose_deal(self.listing, self.stranger, self.buyer.pk)

    def test_buyer_with_lower_pk_than_owner_can_get_deal(self):
        deal = propose_deal(self.listing, self.seller, self.buyer.pk)
        self.assertEqual(deal.buyer_id, self.buyer.pk)

    def test_lower_pk_stranger_cannot_confirm(self):
        buyer2 = make_user()  # покупатель с большим pk, чужой - с меньшим
        Conversation.objects.create(local_listing=self.listing, initiator=buyer2)
        deal = Deal.objects.create(listing=self.listing, seller=self.seller, buyer=buyer2)
        with self.assertRaisesMessage(ValueError, 'Тільки покупець може підтвердити'):
            confirm_deal(deal, self.stranger)

    def test_lower_pk_stranger_cannot_review(self):
        buyer2 = make_user()
        deal = Deal.objects.create(listing=self.listing, seller=self.seller, buyer=buyer2,
                                   status=Deal.Status.CONFIRMED)
        with self.assertRaisesMessage(ValueError, 'Залишити відгук може тільки покупець'):
            create_review(deal, self.stranger, 5)

    def test_higher_pk_stranger_cannot_confirm_or_review(self):
        late = make_user()  # pk больше покупателя
        with self.assertRaisesMessage(ValueError, 'Тільки покупець може підтвердити'):
            confirm_deal(self._deal(), late)
        deal = Deal.objects.create(listing=make_local_listing(self.seller), seller=self.seller, buyer=self.buyer,
                                   status=Deal.Status.CONFIRMED)
        with self.assertRaisesMessage(ValueError, 'Залишити відгук може тільки покупець'):
            create_review(deal, late, 5)

    @patch('deals.services._notify')
    def test_lower_pk_seller_cancels_buyer_notified(self, notify):
        # Продавец с pk меньше покупателя: «кто отменил» - по равенству, а не по порядку id.
        listing = make_local_listing(self.stranger)
        deal = Deal.objects.create(listing=listing, seller=self.stranger, buyer=self.buyer)
        cancel_deal(deal, self.stranger)
        self.assertEqual(notify.call_args.args[:2], (self.buyer.pk, 'deal_cancelled'))

    def test_no_review_for_cancelled_deal(self):
        deal = self._deal(Deal.Status.CANCELLED)
        with self.assertRaisesMessage(ValueError, 'тільки після підтвердженої угоди'):
            create_review(deal, self.buyer, 5)


@patch('deals.services._notify', side_effect=RuntimeError('notify down'))
class AtomicRollbackTests(_DealBase):
    """Ошибка уведомления в конце сервиса откатывает всё, что он успел записать."""

    def test_propose_rolls_back(self, _notify):
        with self.assertRaisesMessage(RuntimeError, 'notify down'):
            propose_deal(self.listing, self.seller, self.buyer.pk)
        self.assertFalse(Deal.objects.exists())

    def test_confirm_rolls_back_deal_and_listing(self, _notify):
        deal = self._deal()
        with self.assertRaisesMessage(RuntimeError, 'notify down'):
            confirm_deal(deal, self.buyer)
        deal.refresh_from_db()
        self.listing.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.PROPOSED)
        self.assertEqual(self.listing.status, LocalListing.Status.ACTIVE)

    def test_cancel_rolls_back(self, _notify):
        deal = self._deal()
        with self.assertRaisesMessage(RuntimeError, 'notify down'):
            cancel_deal(deal, self.buyer)
        deal.refresh_from_db()
        self.assertEqual(deal.status, Deal.Status.PROPOSED)

    def test_review_rolls_back(self, _notify):
        deal = self._deal(Deal.Status.CONFIRMED)
        with self.assertRaisesMessage(RuntimeError, 'notify down'):
            create_review(deal, self.buyer, 5)
        self.assertFalse(Review.objects.exists())


class CancelNotifiesOtherSideTests(_DealBase):
    @patch('deals.services._notify')
    def test_buyer_cancels_seller_notified(self, notify):
        cancel_deal(self._deal(), self.buyer)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[:2], (self.seller.pk, 'deal_cancelled'))

    @patch('deals.services._notify')
    def test_seller_cancels_buyer_notified(self, notify):
        cancel_deal(self._deal(), self.seller)
        self.assertEqual(notify.call_args.args[:2], (self.buyer.pk, 'deal_cancelled'))


class SellerRatingTests(_DealBase):
    def _reviews(self, *ratings):
        for r in ratings:
            buyer = make_user()
            listing = make_local_listing(self.seller)
            deal = Deal.objects.create(listing=listing, seller=self.seller, buyer=buyer,
                                       status=Deal.Status.CONFIRMED)
            Review.objects.create(deal=deal, author=buyer, target=self.seller, rating=r)

    def test_avg_rating_rounded_to_one_decimal(self):
        self._reviews(5, 4, 4)  # 4.333...
        self.assertEqual(seller_rating(self.seller.pk)['avg_rating'], 4.3)

    @override_settings(SELLER_BADGE_THRESHOLD=2)
    def test_badge_from_threshold_inclusive_and_above(self):
        self._reviews(5, 5)
        self.assertIs(seller_rating(self.seller.pk)['has_badge'], True)
        self._reviews(5)  # 3 > 2: бейдж остаётся
        info = seller_rating(self.seller.pk)
        self.assertEqual((info['confirmed_deal_count'], info['has_badge']), (3, True))

    def test_default_threshold_is_three(self):
        with self.settings():
            from django.conf import settings
            del settings.SELLER_BADGE_THRESHOLD
            self.assertEqual(seller_rating(self.seller.pk)['badge_threshold'], 3)
