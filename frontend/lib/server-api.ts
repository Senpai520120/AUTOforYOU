/**
 * Серверні запити до API — для рендера каталогів на сервері.
 *
 * Клієнтський api/client.ts тут не годиться: він читає JWT з localStorage,
 * якого на сервері не існує. Тому серверний шар ходить в API анонімно і
 * віддає рівно те, що бачить незалогінений відвідувач і пошуковий робот.
 *
 * INTERNAL_API_URL задається в Docker (http://backend:8000).
 */
const apiUrl = process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type SearchParams = Record<string, string | string[] | undefined>;

/**
 * Збирає query-рядок тільки з дозволених ключів.
 *
 * Білий список навмисний: без нього будь-який параметр з адресного рядка
 * потрапляв би в запит до API як є.
 */
export function buildQuery(params: SearchParams, allowed: readonly string[]): string {
  const p = new URLSearchParams();
  for (const key of allowed) {
    const raw = params[key];
    const value = Array.isArray(raw) ? raw[0] : raw;
    if (value !== undefined && value !== '') p.set(key, value);
  }
  const query = p.toString();
  return query ? `?${query}` : '';
}

/** Повертає null замість винятку: сторінка має відрендеритись і без API. */
export async function serverGet<T>(path: string, revalidate = 60): Promise<T | null> {
  try {
    const res = await fetch(`${apiUrl}${path}`, { next: { revalidate } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** Посилання на ту саму сторінку з іншим значенням page. */
export function pageHref(basePath: string, params: SearchParams, page: number): string {
  const p = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    const value = Array.isArray(raw) ? raw[0] : raw;
    if (value !== undefined && value !== '' && key !== 'page') p.set(key, value);
  }
  p.set('page', String(page));
  return `${basePath}?${p.toString()}`;
}
