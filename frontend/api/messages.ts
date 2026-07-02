import { apiGet, apiPost } from '@/api/client';
import type {
  ConversationSummary,
  ConversationDetail,
  ChatMessage,
  StartConversationResult,
} from '@/lib/types';

export function getConversations() {
  return apiGet<ConversationSummary[]>('/api/v1/messages/conversations/');
}

export function getConversation(id: number) {
  return apiGet<ConversationDetail>(`/api/v1/messages/conversations/${id}/`);
}

export function sendMessage(conversationId: number, text: string) {
  return apiPost<ChatMessage>(`/api/v1/messages/conversations/${conversationId}/`, { text });
}

export function startConversation(
  listingType: 'local' | 'imported',
  listingId: number,
  text: string,
) {
  return apiPost<StartConversationResult>('/api/v1/messages/start/', {
    listing_type: listingType,
    listing_id: listingId,
    text,
  });
}

export function getUnreadCount() {
  return apiGet<{ unread_count: number }>('/api/v1/messages/unread-count/');
}
