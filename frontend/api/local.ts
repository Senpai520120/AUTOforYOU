import { apiFetch, apiGet, apiPost, apiPatch, apiDelete } from './client';
import {
  LocalListing,
  LocalListingFilters,
  PaginatedResponse,
  Region,
  City,
  VinPrefillResult,
} from '@/lib/types';

function buildQuery(filters: LocalListingFilters): string {
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== null) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const localApi = {
  list: (filters: LocalListingFilters = {}) =>
    apiGet<PaginatedResponse<LocalListing>>(`/api/v1/local/listings/${buildQuery(filters)}`),

  detail: (id: number) =>
    apiGet<LocalListing>(`/api/v1/local/listings/${id}/`),

  create: (data: Record<string, unknown>) =>
    apiPost<LocalListing>('/api/v1/local/listings/', data),

  update: (id: number, data: Record<string, unknown>) =>
    apiPatch<LocalListing>(`/api/v1/local/listings/${id}/`, data),

  remove: (id: number) =>
    apiDelete(`/api/v1/local/listings/${id}/`),

  regions: () =>
    apiGet<Region[]>('/api/v1/local/regions/'),

  cities: (regionId: number) =>
    apiGet<City[]>(`/api/v1/local/regions/${regionId}/cities/`),

  vinPrefill: (vin: string) =>
    apiGet<VinPrefillResult>(`/api/v1/local/vin-prefill/${vin}/`),

  myListings: () =>
    apiGet<PaginatedResponse<LocalListing>>('/api/v1/local/my-listings/'),
};
