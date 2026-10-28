import type { AnalyticsProvider } from './types';

const TOKEN_RE = /^[A-Za-z0-9]{16,64}$/;
const SCRIPT_ATTR = 'data-afy-analytics';

/**
 * Cloudflare Web Analytics: без cookie й без localStorage, окремих подій не шле
 * (лише перегляди сторінок), тож згоди не потребує.
 */
export const cloudflare: AnalyticsProvider = {
  key: 'cloudflare_analytics',
  requiresConsent: false,
  settingKey: 'cloudflare_token',
  isValidId: (id) => TOKEN_RE.test(id),

  load(token) {
    if (!TOKEN_RE.test(token)) return;
    const s = document.createElement('script');
    s.defer = true;
    s.src = 'https://static.cloudflareinsights.com/beacon.min.js';
    s.setAttribute('data-cf-beacon', JSON.stringify({ token }));
    s.setAttribute(SCRIPT_ATTR, 'cloudflare');
    s.onerror = () => {};
    document.head.appendChild(s);
  },

  unload() {
    document.querySelectorAll(`script[${SCRIPT_ATTR}="cloudflare"]`).forEach((n) => n.remove());
  },

  track() {
    // Подій немає: лише автоматичні перегляди сторінок.
  },
};
