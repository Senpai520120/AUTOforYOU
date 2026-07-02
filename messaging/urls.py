from django.urls import path
from .views import (
    ConversationDetailView,
    ConversationListView,
    StartConversationView,
    UnreadCountView,
)

urlpatterns = [
    path('start/', StartConversationView.as_view(), name='msg-start'),
    path('conversations/', ConversationListView.as_view(), name='msg-conversations'),
    path('conversations/<int:pk>/', ConversationDetailView.as_view(), name='msg-detail'),
    path('unread-count/', UnreadCountView.as_view(), name='msg-unread-count'),
]
