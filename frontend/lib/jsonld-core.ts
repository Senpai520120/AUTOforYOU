// Ядро побудови schema.org-розмітки (задача 9.54): чисті функції без імпортів сайту,
// щоб їх можна було перевіряти без браузера (e2e/seo.spec.ts). Назву, адресу сайту й реквізити приймають параметрами.

export type JsonLd = Record<string, unknown>;

const CONTEXT = 'https://schema.org';

/**
 * JSON для вставки в `<script type="application/ld+json">`.
 *
 * Текст із адмінки (назва, адреса) не повинен закрити тег: `<`, `>`, `&` і роздільники рядків
 * U+2028/2029 замінюються на \uXXXX. JSON.parse повертає вихідний рядок без змін.
 */
export function jsonLdString(data: JsonLd): string {
  return JSON.stringify(data)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .split(String.fromCharCode(0x2028)).join('\\u2028')
    .split(String.fromCharCode(0x2029)).join('\\u2029');
}

const clean = (v: string | null | undefined) => (typeof v === 'string' ? v.trim() : '');

/** Лише http(s)-посилання: щось інше (javascript:, порожнє) у sameAs не потрапляє. */
function httpUrl(v: string | null | undefined): string {
  const s = clean(v);
  try {
    const u = new URL(s);
    return u.protocol === 'https:' || u.protocol === 'http:' ? s : '';
  } catch {
    return '';
  }
}

export interface SiteIdentity {
  name: string;
  /** Адреса сайту без кінцевого слеша. */
  url: string;
}

/** Реквізити й контакти з налаштувань сайту; будь-яке поле може бути порожнім. */
export interface OrgFields {
  legalName?: string;
  telephone?: string;
  email?: string;
  address?: string;
  sameAs?: string;
}

/** Organization: порожні значення в розмітку не виводяться. */
export function buildOrganizationLd(site: SiteIdentity, f: OrgFields = {}): JsonLd {
  const legalName = clean(f.legalName);
  const telephone = clean(f.telephone);
  const email = clean(f.email);
  const address = clean(f.address);
  const sameAs = httpUrl(f.sameAs);
  return {
    '@context': CONTEXT,
    '@type': 'Organization',
    name: site.name,
    url: site.url,
    ...(legalName ? { legalName } : {}),
    ...(telephone ? { telephone } : {}),
    ...(email ? { email } : {}),
    ...(address ? { address: { '@type': 'PostalAddress', streetAddress: address } } : {}),
    ...(sameAs ? { sameAs: [sameAs] } : {}),
  };
}

export function buildWebsiteLd(site: SiteIdentity): JsonLd {
  return { '@context': CONTEXT, '@type': 'WebSite', name: site.name, url: site.url, inLanguage: 'uk' };
}

export interface Crumb {
  name: string;
  /** Шлях сайту без query ('/', '/prigon'). */
  path: string;
}

/** BreadcrumbList: позиції з 1 без пропусків, адреси абсолютні. Крихти з порожньою назвою відкидаються. */
export function buildBreadcrumbLd(siteUrl: string, crumbs: Crumb[]): JsonLd {
  const items = crumbs.filter((c) => clean(c.name));
  return {
    '@context': CONTEXT,
    '@type': 'BreadcrumbList',
    itemListElement: items.map((c, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: clean(c.name),
      item: `${siteUrl}${c.path.startsWith('/') ? c.path : `/${c.path}`}`,
    })),
  };
}
