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
