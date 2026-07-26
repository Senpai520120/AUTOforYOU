from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer
from .services import unread_count


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user)[:50]
        return Response(NotificationSerializer(qs, many=True).data)


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Body: {id: <int>} or {all: true}"""
        if request.data.get('all'):
            Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            return Response({'marked': 'all'})
        nid = request.data.get('id')
        if nid:
            Notification.objects.filter(user=request.user, pk=nid).update(is_read=True)
            return Response({'marked': nid})
        return Response({'detail': 'Provide id or all=true.'}, status=status.HTTP_400_BAD_REQUEST)


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'unread_count': unread_count(request.user.pk)})
