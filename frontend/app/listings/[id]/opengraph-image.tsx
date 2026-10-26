import { OG_CONTENT_TYPE, OG_SIZE, formatPrice, listingImage, notFoundImage } from '@/lib/og';
import type { Listing } from '@/lib/types';
import { INTERNAL_API_URL } from '@/lib/config';

// 6.3b: превʼю лота — марка, модель, рік, ціна у валюті лота. Фото Copart/IAAI не використовуються:
// режим фото за замовчуванням `off` (Q8), режими partner/auction з’являться з задачею 2.11 (shareable_images).
// Невідомий лот або каталог заморожено (LOTS_ENABLED=false, 404 з API і proxy.ts) — 404.
export const alt = 'Авто з США — ціна під ключ';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const dynamic = 'force-dynamic';  // превʼю не старше самої сторінки (6.3b)

const API = INTERNAL_API_URL;

export async function renderLotImage(rawId: string): Promise<Response> {
  const id = parseInt(rawId, 10);
  if (isNaN(id)) return notFoundImage();
  // no-store: 404 у кеш Next не потрапляє, і застарілий 200 віддавався б далі — зняте оголошення «світилося» б у превʼю.
  let listing: Listing | null = null;
  try {
    const res = await fetch(`${API}/api/v1/listings/${id}/`, { cache: 'no-store' });
    if (res.status === 404) return notFoundImage();
    if (res.ok) listing = await res.json();
  } catch {
    listing = null;
  }
  if (!listing) return listingImage({ title: 'Авто з США під ключ', price: '' });
  const v = listing.vehicle_detail;
  return listingImage({
    title: `${v.make} ${v.model} ${v.year}`,
    price: formatPrice(listing.price, listing.currency),
    subtitle: 'Авто з аукціону США',
  });
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return renderLotImage(id);
}
