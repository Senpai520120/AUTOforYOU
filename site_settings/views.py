from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PUBLIC_CACHE_KEY, SiteSettings
from .serializers import PublicSiteSettingsSerializer

CACHE_TTL = 300


class SiteSettingsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        data = cache.get(PUBLIC_CACHE_KEY)
        if data is None:
            data = dict(PublicSiteSettingsSerializer(SiteSettings.load()).data)
            cache.set(PUBLIC_CACHE_KEY, data, CACHE_TTL)
        return Response(data)
