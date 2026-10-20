"""Выгрузка «Мої дані» (задача 1.8): все данные пользователя одним JSON.

Только записи самого пользователя. Контрагенты (собеседник, вторая сторона сделки,
автор отзыва, тот, на кого жалоба) - только отображаемым именем, без email и телефона.
Служебные поля брокера/модератора и сырые ответы платёжного сервиса не выгружаются.
Новая модель с данными пользователя - новый раздел здесь (список сверяется с политикой, 1.12).
"""
from django.utils import timezone

from .display import public_display_name

EXPORT_FORMAT_VERSION = 1


def _rows(qs, *fields):
    return list(qs.values(*fields))


def _listing_title(listing):
    if listing is None:
        return ''
    return f'{listing.make} {listing.model} {listing.year}'


def _vehicle_title(listing):
    if listing is None:
        return ''
    v = listing.vehicle
    return f'{v.make} {v.model} {v.year}'


def _profile(user):
    return {
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'phone': user.phone,
        'role': user.role,
        'is_verified_dealer': user.is_verified_dealer,
        'is_email_verified': user.is_email_verified,
        'telegram_linked': user.telegram_id is not None,
        'created_at': user.created_at,
        'agreed_to_terms_at': user.agreed_to_terms_at,
        'deletion_scheduled_at': user.deletion_scheduled_at,
    }


def _local_listings(user):
    from local_listings.models import LocalListing

    result = []
    qs = LocalListing.objects.filter(owner=user).select_related('region', 'city').prefetch_related('images')
    for ll in qs.order_by('pk'):
        result.append({
            'id': ll.pk, 'make': ll.make, 'model': ll.model, 'year': ll.year,
            'mileage_km': ll.mileage_km, 'engine_cc': ll.engine_cc, 'fuel_type': ll.fuel_type,
            'transmission': ll.transmission, 'body_type': ll.body_type, 'condition': ll.condition,
            'price': ll.price, 'currency': ll.currency, 'price_type': ll.price_type,
            'region': ll.region.name, 'city': ll.city.name, 'description': ll.description,
            'status': ll.status, 'seller_type': ll.seller_type, 'contact_phone': ll.contact_phone,
            'rejection_reason': ll.rejection_reason, 'agreed_to_rules_at': ll.agreed_to_rules_at,
            'expires_at': ll.expires_at, 'promoted_until': ll.promoted_until,
            'created_at': ll.created_at, 'updated_at': ll.updated_at,
            'photos': [img.image.url if img.image else img.source_url for img in ll.images.all()],
        })
    return result


def _imported_listings(user):
    from listings.models import Listing

    return [
        {
            'id': lst.pk, 'vehicle': _vehicle_title(lst), 'vin': lst.vehicle.vin, 'price': lst.price,
            'currency': lst.currency, 'channel': lst.channel, 'status': lst.status,
            'created_at': lst.created_at,
        }
        for lst in Listing.objects.filter(seller=user).select_related('vehicle').order_by('pk')
    ]


def _conversations(user):
    from messaging.models import Conversation

    qs = (
        Conversation.objects.filter(participants=user)
        .select_related('local_listing', 'imported_listing__vehicle')
        .prefetch_related('participants', 'messages__sender')
        .order_by('pk')
    )
    result = []
    for conv in qs:
        if conv.local_listing_id:
            subject = _listing_title(conv.local_listing)
        elif conv.imported_listing_id:
            subject = _vehicle_title(conv.imported_listing)
        else:
            subject = ''
        result.append({
            'id': conv.pk,
            'subject': subject,
            'with': [public_display_name(p) for p in conv.participants.all() if p.pk != user.pk],
            'messages': [
                {
                    'from': 'я' if m.sender_id == user.pk else public_display_name(m.sender),
                    'text': m.text, 'created_at': m.created_at, 'read_at': m.read_at,
                }
                for m in conv.messages.all()
            ],
        })
    return result


def _deals(user):
    from django.db.models import Q

    from deals.models import Deal

    qs = (
        Deal.objects.filter(Q(seller=user) | Q(buyer=user))
        .select_related('listing', 'seller', 'buyer').order_by('pk')
    )
    result = []
    for deal in qs:
        as_seller = deal.seller_id == user.pk
        other = deal.buyer if as_seller else deal.seller
        result.append({
            'id': deal.pk, 'role': 'seller' if as_seller else 'buyer',
            'counterparty': public_display_name(other), 'listing': _listing_title(deal.listing),
            'status': deal.status, 'created_at': deal.created_at, 'confirmed_at': deal.confirmed_at,
        })
    return result


def _reviews(user):
    from deals.models import Review

    written = [
        {'deal_id': r.deal_id, 'about': public_display_name(r.target), 'rating': r.rating,
         'text': r.text, 'created_at': r.created_at}
        for r in Review.objects.filter(author=user).select_related('target').order_by('pk')
    ]
    received = [
        {'deal_id': r.deal_id, 'author': public_display_name(r.author), 'rating': r.rating,
         'text': r.text, 'created_at': r.created_at}
        for r in Review.objects.filter(target=user).select_related('author').order_by('pk')
    ]
    return written, received


def _reports_filed(user):
    from reports.models import Report

    return [
        {
            'id': r.pk, 'listing_id': r.listing_id,
            'about_user': public_display_name(r.reported_user) if r.reported_user_id else '',
            'reason': r.reason, 'comment': r.comment, 'status': r.status, 'created_at': r.created_at,
        }
        for r in Report.objects.filter(reporter=user).select_related('reported_user').order_by('pk')
    ]


def build_user_export(user) -> dict:
    from favorites.models import Favorite
    from leads.models import Lead
    from notifications.models import Notification
    from payments.models import Payment
    from pricing.models import Calculation
    from saved_searches.models import SavedSearch

    from .models import ConsentRecord, DealerApplication, TrustedShop

    reviews_written, reviews_received = _reviews(user)
    return {
        'format_version': EXPORT_FORMAT_VERSION,
        'exported_at': timezone.now(),
        'profile': _profile(user),
        'consents': _rows(
            ConsentRecord.objects.filter(user=user).order_by('given_at', 'pk'),
            'document', 'doc_version', 'given_at', 'method', 'lead_public_id', 'partner_name',
        ),
        'trusted_shops': _rows(
            TrustedShop.objects.filter(owner=user).order_by('pk'),
            'name', 'type', 'contacts', 'rating', 'notes', 'created_at', 'updated_at',
        ),
        'dealer_applications': _rows(
            DealerApplication.objects.filter(user=user).order_by('pk'),
            'company_name', 'full_name', 'contact_phone', 'documents', 'status', 'review_notes',
            'agreed_to_processing_at', 'created_at', 'reviewed_at',
        ),
        'calculations': _rows(
            Calculation.objects.filter(user=user).order_by('pk'),
            'id', 'inputs_snapshot', 'breakdown', 'total_usd', 'total_uah', 'is_estimate', 'created_at',
        ),
        'watched_shipments': _rows(
            user.watched_shipments.order_by('pk'), 'container_no', 'status', 'eta', 'arrival_port_eu',
        ),
        'leads': _rows(
            Lead.objects.filter(user=user).order_by('pk'),
            'public_id', 'name', 'phone', 'email', 'contact_method', 'contact_handle', 'comment',
            'source', 'budget_usd', 'needed_when', 'city', 'vehicle_label', 'total_usd', 'total_uah',
            'status', 'consent_at', 'partner_name', 'partner_consent_at', 'created_at', 'updated_at',
        ),
        'local_listings': _local_listings(user),
        'imported_listings': _imported_listings(user),
        'favorites': _rows(
            Favorite.objects.filter(user=user).order_by('pk'),
            'local_listing_id', 'imported_listing_id', 'created_at',
        ),
        'saved_searches': _rows(
            SavedSearch.objects.filter(user=user).order_by('pk'),
            'name', 'filters', 'notify', 'last_notified_at', 'created_at',
        ),
        'notifications': _rows(
            Notification.objects.filter(user=user).order_by('pk'),
            'type', 'title', 'text', 'link', 'is_read', 'created_at',
        ),
        'conversations': _conversations(user),
        'deals': _deals(user),
        'reviews_written': reviews_written,
        'reviews_received': reviews_received,
        'reports_filed': _reports_filed(user),
        'payments': _rows(
            Payment.objects.filter(user=user).order_by('pk'),
            'order_id', 'amount', 'currency', 'description', 'purpose', 'status', 'created_at', 'updated_at',
        ),
    }
