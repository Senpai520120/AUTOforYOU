import { apiFetch, apiGet, apiPost, apiPatch, apiDelete } from './client';
import { TrustedShop, Shipment, PaginatedResponse, User } from '@/lib/types';

export type ProfileUpdate = Pick<User, 'first_name' | 'last_name' | 'phone'>;

export const meApi = {
  trustedShops: {
    list: () => apiGet<PaginatedResponse<TrustedShop>>('/api/v1/auth/me/trusted-shops/'),
    create: (data: Omit<TrustedShop, 'id' | 'created_at' | 'updated_at'>) =>
      apiPost<TrustedShop>('/api/v1/auth/me/trusted-shops/', data),
    update: (id: number, data: Partial<TrustedShop>) =>
      apiPatch<TrustedShop>(`/api/v1/auth/me/trusted-shops/${id}/`, data),
    delete: (id: number) =>
      apiDelete(`/api/v1/auth/me/trusted-shops/${id}/`),
  },
  shipments: () =>
    apiGet<PaginatedResponse<Shipment>>('/api/v1/auth/me/shipments/'),
  profile: {
    update: (data: ProfileUpdate) => apiPatch<User>('/api/v1/auth/profile/', data),
  },
  /** Вивантаження «Мої дані»: JSON зберігається файлом через blob (без токенів в URL). */
  exportData: async () => {
    const data = await apiGet<unknown>('/api/v1/auth/me/export/');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `autoforyou-data-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  /** Запит видалення акаунта (1.8): 202 і дата; сервер відкликає сесії й видаляє cookie. */
  deleteAccount: (password: string) =>
    apiFetch<{ deletion_scheduled_for: string }>('/api/v1/auth/profile/', {
      method: 'DELETE', body: JSON.stringify({ password }),
    }),
  cancelDeletion: () => apiPost<User>('/api/v1/auth/profile/cancel-deletion/'),
};
