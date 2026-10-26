import { OG_CONTENT_TYPE, OG_SIZE, formatPrice, listingImage, notFoundImage, photoDataUri } from '@/lib/og';
import type { LocalListing } from '@/lib/types';

// 6.3b: превʼю місцевого оголошення — марка, модель, рік, ціна у валюті оголошення, місто, перше фото.
// API віддає лише активні оголошення: невідоме, pending, hidden, blocked, видалене — 404 (як сторінка).
export const alt = 'Оголошення про продаж авто';
export const size = OG_SIZE;
export const contentType = OG_CONTENT_TYPE;
export const dynamic = 'force-dynamic';  // превʼю не старше самої сторінки (6.3b)

const API = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export async function renderLocalListingImage(id: string): Promise<Response> {
  if (!/^\d+$/.test(id)) return notFoundImage();
  // no-store: 404 у кеш Next не потрапляє, і застарілий 200 віддавався б далі — зняте оголошення «світилося» б у превʼю.
  let listing: LocalListing | null = null;
  try {
    const res = await fetch(`${API}/api/v1/local/listings/${id}/`, { cache: 'no-store' });
    if (res.status === 404) return notFoundImage();
    if (res.ok) listing = await res.json();
  } catch {
    listing = null;
  }
  if (!listing) return listingImage({ title: 'Оголошення про продаж авто', price: '' });
  const img = listing.images.find(i => i.is_primary) ?? listing.images[0];
  return listingImage({
    title: `${listing.make} ${listing.model} ${listing.year}`,
    price: formatPrice(listing.price, listing.currency),
    subtitle: listing.city_name,
    photo: await photoDataUri(img?.image),
  });
}

export default async function Image({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return renderLocalListingImage(id);
}
