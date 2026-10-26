/**
 * Базова адреса сайту — єдине місце (задача 6.3).
 * NEXT_PUBLIC_SITE_URL вшивається при збірці: після зміни фронтенд треба пересібрати.
 */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://autoforyou.ua').replace(/\/+$/, '');

export const SITE_NAME = 'AUTOforYOU';

/** Абсолютна адреса за шляхом сайту ('/ua' → 'https://…/ua'). */
export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}
