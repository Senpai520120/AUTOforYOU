import { SITE_URL } from '@/lib/config';

// Адреса сайту живе в lib/config.ts (задача 6.4); тут лишається для сумісності імпортів.
export { SITE_URL };

export const SITE_NAME = 'AUTOforYOU';

/** Абсолютна адреса за шляхом сайту ('/ua' → 'https://…/ua'). */
export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}
