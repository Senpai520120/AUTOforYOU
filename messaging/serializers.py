from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Conversation, Message

User = get_user_model()


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'sender', 'sender_name', 'text', 'created_at', 'read_at']

    def get_sender_name(self, obj):
        return obj.sender.first_name or obj.sender.email.split('@')[0]


class ConversationListSerializer(serializers.ModelSerializer):
    subject_title = serializers.SerializerMethodField()
    subject_url = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()
    last_message_text = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'subject_title', 'subject_url',
            'other_participant', 'last_message_text',
            'last_message_at', 'unread_count',
        ]

    def _user(self):
        return self.context['request'].user

    def get_subject_title(self, obj):
        if obj.local_listing:
            ll = obj.local_listing
            return f'{ll.make} {ll.model} {ll.year}'
        if obj.imported_listing_id:
            try:
                v = obj.imported_listing.vehicle
                return f'{v.make} {v.model} {v.year}'
            except Exception:
                return f'Оголошення #{obj.imported_listing_id}'
        return 'Діалог'

    def get_subject_url(self, obj):
        if obj.local_listing_id:
            return f'/local/{obj.local_listing_id}'
        if obj.imported_listing_id:
            return f'/listings/{obj.imported_listing_id}'
        return '/'

    def get_other_participant(self, obj):
        user = self._user()
        other = obj.participants.exclude(pk=user.pk).first()
        return ParticipantSerializer(other).data if other else None

    def get_last_message_text(self, obj):
        msgs = list(obj.messages.all())
        return msgs[-1].text[:100] if msgs else ''

    def get_unread_count(self, obj):
        user = self._user()
        return sum(
            1 for m in obj.messages.all()
            if m.read_at is None and m.sender_id != user.pk
        )


class ConversationDetailSerializer(serializers.ModelSerializer):
    subject_title = serializers.SerializerMethodField()
    subject_url = serializers.SerializerMethodField()
    participants = ParticipantSerializer(many=True, read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'subject_title', 'subject_url', 'participants', 'messages', 'created_at', 'last_message_at']

    def get_subject_title(self, obj):
        if obj.local_listing:
            ll = obj.local_listing
            return f'{ll.make} {ll.model} {ll.year}'
        if obj.imported_listing_id:
            try:
                v = obj.imported_listing.vehicle
                return f'{v.make} {v.model} {v.year}'
            except Exception:
                return f'Оголошення #{obj.imported_listing_id}'
        return 'Діалог'

    def get_subject_url(self, obj):
        if obj.local_listing_id:
            return f'/local/{obj.local_listing_id}'
        if obj.imported_listing_id:
            return f'/listings/{obj.imported_listing_id}'
        return '/'


class StartConversationSerializer(serializers.Serializer):
    listing_type = serializers.ChoiceField(choices=['local', 'imported'])
    listing_id = serializers.IntegerField(min_value=1)
    text = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=1, max_length=2000, trim_whitespace=True)
