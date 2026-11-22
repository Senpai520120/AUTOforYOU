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

export interface FaqEntry {
  question: string;
  answer: string;
}

/** FAQPage: лише записи з непорожніми питанням і відповіддю; без записів — null (розмітку не виводимо). */
export function buildFaqLd(items: FaqEntry[]): JsonLd | null {
  const valid = items.filter((i) => clean(i.question) && clean(i.answer));
  if (!valid.length) return null;
  return {
    '@context': CONTEXT,
    '@type': 'FAQPage',
    mainEntity: valid.map((i) => ({
      '@type': 'Question',
      name: clean(i.question),
      acceptedAnswer: { '@type': 'Answer', text: clean(i.answer) },
    })),
  };
}

// ─── Car + Offer (задача 12.1) ───────────────────────────────────────────────

const FUEL_TYPES: Record<string, string> = {
  petrol: 'Gasoline', diesel: 'Diesel', electric: 'Electric', hybrid: 'Hybrid', gas: 'LPG',
};
const TRANSMISSIONS: Record<string, string> = {
  auto: 'Automatic', manual: 'Manual', cvt: 'CVT', robot: 'Automated manual',
};
const CONDITIONS: Record<string, string> = {
  new: 'NewCondition', used: 'UsedCondition', damaged: 'DamagedCondition',
};
const CURRENCIES = ['UAH', 'USD', 'EUR'];
/** Лише 17 символів без I, O, Q; часткові й маскований VIN (1HGCM82633A****) не проходять. */
const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/i;

export type Availability = 'InStock' | 'OutOfStock' | 'PreOrder';
const schemaUrl = (name: string) => `https://schema.org/${name}`;

/** Місцеве оголошення: active → в наявності, sold → продано; решта (hidden, pending…) — null, розмітки немає. */
export function localAvailability(status: string | null | undefined): Availability | null {
  if (status === 'active') return 'InStock';
  if (status === 'sold') return 'OutOfStock';
  return null;
}

/** Лот: in_stock → в наявності, in_transit → під замовлення, sold → продано; невідомий — null. */
export function lotAvailability(status: string | null | undefined): Availability | null {
  if (status === 'in_stock') return 'InStock';
  if (status === 'in_transit') return 'PreOrder';
  if (status === 'sold') return 'OutOfStock';
  return null;
}

/**
 * Вхід для Car + Offer. Полів продавця (ім'я, телефон, місто, регіон, id, опис) тут немає свідомо:
 * персональні дані не можуть потрапити в розмітку по побудові.
 */
export interface VehicleOfferInput {
  make: string;
  model: string;
  year?: number | null;
  mileageKm?: number | null;
  /** Ключ API (petrol, diesel…); невідомий — поле опускається. */
  fuelType?: string | null;
  transmission?: string | null;
  condition?: string | null;
  /** Лише публічний повний VIN (лоти). Для місцевих оголошень і лендингів не передається. */
  vin?: string | null;
  /** Абсолютна адреса сторінки. */
  url: string;
  /** Рядок Decimal з API ("12500.00") або число. */
  price: string | number;
  currency: string;
  /**
   * undefined — поле availability не виводиться (лендинг: оцінка послуги, а не залишок).
   * null — статус не публічний: розмітка не будується взагалі.
   */
  availability?: Availability | null;
}

/**
 * Ціна рядком без округлення через float: лише "123" або "123.45", більше нуля.
 * Запис з API береться як є ("12500.00" лишається "12500.00"). Інше (NaN, 0, мінус, "1e5") — null.
 */
export function normalizePrice(v: string | number | null | undefined): string | null {
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return null;
    v = String(v);
  }
  const s = clean(v);
  if (!/^\d+(\.\d+)?$/.test(s) || !/[1-9]/.test(s)) return null;
  return s;
}

/** Car з вкладеним Offer; null — немає обов'язкових даних (марка/модель, ціна, валюта) або статус не публічний. */
export function buildVehicleOfferLd(input: VehicleOfferInput): JsonLd | null {
  const make = clean(input.make);
  const model = clean(input.model);
  const price = normalizePrice(input.price);
  const currency = clean(input.currency).toUpperCase();
  const url = httpUrl(input.url);
  if (!make || !model || !price || !CURRENCIES.includes(currency) || !url) return null;
  if (input.availability === null) return null;

  const year = Number.isInteger(input.year) && (input.year as number) > 0 ? (input.year as number) : null;
  const mileage = typeof input.mileageKm === 'number' && Number.isFinite(input.mileageKm) && input.mileageKm >= 0
    ? input.mileageKm : null;
  const fuel = FUEL_TYPES[clean(input.fuelType)];
  const gearbox = TRANSMISSIONS[clean(input.transmission)];
  const condition = CONDITIONS[clean(input.condition)];
  const vin = clean(input.vin);

  return {
    '@context': CONTEXT,
    '@type': 'Car',
    name: [make, model, year].filter((p) => p !== null).join(' '),
    brand: { '@type': 'Brand', name: make },
    model,
    ...(year ? { vehicleModelDate: String(year) } : {}),
    ...(mileage !== null ? { mileageFromOdometer: { '@type': 'QuantitativeValue', value: mileage, unitCode: 'KMT' } } : {}),
    ...(fuel ? { fuelType: fuel } : {}),
    ...(gearbox ? { vehicleTransmission: gearbox } : {}),
    ...(VIN_RE.test(vin) ? { vehicleIdentificationNumber: vin } : {}),
    ...(condition ? { itemCondition: schemaUrl(condition) } : {}),
    url,
    offers: {
      '@type': 'Offer',
      price,
      priceCurrency: currency,
      ...(input.availability ? { availability: schemaUrl(input.availability) } : {}),
      url,
    },
  };
}
