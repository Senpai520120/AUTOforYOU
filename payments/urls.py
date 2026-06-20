from django.urls import path
from .views import LiqPayCheckoutView, LiqPayCallbackView

urlpatterns = [
    path('liqpay/checkout/', LiqPayCheckoutView.as_view(), name='liqpay-checkout'),
    path('liqpay/callback/', LiqPayCallbackView.as_view(), name='liqpay-callback'),
]
