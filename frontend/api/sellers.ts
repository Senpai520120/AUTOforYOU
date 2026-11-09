import { apiGet } from './client';
import type { SellerProfile } from '@/lib/types';

/** Шлях публічної сторінки продавця (задача 8.6); id — лише ціле число. */
export function sellerPath(id: number | string, page?: number): string {
  const n = Number(id);
  const query = page && page > 1 ? `?page=${page}` : '';
  return `/api/v1/local/sellers/${Number.isInteger(n) && n > 0 ? n : 0}/${query}`;
}

export const sellersApi = {
  get: (id: number | string, page?: number) => apiGet<SellerProfile>(sellerPath(id, page)),
};
