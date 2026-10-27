from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FAQ_CACHE_KEY, FAQ_PLACES, HOW_IT_WORKS_CACHE_KEY, FaqItem, ImportStep, has_draft_marker
from .serializers import FaqItemSerializer, ImportStepSerializer

CACHE_TTL = 300


def _publishable(qs, *fields):
    """Активні записи без чернеткової позначки: захист, якщо запис увімкнено в обхід clean() (save/update/shell)."""
    return [o for o in qs.filter(is_active=True) if not has_draft_marker(*(getattr(o, f) for f in fields))]


class _PublicView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # Публічний кешований GET без ПДн. Throttle вимкнено: SSR Next ходить з однієї IP (підвал і сторінки
    # на кожному рендері), навантаження тримає кеш, а загальний ліміт запитів стоїть в nginx.
    throttle_classes = []


class HowItWorksView(_PublicView):
    """GET /api/v1/content/how-it-works/ - активні етапи й FAQ; published=false, якщо етапів немає."""

    def get(self, request):
        data = cache.get(HOW_IT_WORKS_CACHE_KEY)
        if data is None:
            steps = ImportStepSerializer(_publishable(ImportStep.objects.all(), *ImportStep.text_fields), many=True).data
            faq = FaqItemSerializer(_publishable(FaqItem.objects.all(), *FaqItem.text_fields), many=True).data
            data = {'published': bool(steps), 'steps': list(steps), 'faq': list(faq)}
            cache.set(HOW_IT_WORKS_CACHE_KEY, data, CACHE_TTL)
        return Response(data)


class FaqView(_PublicView):
    """GET /api/v1/content/faq/?place=calculator - FAQ з прапорцем show_on_calculator."""

    def get(self, request):
        place = request.query_params.get('place', '')
        if place not in FAQ_PLACES:
            return Response({'faq': []})
        key = FAQ_CACHE_KEY.format(place=place)
        data = cache.get(key)
        if data is None:
            items = _publishable(FaqItem.objects.filter(show_on_calculator=True), *FaqItem.text_fields)
            data = {'faq': list(FaqItemSerializer(items, many=True).data)}
            cache.set(key, data, CACHE_TTL)
        return Response(data)
