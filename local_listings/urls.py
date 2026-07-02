from django.urls import path
from .views import (
    LocalListingListCreateView,
    LocalListingDetailView,
    MyListingsView,
    VinPrefillView,
    RegionListView,
    CityListView,
    LocalListingImageUploadView,
    LocalListingImageDetailView,
    PromotionTariffListView,
    LocalListingPromoteView,
)

urlpatterns = [
    path('listings/', LocalListingListCreateView.as_view(), name='local-listing-list'),
    path('listings/<int:pk>/', LocalListingDetailView.as_view(), name='local-listing-detail'),
    path('listings/<int:pk>/images/', LocalListingImageUploadView.as_view(), name='local-listing-images'),
    path('listings/<int:pk>/images/<int:img_id>/', LocalListingImageDetailView.as_view(), name='local-listing-image-detail'),
    path('listings/<int:pk>/promote/', LocalListingPromoteView.as_view(), name='local-listing-promote'),
    path('my-listings/', MyListingsView.as_view(), name='local-my-listings'),
    path('tariffs/', PromotionTariffListView.as_view(), name='local-tariffs'),
    path('vin-prefill/<str:vin>/', VinPrefillView.as_view(), name='local-vin-prefill'),
    path('regions/', RegionListView.as_view(), name='local-regions'),
    path('regions/<int:region_id>/cities/', CityListView.as_view(), name='local-cities'),
]
