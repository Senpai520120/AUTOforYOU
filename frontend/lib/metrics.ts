import { API_URL } from '@/lib/config';
/**
 * Клієнтські лічильники без ПДн (задача 8.7): POST /api/v1/metrics/event/ з одним полем key.
 * Без cookie і ідентифікаторів, fire-and-forget: помилки глушаться, на UX не впливають.
 */
const ENDPOINT = '/api/v1/metrics/event/';

export type ClientMetricKey = 'calculator_visit' | 'landing_visit' | 'mobile_bar_click';

export function sendMetric(key: ClientMetricKey): void {
  if (typeof window === 'undefined') return;
  const api = API_URL;
  try {
    void fetch(`${api}${ENDPOINT}`, {
      method: 'POST',
      body: JSON.stringify({ key }),
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
      credentials: 'omit',
    }).catch(() => undefined);
  } catch {
    // лічильник не повинен ламати сторінку
  }
}

/** Один раз за вкладку (sessionStorage, без cookie). */
function trackVisitOnce(key: ClientMetricKey): void {
  const flag = `metric_${key}`;
  try {
    if (window.sessionStorage.getItem(flag)) return;
    window.sessionStorage.setItem(flag, '1');
  } catch {
    // sessionStorage недоступний (приватний режим): рахуємо візит без прапора
  }
  sendMetric(key);
}

export function trackCalculatorVisitOnce(): void {
  trackVisitOnce('calculator_visit');
}

export function trackLandingVisitOnce(): void {
  trackVisitOnce('landing_visit');
}
