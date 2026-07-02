from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Favorite
from .serializers import FavoriteSerializer


class FavoriteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Favorite.objects.filter(user=request.user).select_related(
            'local_listing',
            'imported_listing__vehicle',
        ).prefetch_related(
            'local_listing__images',
            'imported_listing__vehicle__images',
        )
        return Response(FavoriteSerializer(qs, many=True).data)

    def post(self, request):
        """Add to favorites. Body: {listing_type: 'local'|'imported', listing_id: <int>}"""
        listing_type = request.data.get('listing_type')
        listing_id = request.data.get('listing_id')
        if listing_type not in ('local', 'imported') or not listing_id:
            return Response({'detail': 'listing_type and listing_id required.'}, status=status.HTTP_400_BAD_REQUEST)

        kwargs = {'user': request.user}
        if listing_type == 'local':
            kwargs['local_listing_id'] = listing_id
        else:
            kwargs['imported_listing_id'] = listing_id

        try:
            fav, created = Favorite.objects.get_or_create(**kwargs)
        except IntegrityError:
            fav = Favorite.objects.filter(**kwargs).first()
            created = False

        return Response(
            FavoriteSerializer(fav).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request):
        """Remove from favorites. Body: {listing_type, listing_id}"""
        listing_type = request.data.get('listing_type')
        listing_id = request.data.get('listing_id')
        kwargs = {'user': request.user}
        if listing_type == 'local':
            kwargs['local_listing_id'] = listing_id
        else:
            kwargs['imported_listing_id'] = listing_id
        deleted, _ = Favorite.objects.filter(**kwargs).delete()
        return Response({'deleted': deleted > 0})


class FavoriteStatusView(APIView):
    """Check if current user has favorited a specific listing."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        listing_type = request.query_params.get('listing_type')
        listing_id = request.query_params.get('listing_id')
        if not listing_type or not listing_id:
            return Response({'is_favorite': False})
        kwargs = {'user': request.user}
        if listing_type == 'local':
            kwargs['local_listing_id'] = listing_id
        else:
            kwargs['imported_listing_id'] = listing_id
        return Response({'is_favorite': Favorite.objects.filter(**kwargs).exists()})
