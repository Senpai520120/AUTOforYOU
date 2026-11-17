// Розбір помилок калькулятора (2.6, 09-Q6): жодного сирого JSON на сторінці.
import { ApiError } from '@/api/client';

export interface CalcErrorView {
  fieldErrors: Record<string, string>;
  message: string;
  details: string[];
}

const NOT_CONFIGURED = 'Калькулятор ще не налаштовано для цих параметрів. Спробуйте інший порт чи аукціон або залиште заявку брокеру.';
const TOO_MANY = 'Забагато розрахунків, спробуйте за годину.';
const GENERIC = 'Не вдалося виконати розрахунок. Спробуйте пізніше.';
const INVALID = 'Перевірте поля форми.';

// Технічні назви тарифів → людська мова (бачать лише staff/broker, яким сервер віддає `missing`).
const MODEL_LABELS: [string, string][] = [
  ['AuctionFeeTier', 'збір аукціону'],
  ['UsLandRoute', 'доставка по США'],
  ['OceanFreightRate', 'морський фрахт'],
  ['EuToUaDeliveryRate', 'доставка ЄС → Україна'],
  ['ExchangeRate', 'курс валют'],
  ['CustomsExciseRate', 'ставка акцизу'],
  ['CustomsCalcRule', 'правило розмитнення'],
  ['PensionFundBracket', 'пенсійний збір'],
];

function humanize(item: string): string {
  for (const [model, label] of MODEL_LABELS) {
    if (item.startsWith(model)) return `${label}${item.slice(model.length).replace(/^:?\s*(для\s*)?/, ': ')}`.replace(/:\s*$/, '');
  }
  return item;
}

function firstMessage(value: unknown): string {
  if (Array.isArray(value)) return firstMessage(value[0]);
  return typeof value === 'string' ? value : '';
}

export function describeCalcError(err: unknown): CalcErrorView {
  const status = err instanceof ApiError ? err.status : 0;
  const data = (err instanceof ApiError ? err.data : null) as Record<string, unknown> | null;

  if (status === 400 && data && typeof data === 'object') {
    const fieldErrors: Record<string, string> = {};
    for (const [field, value] of Object.entries(data)) {
      const msg = firstMessage(value);
      if (msg) fieldErrors[field] = msg;
    }
    return { fieldErrors, message: INVALID, details: [] };
  }
  if (status === 422) {
    const missing = Array.isArray(data?.missing) ? (data.missing as unknown[]).filter((m): m is string => typeof m === 'string') : [];
    return { fieldErrors: {}, message: NOT_CONFIGURED, details: missing.map(humanize) };
  }
  if (status === 429) return { fieldErrors: {}, message: TOO_MANY, details: [] };
  return { fieldErrors: {}, message: GENERIC, details: [] };
}

// "0.1000" → "10", "0.0500" → "5", "0.125" → "12.5" — без parseFloat-округлення.
export function percentFromDecimal(value: string | undefined): string {
  if (!value || !/^\d+(\.\d+)?$/.test(value)) return '—';
  const [int, frac = ''] = value.split('.');
  const padded = frac.padEnd(2, '0');
  const whole = String(Number(int + padded.slice(0, 2)));
  const rest = padded.slice(2).replace(/0+$/, '');
  return rest ? `${whole}.${rest}` : whole;
}
