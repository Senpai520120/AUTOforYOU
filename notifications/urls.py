from django.urls import path

from .views import MarkReadView, NotificationListView, UnreadCountView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications-list'),
    path('mark-read/', MarkReadView.as_view(), name='notifications-mark-read'),
    path('unread-count/', UnreadCountView.as_view(), name='notifications-unread-count'),
]
