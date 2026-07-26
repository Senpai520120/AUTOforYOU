from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ['sender', 'text', 'created_at', 'read_at']
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'initiator', 'local_listing', 'imported_listing', 'last_message_at']
    list_filter = ['last_message_at']
    search_fields = ['initiator__email']
    readonly_fields = ['created_at', 'last_message_at']
    filter_horizontal = ['participants']
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'conversation', 'sender', '_preview', 'created_at', 'read_at']
    list_filter = ['created_at', 'read_at']
    search_fields = ['sender__email', 'text']
    readonly_fields = ['created_at']

    @admin.display(description='Текст')
    def _preview(self, obj):
        return obj.text[:60]
