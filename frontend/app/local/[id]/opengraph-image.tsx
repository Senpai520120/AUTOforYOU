import { isC2CEnabled } from '@/lib/c2c';
import {
  brandCard, ITEM_CACHE, fetchPublicJson, itemCard, loadMediaPhoto, notFoundResponse, OG_CONTENT_TYPE, OG_SIZE,
} from '@/lib/og-card';
import type { LocalListing } from '@/lib/types';

export const alt = 'Оголошення по Україні - AUTOforYOU';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
// Не довше, ніж сама сторінка оголошення.
export const revalidate = 60;

// Публічні статуси: pending/rejected/hidden/draft/expired - як 404 сторінки.
const PUBLIC_STATUSES = new Set(['active', 'sold']);

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) return notFoundResponse();
  // Розділ вимкнено - нічого не розкриваємо.
  if (!(await isC2CEnabled())) return notFoundResponse();

  const res = await fetchPublicJson<LocalListing>(`/api/v1/local/listings/${id}/`);
  if (res.kind === 'missing') return notFoundResponse();
  try {
    if (res.kind === 'error') return await brandCard(undefined, undefined, ITEM_CACHE);
    const l = res.data;
    if (!PUBLIC_STATUSES.has(l.status)) return notFoundResponse();
    const img = l.images.find((i) => i.is_primary) ?? l.images[0];
    const photo = await loadMediaPhoto(img?.image);
    return await itemCard({
      title: `${l.make} ${l.model} ${l.year}`,
      price: `${Number(l.price).toLocaleString('uk-UA')} ${l.currency}`,
      label: `Оголошення по Україні · ${l.city_name}`,
      photo,
    });
  } catch {
    return brandCard(undefined, undefined, ITEM_CACHE);
  }
}
