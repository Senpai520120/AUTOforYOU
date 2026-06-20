from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from listings.urls import b2b_urlpatterns
from integrations.views import VinReportView, VinDecodeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/vehicles/', include('vehicles.urls')),
    path('api/v1/vehicles/<str:vin>/report/', VinReportView.as_view(), name='vin-report'),
    path('api/v1/vehicles/<str:vin>/decode/', VinDecodeView.as_view(), name='vin-decode'),
    path('api/v1/pricing/', include('pricing.urls')),
    path('api/v1/listings/', include('listings.urls')),
    path('api/v1/shipments/', include('shipments.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/v1/b2b/', include((b2b_urlpatterns, 'b2b'))),
    # Legacy
    path('api/', include('cars.urls')),
    # OpenAPI / Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
