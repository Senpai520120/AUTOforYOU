// Структуровані дані schema.org (задача 9.54): прив'язка чистого ядра (jsonld-core.ts) до налаштувань сайту.
import type { LandingDetail, Listing, LocalListing, SiteSettings } from '@/lib/types';
import { SITE_NAME, SITE_URL } from '@/lib/site';
import { listingSlug } from '@/lib/utils';
import { ownerTitle, supportContact } from '@/lib/site-settings';
import {
  buildBreadcrumbLd,
  buildFaqLd,
  buildOrganizationLd,
  buildVehicleOfferLd,
  buildWebsiteLd,
  localAvailability,
  lotAvailability,
  type Crumb,
  type FaqEntry,
  type JsonLd,
} from '@/lib/jsonld-core';

export { jsonLdString } from '@/lib/jsonld-core';
export type { Crumb, FaqEntry, JsonLd };

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

/** FAQPage для питань про модель; null — питань немає. */
export const faqLd = (items: FaqEntry[]): JsonLd | null => buildFaqLd(items);

/**
 * Car + Offer для місцевого оголошення (12.1). Передаються лише технічні поля: ім'я, телефон, місто,
 * регіон, seller_* й опис продавця не читаються. Статус без availability (hidden, pending…) — null.
 */
export function localListingLd(l: LocalListing): JsonLd | null {
  return buildVehicleOfferLd({
    make: l.make, model: l.model, year: l.year, mileageKm: l.mileage_km,
    fuelType: l.fuel_type, transmission: l.transmission, condition: l.condition,
    price: l.price, currency: l.currency,
    url: `${SITE_URL}/local/${l.id}`,
    availability: localAvailability(l.status),
  });
}

/** Car + Offer для лота: VIN публічний (показується гостю на сторінці), тому йде в розмітку. */
export function listingLd(l: Listing): JsonLd | null {
  const v = l.vehicle_detail;
  return buildVehicleOfferLd({
    make: v.make, model: v.model, year: v.year, mileageKm: v.mileage_km,
    fuelType: v.fuel_type, vin: v.vin,
    price: l.price, currency: l.currency,
    url: `${SITE_URL}/listings/${listingSlug(l)}`,
    availability: lotAvailability(l.status),
  });
}

/** Car + Offer для лендингу: ціна — оцінка розрахунку в USD; без VIN, пробігу, року й availability. */
export function landingLd(p: LandingDetail): JsonLd | null {
  return buildVehicleOfferLd({
    make: p.make, model: p.model, fuelType: p.fuel_type,
    price: p.calculation.total_usd_full ?? p.calculation.total_usd, currency: 'USD',
    url: `${SITE_URL}/prigon/${p.slug}`,
  });
}
