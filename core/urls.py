from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from cars.views import CarListView, CustomsCalculatorView
from integrations.views import LotImportView, RegistryReportView, VinDecodeView, VinReportView
from listings.urls import b2b_urlpatterns
from users.urls import dealer_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('users.urls')),
    path('api/v1/vehicles/', include('vehicles.urls')),
    path('api/v1/vehicles/<str:vin>/report/', VinReportView.as_view(), name='vin-report'),
    path('api/v1/vehicles/<str:vin>/decode/', VinDecodeView.as_view(), name='vin-decode'),
    path('api/v1/vehicles/<str:vin>/registry/', RegistryReportView.as_view(), name='vin-registry'),
    path('api/v1/lots/import/', LotImportView.as_view(), name='lot-import'),
    path('api/v1/pricing/', include('pricing.urls')),
    path('api/v1/listings/', include('listings.urls')),
    path('api/v1/shipments/', include('shipments.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/v1/local/', include('local_listings.urls')),
    path('api/v1/messages/', include('messaging.urls')),
    path('api/v1/notifications/', include('notifications.urls')),
    path('api/v1/favorites/', include('favorites.urls')),
    path('api/v1/saved-searches/', include('saved_searches.urls')),
    path('api/v1/reports/', include('reports.urls')),
    path('api/v1/leads/', include('leads.urls')),
    path('api/v1/broker/', include('leads.broker_urls')),
    path('api/v1/deals/', include('deals.urls')),
    path('api/v1/site-settings/', include('site_settings.urls')),
    path('api/v1/monitoring/', include('core.monitoring_urls')),
    path('api/v1/telegram/', include('telegram_bot.urls')),
    path('api/v1/b2b/', include((b2b_urlpatterns, 'b2b'))),
    path('api/v1/dealers/', include((dealer_urlpatterns, 'dealers'))),
    # Legacy
    # cars/ не правим (Q7): публичность задаём здесь, как раньше давал AllowAny по умолчанию.
    # Пути и name те же, что в cars/urls.py.
    path('api/calculate/', CustomsCalculatorView.as_view(permission_classes=[AllowAny]), name='calculator'),
    path('api/list/', CarListView.as_view(permission_classes=[AllowAny]), name='car-list'),
    # OpenAPI / Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
