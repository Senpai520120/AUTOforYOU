import { apiGet, apiPost, apiFetch } from '@/api/client';
import type { SavedSearch } from '@/lib/types';

export function getSavedSearches() {
  return apiGet<SavedSearch[]>('/api/v1/saved-searches/');
}

export function createSavedSearch(name: string, filters: Record<string, string>, notify = true) {
  return apiPost<SavedSearch>('/api/v1/saved-searches/', { name, filters, notify });
}

export function deleteSavedSearch(id: number) {
  return apiFetch<void>(`/api/v1/saved-searches/${id}/`, { method: 'DELETE' });
}

export function patchSavedSearch(id: number, data: Partial<Pick<SavedSearch, 'name' | 'notify'>>) {
  return apiFetch<SavedSearch>(`/api/v1/saved-searches/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}
