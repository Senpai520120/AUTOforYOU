from django.urls import path

from .views import TelegramLinkTokenView, TelegramWebhookView

urlpatterns = [
    path('link-token/', TelegramLinkTokenView.as_view(), name='telegram-link-token'),
    path('webhook/', TelegramWebhookView.as_view(), name='telegram-webhook'),
]
