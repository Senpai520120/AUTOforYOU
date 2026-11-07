// Структуровані дані schema.org (задача 9.54): прив'язка чистого ядра (jsonld-core.ts) до налаштувань сайту.
import type { SiteSettings } from '@/lib/types';
import { SITE_NAME, SITE_URL } from '@/lib/site';
import { ownerTitle, supportContact } from '@/lib/site-settings';
import {
  buildBreadcrumbLd,
  buildOrganizationLd,
  buildWebsiteLd,
  type Crumb,
  type JsonLd,
} from '@/lib/jsonld-core';

export { jsonLdString } from '@/lib/jsonld-core';
export type { Crumb, JsonLd };

const SITE = { name: SITE_NAME, url: SITE_URL };

/**
 * Organization: назва бренду з SITE_NAME, реквізити й контакти лише з налаштувань сайту.
 * ЄДРПОУ/ІПН (owner_code) не виводиться ніколи. null (API недоступне) — лише назва й адреса сайту.
 */
export function organizationLd(s: SiteSettings | null): JsonLd {
  return buildOrganizationLd(SITE, {
    legalName: ownerTitle(s),
    telephone: s?.phone,
    email: supportContact(s),
    address: s?.owner_address,
    sameAs: s?.telegram_channel_url,
  });
}

export const websiteLd = (): JsonLd => buildWebsiteLd(SITE);

export const breadcrumbLd = (crumbs: Crumb[]): JsonLd => buildBreadcrumbLd(SITE_URL, crumbs);
