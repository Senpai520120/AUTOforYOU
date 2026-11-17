/**
 * Джерело заявки (Н-26, Н-37): UTM, реферер і сторінка входу.
 *
 * - Тільки sessionStorage: без cookie й без згоди (власні дані, третім особам не передаються).
 * - Усі звернення до сховища в try/catch (приватний режим Safari, заборона сховища).
 * - «Перше дотик»: збережене не перезаписується звичайними переходами; свіжі utm_* в URL
 *   замінюють збережені utm. Реферер власного сайту ігнорується. URL — лише шлях без query.
 * - В API йдуть тільки непорожні значення.
 */
const KEY = 'afy:attribution';
const UTM_KEYS = ['source', 'medium', 'campaign', 'content'] as const;
// Те саме правило, що в бекенді (leads/validators.py): літери, цифри, _ . -, до 100 символів.
const UTM_VALUE = /^[\p{L}\p{N}_.-]{1,100}$/u;

export interface Attribution {
  utm?: Record<string, string>;
  referrer?: string;
  entry_page_url?: string;
}

function read(): Attribution | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? (parsed as Attribution) : null;
  } catch {
    return null;
  }
}

function write(value: Attribution) {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // сховище недоступне — форма працює без джерела
  }
}

function freshUtm(search: string): Record<string, string> {
  const params = new URLSearchParams(search);
  const utm: Record<string, string> = {};
  for (const key of UTM_KEYS) {
    const v = params.get(`utm_${key}`)?.trim() ?? '';
    if (UTM_VALUE.test(v)) utm[key] = v;
  }
  return utm;
}

function externalReferrer(): string {
  try {
    if (!document.referrer) return '';
    const url = new URL(document.referrer);
    if (url.host === window.location.host) return '';
    return `${url.protocol}//${url.host}`;
  } catch {
    return '';
  }
}

/** Викликається при кожному заході на сторінку; сам вирішує, що зберігати. */
export function captureAttribution(): void {
  if (typeof window === 'undefined') return;
  const utm = freshUtm(window.location.search);
  const stored = read();
  if (stored) {
    if (Object.keys(utm).length) write({ ...stored, utm });
    return;
  }
  const record: Attribution = { entry_page_url: window.location.pathname };
  if (Object.keys(utm).length) record.utm = utm;
  const referrer = externalReferrer();
  if (referrer) record.referrer = referrer;
  write(record);
}

export function getAttribution(): Attribution {
  if (typeof window === 'undefined') return {};
  const stored = read();
  if (!stored) return {};
  const result: Attribution = {};
  if (stored.utm && Object.keys(stored.utm).length) result.utm = stored.utm;
  if (stored.referrer) result.referrer = stored.referrer;
  if (stored.entry_page_url) result.entry_page_url = stored.entry_page_url;
  return result;
}
