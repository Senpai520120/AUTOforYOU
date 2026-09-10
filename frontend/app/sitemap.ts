import type { MetadataRoute } from 'next';
import { listingSlug } from '@/lib/utils';
import type { Listing, LocalListing, PaginatedResponse } from '@/lib/types';
import { serverGet } from '@/lib/server-api';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

/** Роздрібні лоти імпорту: в наявності та в дорозі. */
async function fetchActiveListings(): Promise<Listing[]> {
  const pages = await Promise.all([
    serverGet<PaginatedResponse<Listing>>('/api/v1/listings/?status=in_stock&channel=retail&page=1', 3600),
    serverGet<PaginatedResponse<Listing>>('/api/v1/listings/?status=in_transit&channel=retail&page=1', 3600),
  ]);
  return pages.flatMap(p => p?.results ?? []);
}

/** Активні місцеві оголошення — публічний ендпоінт віддає тільки їх. */
async function fetchLocalListings(): Promise<LocalListing[]> {
  const data = await serverGet<PaginatedResponse<LocalListing>>('/api/v1/local/listings/?page=1', 3600);
  return data?.results ?? [];
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [listings, localListings] = await Promise.all([
    fetchActiveListings(),
    fetchLocalListings(),
  ]);

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${siteUrl}/`, changeFrequency: 'daily', priority: 1 },
    { url: `${siteUrl}/listings`, changeFrequency: 'hourly', priority: 0.9 },
    // Каталог України раніше в sitemap не потрапляв, хоча це єдиний розділ
    // з реальними оголошеннями.
    { url: `${siteUrl}/ua`, changeFrequency: 'hourly', priority: 0.9 },
    { url: `${siteUrl}/calculator`, changeFrequency: 'monthly', priority: 0.7 },
    // Юридичні документи мають бути публічно доступними та індексованими
    { url: `${siteUrl}/terms`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/rules`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/refund`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/privacy`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/cookies`, changeFrequency: 'yearly', priority: 0.3 },
  ];

  const listingRoutes: MetadataRoute.Sitemap = listings.map(l => ({
    url: `${siteUrl}/listings/${listingSlug(l)}`,
    lastModified: new Date(l.updated_at),
    changeFrequency: 'daily',
    priority: 0.8,
  }));

  const localRoutes: MetadataRoute.Sitemap = localListings.map(l => ({
    url: `${siteUrl}/local/${l.id}`,
    lastModified: new Date(l.updated_at),
    changeFrequency: 'daily',
    priority: 0.8,
  }));

  return [...staticRoutes, ...listingRoutes, ...localRoutes];
}
