import { apiGet } from '@/api/client';
import type { SiteSettings } from '@/lib/types';

/**
 * Спільний клієнтський запит публічних налаштувань (задача 10.16).
 * CookieBanner, AnalyticsLoader, PartnerVinLink, useSiteConfig, форма заявки й запасний контакт
 * раніше робили по запиту кожен. Тепер одна спільна обіцянка на сторінку.
 *
 * - Успіх живе TTL_MS (налаштування змінюються рідко, а довга SPA-сесія не має застрягти на старому).
 * - Помилка не кешується: наступний виклик пробує знову.
 * - `force: true` — свіжий запит (кнопка «Спробувати ще раз»).
 */
const TTL_MS = 60_000;

let cached: { promise: Promise<SiteSettings>; at: number } | null = null;

export function fetchSiteSettings(force = false): Promise<SiteSettings> {
  const now = Date.now();
  if (!force && cached && now - cached.at < TTL_MS) return cached.promise;
  const promise = apiGet<SiteSettings>('/api/v1/site-settings/');
  const entry = { promise, at: now };
  cached = entry;
  promise.catch(() => {
    if (cached === entry) cached = null;
  });
  return promise;
}
