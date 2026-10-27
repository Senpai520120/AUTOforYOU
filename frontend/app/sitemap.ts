import type { MetadataRoute } from 'next';
import type { Listing, LocalListing, PaginatedResponse } from '@/lib/types';
import { serverGet } from '@/lib/server-api';
import { isC2CEnabled } from '@/lib/c2c';
import { isModuleEnabled } from '@/lib/site-settings';
import { isHowItWorksPublished } from '@/lib/content';
import { getLandingList } from '@/lib/landings';
import { absoluteUrl } from '@/lib/site';
import { listingSlug } from '@/lib/utils';

// Залежить від прапорців з API: без цього збірка запекла б значення на момент build.
export const dynamic = 'force-dynamic';

/** Захисний потолок кількості URL (ліміт протоколу — 50 000). Змінна SITEMAP_MAX_URLS у .env. */
function maxUrls(): number {
  const n = Number(process.env.SITEMAP_MAX_URLS);
  return Number.isInteger(n) && n > 0 ? n : 45000;
}

/**
 * Усі сторінки списку: йдемо по page=N, поки є `next`. Збій API логуємо й віддаємо те,
 * що вже зібрано (порожній результат при помилці не підміняємо мовчки — 11-Q12).
 * Успішні відповіді кешуються fetch'ем; відповідь з помилкою Next не кешує.
 */
async function fetchAll<T>(path: string, limit: number): Promise<T[]> {
  const sep = path.includes('?') ? '&' : '?';
  const items: T[] = [];
  for (let page = 1; items.length < limit; page++) {
    const data = await serverGet<PaginatedResponse<T>>(`${path}${sep}page=${page}`, 600);
    if (!data) {
      console.error(`[sitemap] не вдалося отримати ${path} (сторінка ${page}); у sitemap потрапило ${items.length} URL`);
      break;
    }
    items.push(...data.results);
    if (!data.next || data.results.length === 0) break;
  }
  return items.slice(0, limit);
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const limit = maxUrls();
  const [c2c, lotsOn, howItWorksOn, landings] = await Promise.all([
    isC2CEnabled(), isModuleEnabled('lots'), isHowItWorksPublished(600), getLandingList(600),
  ]);

  // Статичні сторінки. /calculator навмисно немає: він noindex (11-Q5).
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: absoluteUrl('/'), changeFrequency: 'daily', priority: 1 },
    ...(c2c ? [{ url: absoluteUrl('/ua'), changeFrequency: 'hourly' as const, priority: 0.9 }] : []),
    // Юридичні документи мають бути публічно доступними та індексованими
    { url: absoluteUrl('/terms'), changeFrequency: 'yearly', priority: 0.3 },
    { url: absoluteUrl('/rules'), changeFrequency: 'yearly', priority: 0.3 },
    { url: absoluteUrl('/refund'), changeFrequency: 'yearly', priority: 0.3 },
    { url: absoluteUrl('/privacy'), changeFrequency: 'yearly', priority: 0.3 },
    { url: absoluteUrl('/cookies'), changeFrequency: 'yearly', priority: 0.3 },
    ...(howItWorksOn ? [{ url: absoluteUrl('/how-it-works'), changeFrequency: 'monthly' as const, priority: 0.6 }] : []),
    // Сторінки моделей (2.16): лише опубліковані з розрахунком; збій API = порожній список, sitemap не падає.
    ...(landings && landings.length ? [{ url: absoluteUrl('/prigon'), changeFrequency: 'weekly' as const, priority: 0.6 }] : []),
    ...(lotsOn ? [{ url: absoluteUrl('/listings'), changeFrequency: 'daily' as const, priority: 0.9 }] : []),
  ];

  let room = Math.max(0, limit - staticRoutes.length);

  // Лоти: тільки при увімкненому LOTS_ENABLED; URL — канонічний slug (11-Q2).
  let lotRoutes: MetadataRoute.Sitemap = [];
  if (lotsOn) {
    const [inStock, inTransit] = await Promise.all([
      fetchAll<Listing>('/api/v1/listings/?status=in_stock', room),
      fetchAll<Listing>('/api/v1/listings/?status=in_transit', room),
    ]);
    lotRoutes = [...inStock, ...inTransit].slice(0, room).map(l => ({
      url: absoluteUrl(`/listings/${listingSlug(l)}`),
      lastModified: new Date(l.updated_at),
      changeFrequency: 'daily' as const,
      priority: 0.8,
    }));
    room -= lotRoutes.length;
  }

  // Активні місцеві оголошення (публічний ендпоінт віддає тільки їх); C2C вимкнено — не запитуємо.
  let localRoutes: MetadataRoute.Sitemap = [];
  if (c2c) {
    const local = await fetchAll<LocalListing>('/api/v1/local/listings/', room);
    localRoutes = local.map(l => ({
      url: absoluteUrl(`/local/${l.id}`),
      lastModified: new Date(l.updated_at),
      changeFrequency: 'daily' as const,
      priority: 0.8,
    }));
  }

  const landingRoutes: MetadataRoute.Sitemap = (landings ?? []).map(l => ({
    url: absoluteUrl(`/prigon/${l.slug}`),
    lastModified: new Date(l.updated_at),
    changeFrequency: 'weekly' as const,
    priority: 0.7,
  }));

  return [...staticRoutes, ...landingRoutes, ...lotRoutes, ...localRoutes];
}
