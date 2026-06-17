from django.urls import path
from .views import ListingListView, ListingDetailView, ListingCreateView, B2BBoardView

urlpatterns = [
    path('', ListingListView.as_view(), name='listing-list'),
    path('<int:pk>/', ListingDetailView.as_view(), name='listing-detail'),
    path('create/', ListingCreateView.as_view(), name='listing-create'),
]

b2b_urlpatterns = [
    path('board/', B2BBoardView.as_view(), name='b2b-board'),
]
