import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import LocalListingDetail from './LocalListingDetail';
import { LocalListing } from '@/lib/types';
import { buildMetadata } from '@/lib/seo';
import { isC2CEnabled } from '@/lib/c2c';
import { INTERNAL_API_URL } from '@/lib/config.server';

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
  // Розділ вимкнено або оголошення не публічне: метадані без даних. og:image дає opengraph-image.tsx.
  if (!(await isC2CEnabled())) return { title: 'Оголошення не знайдено' };
  const listing = await getListing(id);
  if (!listing || !['active', 'sold'].includes(listing.status)) return { title: 'Оголошення не знайдено' };
  const price = Number(listing.price).toLocaleString('uk-UA');
  return buildMetadata({
    title: `${listing.make} ${listing.model} ${listing.year} — ${price} ${listing.currency}`,
    description: listing.description || `${listing.make} ${listing.model} ${listing.year}, ${listing.mileage_km} км · ${listing.city_name}`,
    path: `/local/${listing.id}`,
    ownImage: true,
  });
}

export default async function LocalListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) notFound();
  return <LocalListingDetail listing={listing} />;
}
