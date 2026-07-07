from django.urls import path

from .views import TelegramLinkTokenView, TelegramUnlinkView, TelegramWebhookView

urlpatterns = [
    path('link-token/', TelegramLinkTokenView.as_view(), name='telegram-link-token'),
    path('link/', TelegramUnlinkView.as_view(), name='telegram-unlink'),
    path('webhook/', TelegramWebhookView.as_view(), name='telegram-webhook'),
]
