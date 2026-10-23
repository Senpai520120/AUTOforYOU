from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from users.permissions import IsEmailVerified

from .models import Conversation
from .serializers import (
    ConversationDetailSerializer,
    ConversationListSerializer,
    MessageSerializer,
    SendMessageSerializer,
    StartConversationSerializer,
)
from .services import (
    ListingUnavailable,
    get_or_create_conversation,
    mark_as_read,
    send_message_to_conversation,
    unread_count_for_user,
)
from .services import handles_imports as _handles_imports


class StartConversationView(APIView):
    permission_classes = [IsAuthenticated, IsEmailVerified]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'messages'

    def post(self, request):
        sr = StartConversationSerializer(data=request.data)
        sr.is_valid(raise_exception=True)
        try:
            conv, created, _ = get_or_create_conversation(
                initiator=request.user,
                listing_type=sr.validated_data['listing_type'],
                listing_id=sr.validated_data['listing_id'],
                first_text=sr.validated_data['text'],
            )
        except ListingUnavailable as e:
            return Response({'detail': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {'conversation_id': conv.pk, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ConversationListSerializer(many=True))
    def get(self, request):
        user = request.user
        if _handles_imports(user):
            qs = Conversation.objects.filter(
                Q(participants=user) | Q(imported_listing__isnull=False)
            ).distinct()
        else:
            qs = Conversation.objects.filter(participants=user)

        qs = qs.order_by('-last_message_at').prefetch_related(
            'participants', 'messages__sender',
            'local_listing', 'imported_listing__vehicle',
        )
        return Response(
            ConversationListSerializer(qs, many=True, context={'request': request}).data
        )


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Читать переписку можно и без подтверждения, писать - нет.
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsEmailVerified()]
        return super().get_permissions()

    def _get(self, pk, user):
        # Выборка только своих диалогов: чужой id неотличим от несуществующего (404)
        access = Q(participants=user)
        if _handles_imports(user):
            access |= Q(imported_listing__isnull=False)
        conv = get_object_or_404(
            Conversation.objects.filter(access).distinct().prefetch_related(
                'participants', 'messages__sender',
                'local_listing', 'imported_listing__vehicle',
            ),
            pk=pk,
        )
        return conv, None

    @extend_schema(responses=ConversationDetailSerializer)
    def get(self, request, pk):
        conv, err = self._get(pk, request.user)
        if err:
            return err
        mark_as_read(request.user, conv)
        return Response(ConversationDetailSerializer(conv, context={'request': request}).data)

    def post(self, request, pk):
        conv, err = self._get(pk, request.user)
        if err:
            return err

        sr = SendMessageSerializer(data=request.data)
        sr.is_valid(raise_exception=True)
        try:
            msg, detected = send_message_to_conversation(
                sender=request.user,
                conversation=conv,
                text=sr.validated_data['text'],
            )
        except PermissionError as e:
            return Response({'detail': str(e)}, status=status.HTTP_403_FORBIDDEN)

        resp = MessageSerializer(msg).data
        if detected:
            resp['warning'] = (
                'Повідомлення містить контактні дані. '
                'Для безпеки угоди рекомендуємо спілкуватися на платформі.'
            )
        return Response(resp, status=status.HTTP_201_CREATED)


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'unread_count': unread_count_for_user(request.user)})
