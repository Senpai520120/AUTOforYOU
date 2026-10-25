import type { MetadataRoute } from 'next';
import type { LocalListing, PaginatedResponse } from '@/lib/types';
import { serverGet } from '@/lib/server-api';
import { isC2CEnabled } from '@/lib/c2c';

// Залежить від прапорця C2C з API: без цього збірка запекла б значення на момент build.
export const dynamic = 'force-dynamic';

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua';

/** Активні місцеві оголошення — публічний ендпоінт віддає тільки їх. */
async function fetchLocalListings(): Promise<LocalListing[]> {
  const data = await serverGet<PaginatedResponse<LocalListing>>('/api/v1/local/listings/?page=1', 3600);
  return data?.results ?? [];
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Лоти імпорту (/listings) заморожені (задача 2.8): у sitemap їх немає і лоти не запитуються.
  // C2C вимкнено: /ua і /local/* у sitemap немає, оголошення не запитуються.
  const c2c = await isC2CEnabled();
  const localListings = c2c ? await fetchLocalListings() : [];

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${siteUrl}/`, changeFrequency: 'daily', priority: 1 },
    // Каталог України раніше в sitemap не потрапляв, хоча це єдиний розділ
    // з реальними оголошеннями.
    ...(c2c ? [{ url: `${siteUrl}/ua`, changeFrequency: 'hourly' as const, priority: 0.9 }] : []),
    { url: `${siteUrl}/calculator`, changeFrequency: 'monthly', priority: 0.7 },
    // Юридичні документи мають бути публічно доступними та індексованими
    { url: `${siteUrl}/terms`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/rules`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/refund`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/privacy`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${siteUrl}/cookies`, changeFrequency: 'yearly', priority: 0.3 },
  ];

  const localRoutes: MetadataRoute.Sitemap = localListings.map(l => ({
    url: `${siteUrl}/local/${l.id}`,
    lastModified: new Date(l.updated_at),
    changeFrequency: 'daily',
    priority: 0.8,
  }));

  return [...staticRoutes, ...localRoutes];
}
