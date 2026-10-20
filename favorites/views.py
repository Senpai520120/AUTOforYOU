from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules import module_enabled

from .models import Favorite
from .serializers import FavoriteSerializer


def _lots_frozen(listing_type) -> bool:
    """2.8: операции с лотами (imported) при LOTS_ENABLED=false - 404; C2C (local) не затронуто."""
    return listing_type != 'local' and not module_enabled('lots')


def _not_found():
    return Response({'detail': 'Не знайдено.'}, status=status.HTTP_404_NOT_FOUND)


class FavoriteListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Favorite.objects.filter(user=request.user)
        if not module_enabled('lots'):  # 2.8: лоты заморожены - в списке только C2C
            qs = qs.filter(imported_listing__isnull=True)
        qs = qs.select_related(
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
        if _lots_frozen(listing_type):
            return _not_found()

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
        if _lots_frozen(listing_type):
            return _not_found()
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
        if _lots_frozen(listing_type):
            return _not_found()
        kwargs = {'user': request.user}
        if listing_type == 'local':
            kwargs['local_listing_id'] = listing_id
        else:
            kwargs['imported_listing_id'] = listing_id
        return Response({'is_favorite': Favorite.objects.filter(**kwargs).exists()})
