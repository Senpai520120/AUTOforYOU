/**
 * CSRF-токен для небезпечних запитів (задача 1.4).
 *
 * JWT лежить у httpOnly-cookie, тому бекенд перевіряє CSRF на POST/PUT/PATCH/DELETE:
 * значення cookie `csrftoken` (не httpOnly) треба повернути в заголовку X-CSRFToken.
 * Cookie щоразу читається заново: після входу бекенд її оновлює (rotate_token).
 */
import { API_URL as API } from '@/lib/config';
const CSRF_COOKIE = 'csrftoken';

/** Значення не-httpOnly cookie за назвою (httpOnly JS не бачить узагалі). */
export function readCookie(cookieName: string): string | null {
  if (typeof document === 'undefined') return null;
  for (const part of document.cookie.split(';')) {
    const [name, ...rest] = part.trim().split('=');
    if (name === cookieName) return decodeURIComponent(rest.join('='));
  }
  return null;
}

export function readCsrfCookie(): string | null {
  return readCookie(CSRF_COOKIE);
}

let pending: Promise<string | null> | null = null;

/** Токен з cookie; якщо cookie ще немає — один запит GET /auth/csrf/ на всі паралельні виклики. */
export async function getCsrfToken(): Promise<string | null> {
  const existing = readCsrfCookie();
  if (existing) return existing;
  if (typeof window === 'undefined') return null;
  if (!pending) {
    pending = fetch(`${API}/api/v1/auth/csrf/`, { credentials: 'include' })
      .then(() => readCsrfCookie())
      .catch(() => null)
      .finally(() => { pending = null; });
  }
  return pending;
}
