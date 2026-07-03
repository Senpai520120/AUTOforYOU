import { apiGet, apiPost } from './client';
import { Deal, ReviewPayload, SellerRating } from '@/lib/types';

export const dealsApi = {
  list: () =>
    apiGet<Deal[]>('/api/v1/deals/'),

  propose: (listingId: number, buyerId: number) =>
    apiPost<Deal>('/api/v1/deals/', { listing_id: listingId, buyer_id: buyerId }),

  confirm: (dealId: number) =>
    apiPost<Deal>(`/api/v1/deals/${dealId}/confirm/`, {}),

  cancel: (dealId: number) =>
    apiPost<Deal>(`/api/v1/deals/${dealId}/cancel/`, {}),

  review: (dealId: number, data: ReviewPayload) =>
    apiPost<{ id: number; rating: number; text: string }>(`/api/v1/deals/${dealId}/review/`, data),

  sellerRating: (userId: number) =>
    apiGet<SellerRating>(`/api/v1/deals/seller-rating/${userId}/`),

  listingBuyers: (listingId: number) =>
    apiGet<{ id: number; email: string; first_name: string; last_name: string }[]>(
      `/api/v1/deals/listing-buyers/${listingId}/`
    ),
};
