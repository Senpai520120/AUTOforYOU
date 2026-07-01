import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import LocalListingDetail from './LocalListingDetail';
import { LocalListing } from '@/lib/types';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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
  const img = listing.images.find(i => i.is_primary) ?? listing.images[0];
  const imgUrl = img?.image || img?.source_url;
  return {
    title: `${listing.make} ${listing.model} ${listing.year} — ${listing.price} ${listing.currency}`,
    description: `${listing.make} ${listing.model} ${listing.year}, ${listing.mileage_km} км, ${listing.city_name}`,
    openGraph: {
      title: `${listing.make} ${listing.model} ${listing.year}`,
      description: listing.description || `${listing.mileage_km} км · ${listing.city_name}`,
      ...(imgUrl ? { images: [imgUrl] } : {}),
    },
  };
}

export default async function LocalListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) notFound();
  return <LocalListingDetail listing={listing} />;
}
