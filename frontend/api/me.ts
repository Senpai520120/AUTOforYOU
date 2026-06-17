import { apiGet, apiPost, apiPatch, apiDelete } from './client';
import { TrustedShop, Shipment, PaginatedResponse } from '@/lib/types';

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
};
