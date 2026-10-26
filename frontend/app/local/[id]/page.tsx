import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import LocalListingDetail from './LocalListingDetail';
import { LocalListing } from '@/lib/types';
import { buildMetadata } from '@/lib/seo';
import { INTERNAL_API_URL } from '@/lib/config';

// INTERNAL_API_URL is set at runtime in Docker (http://backend:8000) for SSR.
// NEXT_PUBLIC_API_URL is baked at build time and used by browser JS.
const API = INTERNAL_API_URL;

async function getListing(id: string): Promise<LocalListing | null> {
  try {
    const res = await fetch(`${API}/api/v1/local/listings/${id}/`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) return { title: 'Оголошення не знайдено' };
  const price = Number(listing.price).toLocaleString('uk-UA');
  return buildMetadata({
    title: `${listing.make} ${listing.model} ${listing.year} — ${price} ${listing.currency}`,
    description: listing.description || `${listing.make} ${listing.model} ${listing.year}, ${listing.mileage_km} км · ${listing.city_name}`,
    path: `/local/${listing.id}`,
    segmentImage: true,
    // og:image/twitter:image — з ./opengraph-image.tsx (6.3b), файлові метадані мають пріоритет
  });
}

export default async function LocalListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) notFound();
  return <LocalListingDetail listing={listing} />;
}
