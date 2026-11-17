from django.urls import path

from .views import ShipmentDetailView, ShipmentListView, TrackingEventPhotoView

urlpatterns = [
    path('', ShipmentListView.as_view(), name='shipment-list'),
    path('<int:pk>/', ShipmentDetailView.as_view(), name='shipment-detail'),
    path('<int:pk>/events/<int:event_id>/photo/', TrackingEventPhotoView.as_view(), name='tracking-event-photo'),
]
