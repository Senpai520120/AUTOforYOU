/**
 * Сторінки моделей «Пригон з США» (задача 2.16): серверні запити до публічного API.
 *
 * Різниця між «немає сторінки» (404) і «API недоступне» важлива: у першому випадку сторінка 404,
 * у другому чесна помилка, а не порожній розрахунок. Кеш fetch — LANDING_REVALIDATE_SECONDS (.env).
 */
import { INTERNAL_API_URL } from '@/lib/config';
import type { LandingDetail, LandingListItem } from '@/lib/types';

const DEFAULT_REVALIDATE = 60;

/** Час кешу запитів у секундах; некоректне значення = типовий. */
export function landingRevalidate(): number {
  const n = Number(process.env.LANDING_REVALIDATE_SECONDS);
  return Number.isInteger(n) && n >= 0 ? n : DEFAULT_REVALIDATE;
}

export type LandingResult = { status: 'ok'; data: LandingDetail } | { status: 'notfound' } | { status: 'error' };

export async function getLanding(slug: string): Promise<LandingResult> {
  try {
    const res = await fetch(`${INTERNAL_API_URL}/api/v1/landings/${encodeURIComponent(slug)}/`, {
      next: { revalidate: landingRevalidate() },
    });
    if (res.status === 404) return { status: 'notfound' };
    if (!res.ok) return { status: 'error' };
    return { status: 'ok', data: (await res.json()) as LandingDetail };
  } catch {
    return { status: 'error' };
  }
}

/** Опубліковані сторінки. null — API недоступне (sitemap і блоки не падають). */
export async function getLandingList(revalidate = landingRevalidate()): Promise<LandingListItem[] | null> {
  try {
    const res = await fetch(`${INTERNAL_API_URL}/api/v1/landings/`, { next: { revalidate } });
    if (!res.ok) return null;
    const data = (await res.json()) as { results: LandingListItem[] };
    return data.results;
  } catch {
    return null;
  }
}

/** Slug-и опублікованих сторінок (за задачею: getLandingSlugs). */
export async function getLandingSlugs(): Promise<string[] | null> {
  const list = await getLandingList();
  return list ? list.map((l) => l.slug) : null;
}

/** Запит на калькулятор з входами сторінки (ті ж ключі, що читає app/calculator). */
export function calculatorHref(inputs: LandingDetail['calculation']['inputs']): string {
  const p = new URLSearchParams();
  const price = Number(inputs.auction_price_usd);
  if (Number.isFinite(price) && price > 0) p.set('auction_price_usd', String(price));
  if (inputs.engine_cc) p.set('engine_cc', String(inputs.engine_cc));
  if (inputs.fuel_type) p.set('fuel_type', inputs.fuel_type);
  if (inputs.vehicle_year) p.set('year', String(inputs.vehicle_year));
  if (inputs.auction) p.set('auction', inputs.auction);
  if (inputs.us_port) p.set('us_port', inputs.us_port);
  const q = p.toString();
  return q ? `/calculator?${q}` : '/calculator';
}
