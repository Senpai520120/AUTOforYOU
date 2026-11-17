from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer
from .services import unread_count


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=NotificationSerializer(many=True))
    def get(self, request):
        # 06-C7: пагинация вместо среза [:50].
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(Notification.objects.filter(user=request.user), request, view=self)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)


class MarkReadSerializer(serializers.Serializer):
    id = serializers.IntegerField(min_value=1, required=False)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get('all') and attrs.get('id') is None:
            raise serializers.ValidationError('Вкажіть id або all=true.')
        return attrs


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=MarkReadSerializer,
        responses=inline_serializer('MarkReadResult', {'marked': serializers.IntegerField()}),
    )
    def post(self, request):
        """Body: {id: <int>} or {all: true}. Ответ {"marked": <число отмеченных>} (06-Q8, E7)."""
        sr = MarkReadSerializer(data=request.data)
        if not sr.is_valid():
            return Response(sr.errors, status=status.HTTP_400_BAD_REQUEST)
        qs = Notification.objects.filter(user=request.user, is_read=False)
        if not sr.validated_data.get('all'):
            qs = qs.filter(pk=sr.validated_data['id'])
        return Response({'marked': qs.update(is_read=True)})


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'unread_count': unread_count(request.user.pk)})
