import type { Metadata } from 'next';
import { SITE_NAME, absoluteUrl } from '@/lib/site';

export const DESCRIPTION_MAX = 160;

// 6.3b: бренд-картка з app/opengraph-image.tsx. openGraph сторінки замінює успадкований з layout разом
// із файловою картинкою кореня, тож за замовчуванням підставляємо її тут. Сегменти з власним
// opengraph-image.tsx (лот, оголошення) перекривають це файловими метаданими.
const BRAND_IMAGE_ALT = `${SITE_NAME} — пригін авто з США під ключ`;

/** Обрізає опис до 160 символів по межі слова, з «…». */
export function truncateDescription(text: string, max = DESCRIPTION_MAX): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max - 1);
  const lastSpace = cut.lastIndexOf(' ');
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
}

export interface SeoInput {
  /** Заголовок без суфікса: template з layout.tsx додасть « | AUTOforYOU» один раз. */
  title: string;
  /** true — заголовок «як є», без template (головна). */
  absoluteTitle?: boolean;
  description: string;
  /** Канонічний шлях без query ('/ua', '/local/5'). */
  path: string;
  /** Абсолютна адреса картинки. Зазвичай не потрібна: og:image дає файл opengraph-image.tsx сегмента (6.3b). */
  image?: string;
  /** У сегмента власний opengraph-image.tsx (лот, оголошення): бренд-картку за замовчуванням не підставляти,
   *  інакше вона перекриє файлову (перевірено на Next 16). */
  segmentImage?: boolean;
  /** noindex; follow лишається true, якщо followLinks не вимкнено. */
  noindex?: boolean;
  followLinks?: boolean;
}

/**
 * Єдина збірка метаданих сторінки (задача 6.3).
 *
 * Ловушка Next: `openGraph` сторінки ЦІЛКОМ замінює `openGraph` з layout.tsx
 * (об'єкти не зливаються по полях), тож siteName/locale/type додаємо тут щоразу.
 * Сторінки не пишуть openGraph/twitter вручну.
 */
export function buildMetadata(input: SeoInput): Metadata {
  const description = truncateDescription(input.description);
  const url = absoluteUrl(input.path);
  const ogTitle = input.absoluteTitle ? input.title : `${input.title} | ${SITE_NAME}`;
  return {
    title: input.absoluteTitle ? { absolute: input.title } : input.title,
    description,
    alternates: { canonical: url },
    ...(input.noindex ? { robots: { index: false, follow: input.followLinks ?? true } } : {}),
    openGraph: {
      title: ogTitle,
      description,
      url,
      siteName: SITE_NAME,
      locale: 'uk_UA',
      type: 'website',
      ...(input.segmentImage ? {} : {
        images: [input.image
          ? { url: input.image, width: 1200, height: 630, alt: input.title }
          : { url: absoluteUrl('/opengraph-image'), width: 1200, height: 630, alt: BRAND_IMAGE_ALT, type: 'image/png' }],
      }),
    },
    twitter: {
      card: 'summary_large_image',
      title: ogTitle,
      description,
      ...(input.segmentImage ? {} : { images: [input.image ?? absoluteUrl('/twitter-image')] }),
    },
  };
}

/** Чи є у query будь-який фільтр, крім `page` (такі сторінки не індексуються). */
export function hasFilters(params: Record<string, string | string[] | undefined>): boolean {
  return Object.entries(params).some(([key, raw]) => {
    if (key === 'page') return false;
    const value = Array.isArray(raw) ? raw[0] : raw;
    return value !== undefined && value !== '';
  });
}
