from django.urls import path

from .monitoring_views import ClientErrorView

urlpatterns = [
    path('client-errors/', ClientErrorView.as_view(), name='monitoring-client-errors'),
]
