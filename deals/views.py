from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from local_listings.models import LocalListing

from .models import Deal
from .serializers import (
    DealSerializer,
    ProposeDealSerializer,
    ReviewCreateSerializer,
    SellerRatingSerializer,
)
from .services import cancel_deal, confirm_deal, create_review, propose_deal, seller_rating


class DealListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        deals = (
            Deal.objects.filter(seller=user) | Deal.objects.filter(buyer=user)
        ).distinct().select_related('listing', 'seller', 'buyer').prefetch_related('review').order_by('-created_at')
        return Response(DealSerializer(deals, many=True).data)

    def post(self, request):
        sr = ProposeDealSerializer(data=request.data)
        sr.is_valid(raise_exception=True)
        listing_id = request.data.get('listing_id')
        listing = get_object_or_404(LocalListing, pk=listing_id)
        try:
            deal = propose_deal(listing, request.user, sr.validated_data['buyer_id'])
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DealSerializer(deal).data, status=status.HTTP_201_CREATED)


class DealConfirmView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        try:
            deal = confirm_deal(deal, request.user)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DealSerializer(deal).data)


class DealCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        deal = get_object_or_404(Deal, pk=pk)
        try:
            deal = cancel_deal(deal, request.user)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DealSerializer(deal).data)


class DealReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        deal = get_object_or_404(Deal.objects.prefetch_related('review'), pk=pk)
        sr = ReviewCreateSerializer(data=request.data)
        sr.is_valid(raise_exception=True)
        try:
            review = create_review(
                deal, request.user,
                sr.validated_data['rating'],
                sr.validated_data['text'],
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        from .serializers import ReviewSerializer
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class SellerRatingView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, user_id):
        data = seller_rating(user_id)
        return Response(SellerRatingSerializer(data).data)


class ListingBuyersView(APIView):
    """Returns list of users who initiated conversations about a listing (for seller to choose buyer)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, listing_id):
        listing = get_object_or_404(LocalListing, pk=listing_id)
        if listing.owner_id != request.user.pk and not request.user.is_staff:
            return Response({'detail': 'Тільки власник може переглядати покупців.'}, status=403)
        from messaging.models import Conversation
        convs = Conversation.objects.filter(local_listing=listing).select_related('initiator')
        buyers = [
            {'id': c.initiator.pk, 'email': c.initiator.email,
             'first_name': c.initiator.first_name, 'last_name': c.initiator.last_name}
            for c in convs
            if c.initiator_id != listing.owner_id
        ]
        return Response(buyers)
