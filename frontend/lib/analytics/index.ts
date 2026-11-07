import { hasAnalyticsConsent } from '@/lib/consent';
import { cloudflare } from './cloudflare';
import { EVENTS, sanitizeParams, type EventName } from './events';
import { ga4 } from './ga4';
import type { AnalyticsProvider, PublicAnalytics } from './types';

export type { PublicAnalytics, EventParams, AnalyticsProvider } from './types';
export type { EventName } from './events';

const PROVIDERS: AnalyticsProvider[] = [ga4, cloudflare];

// ключ провайдера -> ID, з яким він зараз завантажений
const loaded = new Map<string, string>();

/**
 * Привести завантажені провайдери у відповідність до ID з налаштувань і поточної згоди.
 * Викликається на кожну зміну згоди та після отримання налаштувань. Ідемпотентна.
 */
export function syncProviders(analytics: PublicAnalytics | null | undefined): void {
  if (typeof window === 'undefined') return;
  const consent = hasAnalyticsConsent();
  for (const p of PROVIDERS) {
    try {
      const raw = analytics?.[p.settingKey];
      const id = typeof raw === 'string' && p.isValidId(raw) ? raw : '';
      const want = !!id && (!p.requiresConsent || consent);
      const have = loaded.get(p.key);
      if (have && (!want || have !== id)) {
        p.unload();
        loaded.delete(p.key);
      }
      if (want && !loaded.has(p.key)) {
        p.load(id);
        loaded.set(p.key, id);
      }
    } catch {
      // Аналітика не повинна ламати сайт.
    }
  }
}

/** Перегляд сторінки при зміні маршруту: адреса без query. Без згоди нічого не робить. */
export function trackPageView(): void {
  if (typeof window === 'undefined' || !hasAnalyticsConsent()) return;
  for (const p of PROVIDERS) {
    if (!p.requiresConsent || !loaded.has(p.key)) continue;
    try {
      p.pageView?.();
    } catch {
      // ignore
    }
  }
}

/**
 * Єдина точка відправки подій. Без згоди нічого не робить і не накопичує чергу.
 * Параметри фільтруються: проходить лише категорія `source` зі списку.
 */
export function trackEvent(name: EventName, params?: unknown): void {
  if (typeof window === 'undefined' || !hasAnalyticsConsent()) return;
  const event = EVENTS[name];
  if (!event) return;
  const clean = sanitizeParams(params);
  for (const p of PROVIDERS) {
    if (!p.requiresConsent || !loaded.has(p.key)) continue;
    try {
      p.track(event, clean);
    } catch {
      // ignore
    }
  }
}
