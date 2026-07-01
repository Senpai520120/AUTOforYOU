from django.urls import path
from .views import (
    LocalListingListCreateView,
    LocalListingDetailView,
    VinPrefillView,
    RegionListView,
    CityListView,
)

urlpatterns = [
    path('listings/', LocalListingListCreateView.as_view(), name='local-listing-list'),
    path('listings/<int:pk>/', LocalListingDetailView.as_view(), name='local-listing-detail'),
    path('vin-prefill/<str:vin>/', VinPrefillView.as_view(), name='local-vin-prefill'),
    path('regions/', RegionListView.as_view(), name='local-regions'),
    path('regions/<int:region_id>/cities/', CityListView.as_view(), name='local-cities'),
]
