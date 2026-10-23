from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.modules import MODULE_FLAGS, module_enabled

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
        # Флаги не кэшируем: это значения из окружения, дешёвые и не должны залипать в кэше.
        data = {**data, **{f'{name}_enabled': module_enabled(name) for name in MODULE_FLAGS}}
        return Response(data)
