from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules import module_flags

from .models import PUBLIC_CACHE_KEY, SiteSettings
from .serializers import PublicSiteSettingsSerializer

CACHE_TTL = 300


class SiteSettingsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # Публичный, кэшируемый (5 мин) GET без ПДн. Его дёргает баннер cookie на каждой загрузке
    # страницы; общий anon-лимит (60/час на IP) съедался бы им и ломал остальные запросы.
    throttle_classes = []

    def get(self, request):
        data = cache.get(PUBLIC_CACHE_KEY)
        if data is None:
            data = dict(PublicSiteSettingsSerializer(SiteSettings.load()).data)
            cache.set(PUBLIC_CACHE_KEY, data, CACHE_TTL)
        # 2.8: флаги модулей - из .env (только чтение), не из модели и не из кэша
        return Response({**data, **module_flags()})
