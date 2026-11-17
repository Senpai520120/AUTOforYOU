from rest_framework import generics, permissions
from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle

from users.permissions import IsEmailVerified

from .serializers import ReportCreateSerializer

TOO_MANY_REPORTS = 'Забагато скарг, спробуйте пізніше.'


class ReportCreateView(generics.CreateAPIView):
    """Жалоба на объявление (4.13, B8): только вошедший с подтверждённым email, свой лимит ``reports``."""
    serializer_class = ReportCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsEmailVerified]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = 'reports'

    def check_throttles(self, request):
        for throttle in self.get_throttles():
            if not throttle.allow_request(request, self):
                wait = throttle.wait()
                if isinstance(throttle, ScopedRateThrottle):
                    # Текст без английского «Expected available in…»; Retry-After остаётся.
                    exc = Throttled(detail=TOO_MANY_REPORTS)
                    exc.wait = None if wait is None else max(1, int(wait))
                    raise exc
                raise Throttled(wait=wait)
