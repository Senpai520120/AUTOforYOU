import type { MetadataRoute } from 'next';
import { listingSlug } from '@/lib/utils';
import type { Listing, PaginatedResponse } from '@/lib/types';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function fetchActiveListings(): Promise<Listing[]> {
  try {
    // Fetch first page of active retail listings (in_stock + in_transit)
    const res = await fetch(
      `${apiUrl}/api/v1/listings/?status=in_stock&channel=retail&page=1`,
      { next: { revalidate: 3600 } },
    );
    if (!res.ok) return [];
    const data: PaginatedResponse<Listing> = await res.json();
    const all = [...data.results];

    // Fetch in_transit page too
    const res2 = await fetch(
      `${apiUrl}/api/v1/listings/?status=in_transit&channel=retail&page=1`,
      { next: { revalidate: 3600 } },
    );
    if (res2.ok) {
      const data2: PaginatedResponse<Listing> = await res2.json();
      all.push(...data2.results);
    }
    return all;
  } catch {
    return [];
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const listings = await fetchActiveListings();

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${siteUrl}/`, changeFrequency: 'daily', priority: 1 },
    { url: `${siteUrl}/listings`, changeFrequency: 'hourly', priority: 0.9 },
    { url: `${siteUrl}/calculator`, changeFrequency: 'monthly', priority: 0.7 },
  ];

  const listingRoutes: MetadataRoute.Sitemap = listings.map(l => ({
    url: `${siteUrl}/listings/${listingSlug(l)}`,
    lastModified: new Date(l.updated_at),
    changeFrequency: 'daily',
    priority: 0.8,
  }));

  return [...staticRoutes, ...listingRoutes];
}
