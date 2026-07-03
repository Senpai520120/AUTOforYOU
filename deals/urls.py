from django.urls import path
from .views import (
    DealListCreateView,
    DealConfirmView,
    DealCancelView,
    DealReviewView,
    SellerRatingView,
    ListingBuyersView,
)

urlpatterns = [
    path('', DealListCreateView.as_view(), name='deal-list-create'),
    path('<int:pk>/confirm/', DealConfirmView.as_view(), name='deal-confirm'),
    path('<int:pk>/cancel/', DealCancelView.as_view(), name='deal-cancel'),
    path('<int:pk>/review/', DealReviewView.as_view(), name='deal-review'),
    path('seller-rating/<int:user_id>/', SellerRatingView.as_view(), name='seller-rating'),
    path('listing-buyers/<int:listing_id>/', ListingBuyersView.as_view(), name='listing-buyers'),
]
