import { apiGet, apiPost } from '@/api/client';
import type {
  PaginatedResponse,
  ConversationSummary,
  ConversationDetail,
  ChatMessage,
  StartConversationResult,
} from '@/lib/types';

/** Список діалогів посторінково (4.7). */
export function getConversations(page = 1) {
  return apiGet<PaginatedResponse<ConversationSummary>>(`/api/v1/messages/conversations/?page=${page}`);
}

/** Останні MESSAGES_PAGE_SIZE повідомлень; `before` — id, раніше якого підвантажити порцію. */
export function getConversation(id: number, before?: number) {
  const q = before ? `?before=${before}` : '';
  return apiGet<ConversationDetail>(`/api/v1/messages/conversations/${id}/${q}`);
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
