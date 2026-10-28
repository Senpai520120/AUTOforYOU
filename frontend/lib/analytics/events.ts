import type { EventParams } from './types';

/** Єдиний перелік подій сайту. Значення — назва події в GA4 (рекомендовані назви, де вони є). */
export const EVENTS = {
  calculator_calculate: 'calculator_calculate',
  lead_submit: 'generate_lead',
  sign_up: 'sign_up',
  phone_reveal: 'phone_reveal',
  listing_submit: 'listing_submit',
} as const;

export type EventName = keyof typeof EVENTS;

const SOURCES = new Set(['calculator', 'listing', 'landing', 'register']);

/** Біла фільтрація параметрів: тільки `source` із відомого списку, нічого іншого. */
export function sanitizeParams(params: unknown): EventParams {
  if (params && typeof params === 'object') {
    const source = (params as { source?: unknown }).source;
    if (typeof source === 'string' && SOURCES.has(source)) return { source: source as EventParams['source'] };
  }
  return {};
}
