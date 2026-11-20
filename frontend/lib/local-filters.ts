/** Параметри фільтра каталогу /ua, що рахуються у лічильнику (без `page` і `ordering` — це не відбір). */
export const COUNTED_FILTER_KEYS = [
  'make', 'model', 'year_min', 'year_max', 'price_min', 'price_max',
  'fuel_type', 'transmission', 'body_type', 'region', 'city',
  'mileage_max', 'search',
] as const;

/** Кількість непорожніх параметрів фільтра. `get` — `sp.get` або читання з searchParams сторінки. */
export function countActiveFilters(get: (key: string) => string | string[] | null | undefined): number {
  return COUNTED_FILTER_KEYS.filter((k) => {
    const raw = get(k);
    const v = Array.isArray(raw) ? raw[0] : raw;
    return v !== undefined && v !== null && v !== '';
  }).length;
}
