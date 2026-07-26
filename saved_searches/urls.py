from django.urls import path

from .views import SavedSearchDetailView, SavedSearchListView

urlpatterns = [
    path('', SavedSearchListView.as_view(), name='saved-searches-list'),
    path('<int:pk>/', SavedSearchDetailView.as_view(), name='saved-searches-detail'),
]
