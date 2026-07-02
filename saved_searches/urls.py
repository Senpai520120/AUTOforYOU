from django.urls import path
from .views import SavedSearchListView, SavedSearchDetailView

urlpatterns = [
    path('', SavedSearchListView.as_view(), name='saved-searches-list'),
    path('<int:pk>/', SavedSearchDetailView.as_view(), name='saved-searches-detail'),
]
