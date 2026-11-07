from django.conf import settings
from django.db import transaction
from django.utils import timezone

from users.display import public_display_name

from .models import Deal, Review


def _listing_label(listing) -> str:
    return f'{listing.make} {listing.model} {listing.year}'


def _notify(user_id: int, ntype: str, context: dict):
    # Тексты - в NotificationTemplate (4.7, 06-C5); Telegram после коммита, ошибки в лог (06-Q5, 06-Q7).
    from notifications.services import notify
    notify(user_id, ntype, context, '/me/deals')


@transaction.atomic
def propose_deal(listing, seller, buyer_id: int) -> Deal:
    """
    Seller proposes a deal. Buyer must have a conversation about this listing.
    Returns the created Deal.
    Raises ValueError on validation errors.
    """
    from messaging.models import Conversation

    if listing.owner_id != seller.pk:
        raise ValueError('Тільки власник оголошення може запропонувати угоду.')
    if listing.owner_id == buyer_id:
        raise ValueError('Продавець і покупець не можуть бути однією особою.')

    # Buyer must have written about this listing
    buyer_talked = Conversation.objects.filter(
        local_listing=listing,
        initiator_id=buyer_id,
    ).exists()
    if not buyer_talked:
        raise ValueError('Покупець не писав по цьому оголошенню.')

    if Deal.objects.filter(listing=listing, buyer_id=buyer_id).exists():
        raise ValueError('Угода з цим покупцем вже існує для цього оголошення.')

    deal = Deal.objects.create(
        listing=listing,
        seller=seller,
        buyer_id=buyer_id,
    )

    _notify(buyer_id, 'deal_proposed', {'sender': public_display_name(seller), 'listing': _listing_label(listing)})
    return deal


@transaction.atomic
def confirm_deal(deal: Deal, buyer) -> Deal:
    """Buyer confirms the deal. Sets listing → sold."""
    if deal.buyer_id != buyer.pk:
        raise ValueError('Тільки покупець може підтвердити угоду.')
    if deal.status != Deal.Status.PROPOSED:
        raise ValueError('Угода не в статусі «Запропоновано».')

    deal.status = Deal.Status.CONFIRMED
    deal.confirmed_at = timezone.now()
    deal.save(update_fields=['status', 'confirmed_at'])

    # Mark listing as sold
    from local_listings.models import LocalListing
    LocalListing.objects.filter(pk=deal.listing_id).update(
        status=LocalListing.Status.SOLD
    )

    _notify(deal.seller_id, 'deal_confirmed', {'listing': _listing_label(deal.listing)})
    return deal


@transaction.atomic
def cancel_deal(deal: Deal, user) -> Deal:
    """Seller or buyer cancels the deal."""
    if user.pk not in (deal.seller_id, deal.buyer_id):
        raise ValueError('Тільки учасник угоди може її скасувати.')
    if deal.status == Deal.Status.CONFIRMED:
        raise ValueError('Підтверджену угоду не можна скасувати.')

    deal.status = Deal.Status.CANCELLED
    deal.save(update_fields=['status'])

    other_id = deal.seller_id if user.pk == deal.buyer_id else deal.buyer_id
    _notify(other_id, 'deal_cancelled', {'listing': _listing_label(deal.listing)})
    return deal


@transaction.atomic
def create_review(deal: Deal, author, rating: int, text: str = '') -> Review:
    """Buyer leaves a review after confirmed deal."""
    if deal.buyer_id != author.pk:
        raise ValueError('Залишити відгук може тільки покупець.')
    if deal.status != Deal.Status.CONFIRMED:
        raise ValueError('Відгук можна залишити тільки після підтвердженої угоди.')
    if hasattr(deal, 'review'):
        raise ValueError('Відгук на цю угоду вже залишено.')

    review = Review.objects.create(
        deal=deal,
        author=author,
        target_id=deal.seller_id,
        rating=rating,
        text=text,
    )

    _notify(deal.seller_id, 'review_received', {'rating': rating})
    return review


def seller_rating(seller_id: int) -> dict:
    """Returns seller rating info."""
    from django.db.models import Avg, Count
    threshold = getattr(settings, 'SELLER_BADGE_THRESHOLD', 3)

    confirmed_count = Deal.objects.filter(
        seller_id=seller_id, status=Deal.Status.CONFIRMED
    ).count()

    agg = Review.objects.filter(target_id=seller_id).aggregate(
        avg=Avg('rating'), cnt=Count('pk')
    )

    return {
        'confirmed_deal_count': confirmed_count,
        'review_count': agg['cnt'] or 0,
        'avg_rating': round(agg['avg'], 1) if agg['avg'] else None,
        'has_badge': confirmed_count >= threshold,
        'badge_threshold': threshold,
    }
