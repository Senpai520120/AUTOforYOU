import { apiGet, apiPost } from '@/api/client';
import type { AppNotification } from '@/lib/types';

export function getNotifications() {
  return apiGet<AppNotification[]>('/api/v1/notifications/');
}

export function getUnreadCount() {
  return apiGet<{ unread_count: number }>('/api/v1/notifications/unread-count/');
}

export function markRead(id: number) {
  return apiPost<{ marked: number }>('/api/v1/notifications/mark-read/', { id });
}

export function markAllRead() {
  return apiPost<{ marked: string }>('/api/v1/notifications/mark-read/', { all: true });
}
