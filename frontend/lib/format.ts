/** «щойно / N хв тому / N год тому / 12 жовт.» для ISO-дати. */
export function timeAgo(iso: string): string {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return 'щойно';
  if (diff < 3600) return `${Math.floor(diff / 60)} хв тому`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} год тому`;
  return d.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' });
}

// 10.17: єдиний формат грошей `uk-UA` — пробіл-роздільник тисяч (U+00A0), кома як десятковий знак.
// Позначення валюти — як прийнято в проєкті: «$10 000» і «10 000 грн». Парсер у e2e знімає будь-які нецифри.
const numberFormats = new Map<number, Intl.NumberFormat>();

/** Число у форматі uk-UA; `fraction` — максимум знаків після коми (за замовчуванням 2, зайві нулі не показуються). */
export function formatNumber(value: number | string, fraction = 2): string {
  let nf = numberFormats.get(fraction);
  if (!nf) {
    nf = new Intl.NumberFormat('uk-UA', { maximumFractionDigits: fraction });
    numberFormats.set(fraction, nf);
  }
  return nf.format(Number(value));
}

export function formatUsd(value: number | string, fraction = 2): string {
  return `$${formatNumber(value, fraction)}`;
}

export function formatUah(value: number | string, fraction = 2): string {
  return `${formatNumber(value, fraction)} грн`;
}
