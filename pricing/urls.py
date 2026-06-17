from django.urls import path
from .views import CalculateView, ActiveRatesView

urlpatterns = [
    path('calculate/', CalculateView.as_view(), name='pricing-calculate'),
    path('rates/', ActiveRatesView.as_view(), name='pricing-rates'),
]
