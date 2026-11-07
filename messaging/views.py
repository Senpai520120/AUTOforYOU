from django.conf import settings
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from users.permissions import IsEmailVerified

from .exceptions import ContactsInTextError, ConversationClosed, RecipientDeleted
from .models import Conversation, Message
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
    incoming_q,
    mark_as_read,
    send_message_to_conversation,
    unread_count_for_user,
)
from .services import handles_imports as _handles_imports

CONTACTS_WARNING = (
    'Повідомлення містить контактні дані. '
    'Для безпеки угоди рекомендуємо спілкуватися на платформі.'
)


def _contacts_error(exc):
    # 06-Q1: ошибка содержимого - 400 у поля text, а не 500/403.
    return Response({'text': [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)


def _access_q(user):
    access = Q(participants=user)
    if _handles_imports(user):
        access |= Q(imported_listing__isnull=False)
    return access


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
        except ContactsInTextError as e:
            return _contacts_error(e)
        except ListingUnavailable as e:
            return Response({'detail': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {'conversation_id': conv.pk, 'created': created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ConversationPagination(PageNumberPagination):
    page_size = settings.REST_FRAMEWORK['PAGE_SIZE']


class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ConversationListSerializer(many=True))
    def get(self, request):
        """Фиксированное число запросов независимо от числа диалогов (06-Q6, E4)."""
        user = request.user
        visible = Conversation.objects.filter(_access_q(user)).values('pk')
        last_text = (
            Message.objects.filter(conversation=OuterRef('pk'))
            .order_by('-created_at', '-pk').values('text')[:1]
        )
        unread = (
            Message.objects.filter(incoming_q(user), conversation=OuterRef('pk'), read_at__isnull=True)
            .order_by().values('conversation')
            .annotate(c=Count('pk')).values('c')
        )
        qs = (
            Conversation.objects.filter(pk__in=visible)
            .select_related('local_listing', 'imported_listing__vehicle')
            .prefetch_related('participants')
            .annotate(
                last_text=Subquery(last_text),
                unread=Coalesce(Subquery(unread, output_field=IntegerField()), 0),
            )
            .order_by('-last_message_at', '-pk')
        )
        paginator = ConversationPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = ConversationListSerializer(page, many=True, context={'request': request}).data
        return paginator.get_paginated_response(data)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'messages_reply'

    def get_permissions(self):
        # Читать переписку можно и без подтверждения, писать - нет.
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsEmailVerified()]
        return super().get_permissions()

    def get_throttles(self):
        # 06-S6: ответы в диалоге - свой лимит messages_reply поверх общих anon/user.
        throttles = super().get_throttles()
        if self.request.method == 'POST':
            throttles.append(ScopedRateThrottle())
        return throttles

    def _get(self, pk, user):
        # Выборка только своих диалогов: чужой id неотличим от несуществующего (404)
        return get_object_or_404(
            Conversation.objects.filter(pk__in=Conversation.objects.filter(_access_q(user)).values('pk'))
            .select_related('local_listing', 'imported_listing__vehicle')
            .prefetch_related('participants'),
            pk=pk,
        )

    @extend_schema(
        parameters=[OpenApiParameter('before', OpenApiTypes.INT, description='id сообщения: порция более ранних')],
        responses=ConversationDetailSerializer,
    )
    def get(self, request, pk):
        conv = self._get(pk, request.user)
        before = request.query_params.get('before')
        if before is not None and not (before.isascii() and before.isdigit() and len(before) <= 18):
            return Response({'before': ['Очікується число.']}, status=status.HTTP_400_BAD_REQUEST)
        size = int(settings.MESSAGES_PAGE_SIZE)
        msgs = conv.messages.select_related('sender')
        if before is not None:
            msgs = msgs.filter(pk__lt=int(before))
        chunk = list(msgs.order_by('-pk')[:size + 1])
        has_earlier = len(chunk) > size
        chunk = chunk[:size][::-1]
        if before is None:
            mark_as_read(request.user, conv)
        data = ConversationDetailSerializer(
            conv, context={'request': request, 'messages': chunk, 'has_earlier': has_earlier},
        ).data
        return Response(data)

    def post(self, request, pk):
        conv = self._get(pk, request.user)
        sr = SendMessageSerializer(data=request.data)
        sr.is_valid(raise_exception=True)
        try:
            msg, detected = send_message_to_conversation(
                sender=request.user,
                conversation=conv,
                text=sr.validated_data['text'],
            )
        except ContactsInTextError as e:
            return _contacts_error(e)
        except RecipientDeleted as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ConversationClosed as e:
            return Response({'detail': str(e)}, status=status.HTTP_403_FORBIDDEN)
        except PermissionError as e:
            return Response({'detail': str(e)}, status=status.HTTP_403_FORBIDDEN)

        resp = MessageSerializer(msg).data
        if detected:
            resp['warning'] = CONTACTS_WARNING
        return Response(resp, status=status.HTTP_201_CREATED)


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'unread_count': unread_count_for_user(request.user)})
