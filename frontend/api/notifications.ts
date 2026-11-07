import { apiGet, apiPost } from '@/api/client';
import type { AppNotification, PaginatedResponse } from '@/lib/types';

export function getNotifications(page = 1) {
  return apiGet<PaginatedResponse<AppNotification>>(`/api/v1/notifications/?page=${page}`);
}

export function getUnreadCount() {
  return apiGet<{ unread_count: number }>('/api/v1/notifications/unread-count/');
}

export function markRead(id: number) {
  return apiPost<{ marked: number }>('/api/v1/notifications/mark-read/', { id });
}

export function markAllRead() {
  return apiPost<{ marked: number }>('/api/v1/notifications/mark-read/', { all: true });
}
