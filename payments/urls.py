from django.urls import path

from .views import LiqPayCallbackView, LiqPayCheckoutView

urlpatterns = [
    path('liqpay/checkout/', LiqPayCheckoutView.as_view(), name='liqpay-checkout'),
    path('liqpay/callback/', LiqPayCallbackView.as_view(), name='liqpay-callback'),
]
