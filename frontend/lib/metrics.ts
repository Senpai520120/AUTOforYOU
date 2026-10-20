// Дневні лічильники без ПДн (8.7): лише ключ події, без cookie та ідентифікаторів.
// Fire-and-forget: помилки глушаться, сторінка від лічильника не залежить.
const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type PublicMetricKey = 'calculator_visit' | 'mobile_bar_click';

export function sendMetric(key: PublicMetricKey): void {
  try {
    void fetch(`${API}/api/v1/metrics/event/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key }),
      credentials: 'omit',
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // мережа/середовище без fetch — лічильник не важливіший за сторінку
  }
}

// Один раз за вкладку: прапорець у sessionStorage (не cookie, нічого не йде на сервер).
export function sendMetricOncePerSession(key: PublicMetricKey): void {
  const flag = `metric_sent:${key}`;
  try {
    if (window.sessionStorage.getItem(flag)) return;
    window.sessionStorage.setItem(flag, '1');
  } catch {
    // sessionStorage недоступний (приватний режим) — рахуємо, але без дедуплікації
  }
  sendMetric(key);
}
