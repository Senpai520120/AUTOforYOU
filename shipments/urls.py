from django.urls import path
from .views import ShipmentListView, ShipmentDetailView

urlpatterns = [
    path('', ShipmentListView.as_view(), name='shipment-list'),
    path('<int:pk>/', ShipmentDetailView.as_view(), name='shipment-detail'),
]
