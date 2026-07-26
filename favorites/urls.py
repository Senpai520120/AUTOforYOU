from django.urls import path

from .views import FavoriteListView, FavoriteStatusView

urlpatterns = [
    path('', FavoriteListView.as_view(), name='favorites-list'),
    path('status/', FavoriteStatusView.as_view(), name='favorites-status'),
]
