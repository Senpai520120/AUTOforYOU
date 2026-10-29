/**
 * Єдине місце адрес сайту та API (задача 6.4, 08-C5/11-C9).
 *
 * NEXT_PUBLIC_API_URL і NEXT_PUBLIC_SITE_URL вшиваються в збірку: після зміни фронтенд треба
 * пересібрати. Звертатись до process.env.NEXT_PUBLIC_* треба буквально (Next підставляє їх
 * текстовою заміною), тому змінні читаються нижче по одній.
 * Без змінної `next build` падає з поясненням; fallback на localhost лишається лише для розробки.
 */
const IS_BUILD = process.env.NEXT_PHASE === 'phase-production-build';

function fromEnv(name: string, value: string | undefined, devFallback: string): string {
  const v = (value ?? '').trim();
  if (v) return v.replace(/\/+$/, '');
  if (IS_BUILD) {
    throw new Error(
      `Не задано ${name}. Для production-збірки вкажіть повну адресу (наприклад https://example.com) ` +
        'у .env або build-arg і пересберіть фронтенд.',
    );
  }
  return devFallback;
}

/** Адреса API для браузера. */
export const API_URL = fromEnv('NEXT_PUBLIC_API_URL', process.env.NEXT_PUBLIC_API_URL, 'http://localhost:8000');

/** Публічна адреса сайту (canonical, sitemap, Open Graph). */
export const SITE_URL = fromEnv('NEXT_PUBLIC_SITE_URL', process.env.NEXT_PUBLIC_SITE_URL, 'http://localhost:3000');
