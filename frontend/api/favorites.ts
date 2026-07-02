import { apiGet, apiPost, apiFetch } from '@/api/client';
import type { FavoriteItem } from '@/lib/types';

export function getFavorites() {
  return apiGet<FavoriteItem[]>('/api/v1/favorites/');
}

export function addFavorite(listingType: 'local' | 'imported', listingId: number) {
  return apiPost<FavoriteItem>('/api/v1/favorites/', { listing_type: listingType, listing_id: listingId });
}

export function removeFavorite(listingType: 'local' | 'imported', listingId: number) {
  return apiFetch<{ deleted: boolean }>('/api/v1/favorites/', {
    method: 'DELETE',
    body: JSON.stringify({ listing_type: listingType, listing_id: listingId }),
  });
}

export function getFavoriteStatus(listingType: 'local' | 'imported', listingId: number) {
  return apiGet<{ is_favorite: boolean }>(
    `/api/v1/favorites/status/?listing_type=${listingType}&listing_id=${listingId}`,
  );
}
