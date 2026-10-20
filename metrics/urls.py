from django.urls import path

from .views import MetricEventView

urlpatterns = [
    path('event/', MetricEventView.as_view(), name='metric-event'),
]
