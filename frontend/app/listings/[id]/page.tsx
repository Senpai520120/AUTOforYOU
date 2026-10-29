import { cache } from 'react';
import { notFound, permanentRedirect } from 'next/navigation';
import type { Metadata } from 'next';
import ListingDetail from '@/components/listings/ListingDetail';
import type { Listing } from '@/lib/types';
import { buildMetadata } from '@/lib/seo';
import { isModuleEnabled, requireModule } from '@/lib/site-settings';
import { listingSlug } from '@/lib/utils';
import { INTERNAL_API_URL } from '@/lib/config.server';

const apiUrl = INTERNAL_API_URL;

// cache() deduplicates the fetch — called once for metadata + once for the page = 1 request
const getListing = cache(async (id: number): Promise<Listing | null> => {
  try {
    const res = await fetch(`${apiUrl}/api/v1/listings/${id}/`, {
      next: { revalidate: 300 },
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
});

type Props = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id: rawId } = await params;
  // Support slug format "123-toyota-camry-2020" — parse numeric prefix
  const id = parseInt(rawId, 10);
  if (isNaN(id)) return { title: 'Оголошення не знайдено' };

  // Модуль лотів вимкнено: метадані не розкривають дані лота.
  if (!(await isModuleEnabled('lots'))) return { title: 'Оголошення не знайдено' };
  const listing = await getListing(id);
  if (!listing) return { title: 'Оголошення не знайдено' };

  const v = listing.vehicle_detail;
  const title = `${v.year} ${v.make} ${v.model} — ${Number(listing.price).toLocaleString('uk-UA')} ${listing.currency}`;
  const description = `${v.make} ${v.model} ${v.year}, ${(v.engine_cc / 1000).toFixed(1)}л, ${v.fuel_type === 'petrol' ? 'бензин' : v.fuel_type === 'diesel' ? 'дизель' : v.fuel_type}. Купити авто з США: аукціон ${v.source_auction.toUpperCase()}, доставка під ключ в Україну.`;

  // Єдиний канонічний URL — slug-формат (11-Q2). og:image дає opengraph-image.tsx (генерована картка
  // без фото Copart/IAAI: режим фото Q8 = off; partner/auction потребують shareable_images з 2.11).
  return buildMetadata({
    title,
    description,
    path: `/listings/${listingSlug(listing)}`,
    ownImage: true,
  });
}

export default async function ListingDetailPage({ params }: Props) {
  const { id: rawId } = await params;
  const id = parseInt(rawId, 10);
  if (isNaN(id)) notFound();

  // Модуль заморожено — 404, а не редірект (layout робить те саме, але рендериться паралельно).
  await requireModule('lots');
  const listing = await getListing(id);
  if (!listing) notFound();

  // Неканонічні адреси (/listings/42, /listings/42-мусор) → 308 на slug-URL.
  const canonical = listingSlug(listing);
  if (rawId !== canonical) permanentRedirect(`/listings/${canonical}`);

  return <ListingDetail listing={listing} />;
}
