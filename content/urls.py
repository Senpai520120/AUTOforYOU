from django.urls import path

from .views import FaqView, HowItWorksView

urlpatterns = [
    path('how-it-works/', HowItWorksView.as_view(), name='content-how-it-works'),
    path('faq/', FaqView.as_view(), name='content-faq'),
]
