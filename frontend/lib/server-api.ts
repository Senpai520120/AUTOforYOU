/**
 * Серверні запити до API — для рендера сторінок на сервері.
 *
 * serverGet — анонімний і кешований: віддає рівно те, що бачить
 * незалогінений відвідувач і пошуковий робот (публічні сторінки, SEO).
 *
 * serverGetAuthed — від імені відвідувача: передає в API його httpOnly-cookie
 * `access` (задача 1.4). Без кешу, тільки для сторінок з force-dynamic.
 *
 * INTERNAL_API_URL задається в Docker (http://backend:8000).
 */
import { INTERNAL_API_URL as apiUrl } from '@/lib/config.server';
import { API_URL } from '@/lib/config';

const INTERNAL_MEDIA = `${apiUrl}/media/`;
const PUBLIC_MEDIA = `${API_URL.replace(/\/+$/, '')}/media/`;

/**
 * Замінює внутрішню адресу медіа на публічну (задача 10.3).
 *
 * Django будує абсолютний URL фото з Host запиту. Запит із сервера Next іде на
 * http://backend:8000, тож у відповіді фото мають адресу, яку браузер не відкриє,
 * а /_next/image відповідає 400. Фото з S3/R2 мають власний домен і не змінюються.
 */
export function publicMedia<T>(data: T): T {
  if (data == null || INTERNAL_MEDIA === PUBLIC_MEDIA) return data;
  const json = JSON.stringify(data);
  if (!json.includes(INTERNAL_MEDIA)) return data;
  return JSON.parse(json.split(INTERNAL_MEDIA).join(PUBLIC_MEDIA)) as T;
}

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
    return publicMedia((await res.json()) as T);
  } catch {
    return null;
  }
}

const ACCESS_COOKIE = 'access';

/**
 * GET від імені поточного відвідувача. null — гість, протухший access або збій API.
 *
 * - В API йде тільки cookie `access` (решта cookie браузера бекенду не потрібна).
 *   Домен cookie значення не має: заголовок Cookie збирається вручну, тому
 *   працює і через INTERNAL_API_URL=http://backend:8000.
 * - cache: 'no-store' — відповідь одного користувача не потрапляє в кеш іншого.
 *   Сторінка, що викликає цю функцію, має бути `export const dynamic = 'force-dynamic'`.
 * - Обмеження: refresh-cookie має Path=/api/v1/auth/ і до сервера Next не доходить,
 *   тож протухший access тут не оновити. Сторінка рендериться анонімно, клієнт
 *   робить refresh (api/client) і викликає router.refresh().
 */
export async function serverGetAuthed<T>(path: string): Promise<T | null> {
  try {
    // Динамічний імпорт: модуль імпортують і компоненти, яким next/headers не потрібен.
    const { cookies } = await import('next/headers');
    const access = (await cookies()).get(ACCESS_COOKIE)?.value;
    // JWT — base64url і крапки; інше значення не підставляємо в заголовок.
    if (!access || !/^[\w.-]+$/.test(access)) return null;
    const res = await fetch(`${apiUrl}${path}`, {
      headers: { Cookie: `${ACCESS_COOKIE}=${access}` },
      cache: 'no-store',
    });
    if (!res.ok) return null;
    return publicMedia((await res.json()) as T);
  } catch {
    return null;
  }
}

/** ?page= → ціле ≥ 1; abc, 0, -1, 1.5 дають 1. */
export function pageNumber(params: SearchParams): number {
  const raw = params.page;
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (value === undefined || !/^\d{1,6}$/.test(value)) return 1;
  return Math.max(1, Number(value));
}

/**
 * Номери для пагінації: перша, остання і вікно ±2 навколо поточної; `null` — «…».
 */
export function pageWindow(current: number, total: number, radius = 2): (number | null)[] {
  const pages: (number | null)[] = [];
  let prev = 0;
  for (let p = 1; p <= total; p++) {
    if (p === 1 || p === total || Math.abs(p - current) <= radius) {
      if (p - prev > 1) pages.push(null);
      pages.push(p);
      prev = p;
    }
  }
  return pages;
}

/**
 * Список з ?page=: якщо сторінки за межами діапазону немає (DRF 404 → null),
 * повертає першу, а не «не вдалося завантажити».
 */
export async function fetchPaginated<T>(
  basePath: string,
  params: SearchParams,
  allowed: readonly string[],
): Promise<{ data: T | null; page: number }> {
  let page = pageNumber(params);
  const query = (p: number) => buildQuery({ ...params, page: p > 1 ? String(p) : undefined }, allowed);
  let data = await serverGet<T>(`${basePath}${query(page)}`);
  if (data === null && page > 1) {
    page = 1;
    data = await serverGet<T>(`${basePath}${query(1)}`);
  }
  return { data, page };
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
