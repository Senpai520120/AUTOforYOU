import { cache } from 'react';
import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import ListingDetail from '@/components/listings/ListingDetail';
import type { Listing } from '@/lib/types';

// INTERNAL_API_URL is set at runtime in Docker (http://backend:8000) for SSR.
const apiUrl = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

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

  const listing = await getListing(id);
  if (!listing) return { title: 'Оголошення не знайдено' };

  const v = listing.vehicle_detail;
  const title = `${v.year} ${v.make} ${v.model} — ${Number(listing.price).toLocaleString('uk-UA')} ${listing.currency}`;
  const description = `${v.make} ${v.model} ${v.year}, ${(v.engine_cc / 1000).toFixed(1)}л, ${v.fuel_type === 'petrol' ? 'бензин' : v.fuel_type === 'diesel' ? 'дизель' : v.fuel_type}. Купити авто з США: аукціон ${v.source_auction.toUpperCase()}, доставка під ключ в Україну.`;

  const primaryImg = v.images.find(i => i.is_primary) ?? v.images[0];
  const ogImage = primaryImg?.image || primaryImg?.source_url || null;

  const canonicalUrl = `${siteUrl}/listings/${id}`;

  return {
    title,
    description,
    alternates: { canonical: canonicalUrl },
    openGraph: {
      title,
      description,
      url: canonicalUrl,
      type: 'website',
      ...(ogImage ? { images: [{ url: ogImage, width: 1200, height: 630, alt: title }] } : {}),
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      ...(ogImage ? { images: [ogImage] } : {}),
    },
  };
}

export default async function ListingDetailPage({ params }: Props) {
  const { id: rawId } = await params;
  const id = parseInt(rawId, 10);
  if (isNaN(id)) notFound();

  const listing = await getListing(id);
  if (!listing) notFound();

  return <ListingDetail listing={listing} />;
}
