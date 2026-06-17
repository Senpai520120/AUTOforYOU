import { apiGet, apiPost } from './client';
import { Listing, PaginatedResponse } from '@/lib/types';

export interface ListingFilters {
  status?: string;
  fuel_type?: string;
  max_price?: string;
  currency?: string;
  search?: string;
  page?: number;
}

function buildQuery(filters: ListingFilters): string {
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const listingsApi = {
  list: (filters: ListingFilters = {}) =>
    apiGet<PaginatedResponse<Listing>>(`/api/v1/listings/${buildQuery(filters)}`),

  detail: (id: number) =>
    apiGet<Listing>(`/api/v1/listings/${id}/`),

  b2bBoard: (filters: ListingFilters = {}) =>
    apiGet<PaginatedResponse<Listing>>(`/api/v1/b2b/board/${buildQuery(filters)}`),
};
