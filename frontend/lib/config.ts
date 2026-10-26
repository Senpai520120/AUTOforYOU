/**
 * Адреси API та сайту — єдине місце (задача 6.4, 08-C5 / 11-C9 / 09-C4).
 *
 * NEXT_PUBLIC_* вшиваються при збірці: після зміни — пересібрати фронтенд (11-C10).
 * Production-збірка без NEXT_PUBLIC_API_URL / NEXT_PUBLIC_SITE_URL падає з поясненням (next.config.ts);
 * запасні адреси нижче — лише для розробки.
 */
export const DEV_API_URL = 'http://localhost:8000';
export const DEV_SITE_URL = 'http://localhost:3000';

const trim = (url: string) => url.replace(/\/+$/, '');

/** Адреса API для браузера (і для сервера, якщо INTERNAL_API_URL не задано). */
export const API_URL = trim(process.env.NEXT_PUBLIC_API_URL || DEV_API_URL);

/** Адреса API для серверного рендеру: у Docker — http://backend:8000 (задається під час запуску). */
export const INTERNAL_API_URL = trim(process.env.INTERNAL_API_URL || API_URL);

/** Публічна адреса сайту (canonical, sitemap, OG). */
export const SITE_URL = trim(process.env.NEXT_PUBLIC_SITE_URL || DEV_SITE_URL);

export const SITE_NAME = 'AUTOforYOU';

/** Абсолютна адреса за шляхом сайту ('/ua' → 'https://…/ua'). */
export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}
