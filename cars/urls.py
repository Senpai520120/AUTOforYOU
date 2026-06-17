from django.urls import path
from .views import CustomsCalculatorView, CarListView

urlpatterns = [
    path('calculate/', CustomsCalculatorView.as_view(), name='calculator'),
    path('list/', CarListView.as_view(), name='car-list'),
]
