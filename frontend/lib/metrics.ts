/**
 * Клієнтські лічильники без ПДн (задача 8.7): POST /api/v1/metrics/event/ з одним полем key.
 * Без cookie і ідентифікаторів, fire-and-forget: помилки глушаться, на UX не впливають.
 */
const ENDPOINT = '/api/v1/metrics/event/';
const VISIT_FLAG = 'metric_calculator_visit';

export type ClientMetricKey = 'calculator_visit' | 'mobile_bar_click';

export function sendMetric(key: ClientMetricKey): void {
  if (typeof window === 'undefined') return;
  const api = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
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

/** Візит калькулятора: один раз за вкладку (sessionStorage, без cookie). */
export function trackCalculatorVisitOnce(): void {
  try {
    if (window.sessionStorage.getItem(VISIT_FLAG)) return;
    window.sessionStorage.setItem(VISIT_FLAG, '1');
  } catch {
    // sessionStorage недоступний (приватний режим): рахуємо візит без прапора
  }
  sendMetric('calculator_visit');
}
