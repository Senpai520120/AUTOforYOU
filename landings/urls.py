from django.urls import path

from .views import LandingDetailView, LandingListView

urlpatterns = [
    path('', LandingListView.as_view(), name='landing-list'),
    path('<slug:slug>/', LandingDetailView.as_view(), name='landing-detail'),
]
