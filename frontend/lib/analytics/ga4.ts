import type { AnalyticsProvider, EventParams } from './types';

const ID_RE = /^G-[A-Z0-9]{4,20}$/;
const SCRIPT_ATTR = 'data-afy-analytics';

type GaWindow = Window & {
  dataLayer?: unknown[];
  gtag?: (...args: unknown[]) => void;
  [key: string]: unknown;
};

let currentId = '';
// gtag.js после загрузки остаётся в памяти даже без <script>: при повторном согласии его не пересоздаём.
let initialized = false;
let lastPath = '';
let prevPath = '';

/** Адреса в GA — только origin + pathname: query несёт токены, id диалогов и поисковые запросы. */
export function cleanLocation(): string {
  return window.location.origin + window.location.pathname;
}

/** Referrer без query и hash; чужой или битый адрес сводится к origin + pathname либо ''. */
export function cleanReferrer(): string {
  if (prevPath) return window.location.origin + prevPath;
  try {
    const u = new URL(document.referrer);
    return u.origin + u.pathname;
  } catch {
    return '';
  }
}

function pageView(force: boolean): void {
  const w = window as unknown as GaWindow;
  if (typeof w.gtag !== 'function') return;
  const path = window.location.pathname;
  if (!force && path === lastPath) return;
  if (lastPath) prevPath = lastPath;
  lastPath = path;
  const params = { page_location: cleanLocation(), page_referrer: cleanReferrer() };
  w.gtag('set', params);
  w.gtag('event', 'page_view', params);
}


/** Видаляє cookie GA (_ga, _ga_*, _gid, _gat*) на хості та батьківських доменах. */
export function deleteGaCookies(): void {
  const names = document.cookie
    .split(';')
    .map((c) => c.split('=')[0].trim())
    .filter((n) => n === '_ga' || n === '_gid' || n.startsWith('_ga_') || n.startsWith('_gat'));
  if (!names.length) return;
  const parts = window.location.hostname.split('.');
  const domains: string[] = [''];
  for (let i = 0; i < parts.length - 1; i++) domains.push(`; domain=${parts.slice(i).join('.')}`);
  for (const name of names) {
    for (const d of domains) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${d}`;
    }
  }
}

export const ga4: AnalyticsProvider = {
  key: 'ga4',
  requiresConsent: true,
  settingKey: 'ga4_id',
  isValidId: (id) => ID_RE.test(id),

  load(id) {
    if (!ID_RE.test(id)) return;
    const w = window as unknown as GaWindow;
    currentId = id;
    w[`ga-disable-${id}`] = false;
    if (initialized && typeof w.gtag === 'function') {
      // Повторна згода: gtag.js уже в пам'яті, лише знімаємо заборону й повертаємо вимірювання.
      w.gtag('consent', 'update', { analytics_storage: 'granted' });
      pageView(true);
      return;
    }
    initialized = true;
    w.dataLayer = w.dataLayer || [];
    // gtag.js читає саме об'єкт arguments, тому стрілочна функція тут не підходить.
    w.gtag = function gtag() {
      // eslint-disable-next-line prefer-rest-params
      (w.dataLayer as unknown[]).push(arguments);
    };
    // Consent Mode: лише вимірювання; реклама та персоналізація заборонені.
    w.gtag('consent', 'default', {
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied',
      analytics_storage: 'granted',
    });
    w.gtag('js', new Date());
    w.gtag('config', id, {
      send_page_view: false, // page_view шлемо самі, з адресою без query
      page_location: cleanLocation(),
      page_referrer: cleanReferrer(),
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
    });
    pageView(true);
    const s = document.createElement('script');
    s.async = true;
    s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
    s.setAttribute(SCRIPT_ATTR, 'ga4');
    s.onerror = () => {};
    document.head.appendChild(s);
  },

  unload() {
    const w = window as unknown as GaWindow;
    // Спершу сказати GA, що зберігання заборонено, потім прибрати cookie.
    if (typeof w.gtag === 'function') w.gtag('consent', 'update', { analytics_storage: 'denied' });
    if (currentId) w[`ga-disable-${currentId}`] = true;
    document.querySelectorAll(`script[${SCRIPT_ATTR}="ga4"]`).forEach((n) => n.remove());
    deleteGaCookies();
  },

  track(event: string, params: EventParams) {
    const w = window as unknown as GaWindow;
    if (typeof w.gtag === 'function') w.gtag('event', event, { ...params, page_location: cleanLocation() });
  },

  pageView() {
    pageView(false);
  },
};
